"""
Camera Select Entity for Unfolded Circle integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any, Dict, List, Optional

from ucapi import StatusCodes
from ucapi.select import Select, Attributes, Commands, States

LOG = logging.getLogger(__name__)


class CameraSelect(Select):
    """Select entity for switching between security cameras."""

    def __init__(self, integration_api: Any, cameras_config: List[Dict[str, Any]], media_player: Any):
        """Initialize the camera select entity.

        Args:
            integration_api: The integration API instance
            cameras_config: List of camera configurations
            media_player: Reference to the media player entity to control
        """
        self._api = integration_api
        self.cameras_config = cameras_config
        self.media_player = media_player

        # Build list of camera names
        camera_options = [camera["name"] for camera in cameras_config]
        current_option = camera_options[0] if camera_options else ""

        entity_id = "camera_selector"
        entity_name = "Camera Selector"

        attributes = {
            Attributes.STATE: States.ON,
            Attributes.OPTIONS: camera_options,
            Attributes.CURRENT_OPTION: current_option
        }

        super().__init__(
            identifier=entity_id,
            name=entity_name,
            attributes=attributes,
            cmd_handler=self.handle_command
        )

        LOG.info(f"Created camera select entity with {len(camera_options)} cameras")

    async def push_initial_state(self) -> None:
        """Push initial entity state to remote."""
        LOG.info(f"Pushing initial state for {self.id}")

        if not self._api or not self._api.configured_entities.contains(self.id):
            LOG.warning(f"Entity {self.id} not in configured entities yet")
            return

        attrs_to_update = {
            Attributes.STATE: States.ON,
            Attributes.OPTIONS: self.attributes[Attributes.OPTIONS],
            Attributes.CURRENT_OPTION: self.attributes[Attributes.CURRENT_OPTION]
        }

        self._api.configured_entities.update_attributes(self.id, attrs_to_update)
        LOG.info(f"Initial state pushed for {self.id}")

    async def handle_command(self, entity: Select, command: str, params: Optional[Dict[str, Any]] = None) -> StatusCodes:
        """Handle commands from the remote.

        Args:
            entity: The select entity instance
            command: Command to execute
            params: Optional command parameters

        Returns:
            Status code indicating success or failure
        """
        LOG.info(f"Camera select command received: {command}, params: {params}")

        try:
            if command == Commands.SELECT_OPTION:
                option = params.get("option") if params else None
                return await self._select_camera(option)
            elif command == Commands.SELECT_NEXT:
                return await self._select_next_camera()
            elif command == Commands.SELECT_PREVIOUS:
                return await self._select_previous_camera()
            elif command == Commands.SELECT_FIRST:
                return await self._select_first_camera()
            elif command == Commands.SELECT_LAST:
                return await self._select_last_camera()
            else:
                LOG.warning(f"Unsupported command: {command}")
                return StatusCodes.BAD_REQUEST

        except Exception as e:
            LOG.error(f"Error executing command {command}: {e}", exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _select_camera(self, camera_name: str) -> StatusCodes:
        """Select a specific camera by name.

        Args:
            camera_name: Name of the camera to select

        Returns:
            Status code indicating success or failure
        """
        if not camera_name or camera_name not in self.attributes[Attributes.OPTIONS]:
            LOG.error(f"Invalid camera name: {camera_name}")
            return StatusCodes.BAD_REQUEST

        LOG.info(f"Selecting camera: {camera_name}")

        # Update select entity state
        self.attributes[Attributes.CURRENT_OPTION] = camera_name
        self._update_remote_state()

        # Trigger media player to switch camera
        if self.media_player:
            LOG.info(f"Triggering media player to switch to: {camera_name}")
            result = await self.media_player._select_source(camera_name)

            if result == StatusCodes.OK:
                LOG.info(f"Successfully switched media player to camera: {camera_name}")
            else:
                LOG.error(f"Failed to switch media player to camera: {camera_name}")

            return result
        else:
            LOG.error("No media player reference available")
            return StatusCodes.SERVER_ERROR

    async def _select_next_camera(self) -> StatusCodes:
        """Select the next camera in the list."""
        options = self.attributes[Attributes.OPTIONS]
        current = self.attributes[Attributes.CURRENT_OPTION]

        try:
            current_index = options.index(current)
            next_index = (current_index + 1) % len(options)
            next_camera = options[next_index]

            LOG.info(f"Selecting next camera: {next_camera}")
            return await self._select_camera(next_camera)
        except (ValueError, IndexError) as e:
            LOG.error(f"Error selecting next camera: {e}")
            return StatusCodes.SERVER_ERROR

    async def _select_previous_camera(self) -> StatusCodes:
        """Select the previous camera in the list."""
        options = self.attributes[Attributes.OPTIONS]
        current = self.attributes[Attributes.CURRENT_OPTION]

        try:
            current_index = options.index(current)
            prev_index = (current_index - 1) % len(options)
            prev_camera = options[prev_index]

            LOG.info(f"Selecting previous camera: {prev_camera}")
            return await self._select_camera(prev_camera)
        except (ValueError, IndexError) as e:
            LOG.error(f"Error selecting previous camera: {e}")
            return StatusCodes.SERVER_ERROR

    async def _select_first_camera(self) -> StatusCodes:
        """Select the first camera in the list."""
        options = self.attributes[Attributes.OPTIONS]

        if not options:
            LOG.error("No cameras available")
            return StatusCodes.SERVER_ERROR

        first_camera = options[0]
        LOG.info(f"Selecting first camera: {first_camera}")
        return await self._select_camera(first_camera)

    async def _select_last_camera(self) -> StatusCodes:
        """Select the last camera in the list."""
        options = self.attributes[Attributes.OPTIONS]

        if not options:
            LOG.error("No cameras available")
            return StatusCodes.SERVER_ERROR

        last_camera = options[-1]
        LOG.info(f"Selecting last camera: {last_camera}")
        return await self._select_camera(last_camera)

    def _update_remote_state(self) -> None:
        """Update entity state on remote."""
        if not self._api or not self._api.configured_entities.contains(self.id):
            LOG.debug(f"Entity {self.id} not subscribed, skipping state update")
            return

        attrs_to_update = {
            Attributes.STATE: States.ON,
            Attributes.CURRENT_OPTION: self.attributes[Attributes.CURRENT_OPTION]
        }

        self._api.configured_entities.update_attributes(self.id, attrs_to_update)
        LOG.debug(f"Remote state updated: current option = {self.attributes[Attributes.CURRENT_OPTION]}")

    def update_from_media_player(self, camera_name: str) -> None:
        """Update select entity when media player changes source externally.

        Args:
            camera_name: Name of the camera now selected in media player
        """
        if camera_name in self.attributes[Attributes.OPTIONS]:
            LOG.info(f"Syncing select entity to media player source: {camera_name}")
            self.attributes[Attributes.CURRENT_OPTION] = camera_name
            self._update_remote_state()
        else:
            LOG.warning(f"Camera {camera_name} not in select options")
