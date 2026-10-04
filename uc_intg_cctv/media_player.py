"""
CCTV media player entity for displaying camera snapshots.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import StatusCodes, media_player
from ucapi_framework import MediaPlayerEntity

from uc_intg_cctv.config import CCTVConfig
from uc_intg_cctv.device import CCTVDevice

_LOG = logging.getLogger(__name__)

FEATURES = [
    media_player.Features.ON_OFF,
    media_player.Features.SELECT_SOURCE,
    media_player.Features.MEDIA_IMAGE_URL,
    media_player.Features.MEDIA_TITLE,
    media_player.Features.MEDIA_TYPE,
]


class CCTVMediaPlayer(MediaPlayerEntity):
    """Media player entity that displays camera snapshots on the remote screen."""

    def __init__(self, device_config: CCTVConfig, device: CCTVDevice) -> None:
        self._device = device
        entity_id = f"media_player.{device_config.identifier}"
        super().__init__(
            entity_id,
            device_config.name,
            FEATURES,
            {
                media_player.Attributes.STATE: media_player.States.STANDBY,
                media_player.Attributes.SOURCE: "",
                media_player.Attributes.SOURCE_LIST: [],
                media_player.Attributes.MEDIA_IMAGE_URL: "",
                media_player.Attributes.MEDIA_TITLE: "",
                media_player.Attributes.MEDIA_TYPE: "video",
            },
            device_class=media_player.DeviceClasses.TV,
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Sync entity state from device."""
        if self._device.state == "UNAVAILABLE":
            self.update({media_player.Attributes.STATE: media_player.States.UNAVAILABLE})
            return

        camera_names = self._device.camera_names
        current = self._device.current_camera_name

        state = media_player.States.PLAYING if self._device.streaming else media_player.States.ON

        attrs: dict[str, Any] = {
            media_player.Attributes.STATE: state,
            media_player.Attributes.SOURCE_LIST: camera_names,
            media_player.Attributes.SOURCE: current,
            media_player.Attributes.MEDIA_TITLE: current,
            media_player.Attributes.MEDIA_TYPE: "video",
        }

        if self._device.snapshot_base64:
            attrs[media_player.Attributes.MEDIA_IMAGE_URL] = self._device.snapshot_base64

        self.update(attrs)

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle media player commands."""
        try:
            match cmd_id:
                case media_player.Commands.PLAY_PAUSE | media_player.Commands.TOGGLE:
                    return StatusCodes.OK
                case media_player.Commands.ON:
                    if not self._device.streaming and not await self._device.start_streaming():
                        return StatusCodes.SERVICE_UNAVAILABLE
                case media_player.Commands.OFF:
                    await self._device.stop_streaming()
                case media_player.Commands.SELECT_SOURCE:
                    source = params.get("source", "") if params else ""
                    names = self._device.camera_names
                    if source in names:
                        await self._device.select_camera(names.index(source))
                        if not self._device.streaming and not await self._device.start_streaming():
                            return StatusCodes.SERVICE_UNAVAILABLE
                    else:
                        return StatusCodes.BAD_REQUEST
                case _:
                    return StatusCodes.NOT_IMPLEMENTED
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Command %s failed: %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR
