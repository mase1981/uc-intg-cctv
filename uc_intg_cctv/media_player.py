"""
Security Camera Media Player Entity for Unfolded Circle integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ucapi import StatusCodes
from ucapi.media_player import MediaPlayer, Attributes, Features, States, MediaType, Commands

from uc_intg_cctv.client import SecurityCameraClient
from uc_intg_cctv.config import create_entity_id

LOG = logging.getLogger(__name__)


class SecurityCameraMediaPlayer(MediaPlayer):
    """Security Camera Media Player with snapshot viewing."""
    
    def __init__(self, integration_api: Any, cameras_config: List[Dict[str, Any]]):
        """Initialize the camera media player."""
        self._api = integration_api
        self.cameras_config = cameras_config
        self.clients: Dict[str, SecurityCameraClient] = {}
        
        for camera_config in cameras_config:
            camera_name = camera_config["name"]
            self.clients[camera_name] = SecurityCameraClient(camera_config)
        
        source_list = [camera["name"] for camera in cameras_config]
        current_source = source_list[0] if source_list else ""
        
        entity_id = "security_cameras"
        entity_name = "Security Cameras"
        
        features = [
            Features.ON_OFF,
            Features.SELECT_SOURCE
        ]
        
        attributes = {
            Attributes.STATE: States.OFF,
            Attributes.MEDIA_TYPE: MediaType.VIDEO,
            Attributes.SOURCE_LIST: source_list,
            Attributes.SOURCE: current_source,
            Attributes.MEDIA_IMAGE_URL: "",
            Attributes.MEDIA_TITLE: current_source,
            Attributes.MEDIA_ARTIST: "Camera View"
        }
        
        super().__init__(
            identifier=entity_id,
            name=entity_name,
            features=features,
            attributes=attributes,
            device_class="tv",
            cmd_handler=self.handle_command
        )
        
        self.current_source = current_source
        self.current_client: Optional[SecurityCameraClient] = None
        self.is_streaming = False
        self.stream_task: Optional[asyncio.Task] = None
        self.last_image_update = 0
        self.refresh_rate = 10
        
        if current_source and current_source in self.clients:
            self.current_client = self.clients[current_source]
        
        LOG.info(f"Created camera entity with {len(source_list)} cameras (10s refresh)")
    
    async def push_initial_state(self) -> None:
        """Push initial entity state to remote."""
        LOG.info(f"Pushing initial state for {self.id}")
        
        if not self._api or not self._api.configured_entities.contains(self.id):
            LOG.warning(f"Entity {self.id} not in configured entities yet")
            return
        
        attrs_to_update = {
            Attributes.STATE: States.OFF,
            Attributes.MEDIA_TYPE: MediaType.VIDEO,
            Attributes.SOURCE_LIST: self.attributes[Attributes.SOURCE_LIST],
            Attributes.SOURCE: self.attributes[Attributes.SOURCE],
            Attributes.MEDIA_IMAGE_URL: "",
            Attributes.MEDIA_TITLE: self.attributes[Attributes.SOURCE],
            Attributes.MEDIA_ARTIST: "Camera View"
        }
        
        self._api.configured_entities.update_attributes(self.id, attrs_to_update)
        LOG.info(f"Initial state pushed for {self.id}")
    
    def is_on(self) -> bool:
        """Check if camera feed is currently on."""
        return self.attributes[Attributes.STATE] in [States.PLAYING, States.ON]
    
    async def handle_command(self, entity: MediaPlayer, command: str, params: Optional[Dict[str, Any]] = None) -> StatusCodes:
        """Handle commands from the remote."""
        LOG.info(f"Command received: {command}, params: {params}")
        
        try:
            if command == Commands.ON:
                return await self._turn_on()
            elif command == Commands.OFF:
                return await self._turn_off()
            elif command == Commands.SELECT_SOURCE:
                source = params.get("source") if params else None
                return await self._select_source(source)
            else:
                LOG.warning(f"Unsupported command: {command}")
                return StatusCodes.BAD_REQUEST
                
        except Exception as e:
            LOG.error(f"Error executing command {command}: {e}", exc_info=True)
            return StatusCodes.SERVER_ERROR
    
    async def _turn_on(self) -> StatusCodes:
        """Turn on camera snapshot display."""
        LOG.info("Starting camera snapshot display")
        
        if not self.current_client:
            LOG.error("No camera selected")
            return StatusCodes.BAD_REQUEST
        
        self.attributes[Attributes.STATE] = States.PLAYING
        self.attributes[Attributes.MEDIA_TITLE] = self.current_source
        
        self._update_remote_state()
        
        await self.start_image_streaming()
        
        return StatusCodes.OK
    
    async def _turn_off(self) -> StatusCodes:
        """Turn off camera snapshot display."""
        LOG.info("Stopping camera snapshot display")
        
        await self.stop_image_streaming()
        
        self.attributes[Attributes.STATE] = States.OFF
        self.attributes[Attributes.MEDIA_IMAGE_URL] = ""
        
        self._update_remote_state()
        
        return StatusCodes.OK
    
    async def _select_source(self, source_name: str) -> StatusCodes:
        """Switch to different camera source."""
        if not source_name or source_name not in self.clients:
            LOG.error(f"Invalid camera source: {source_name}")
            return StatusCodes.BAD_REQUEST
        
        LOG.info(f"Switching to camera: {source_name}")
        
        was_streaming = self.is_streaming
        if was_streaming:
            LOG.info("Stopping previous stream before switching")
            await self.stop_image_streaming()
        
        self.current_source = source_name
        self.current_client = self.clients[source_name]
        
        LOG.info(f"Client assigned: {self.current_client is not None}")
        
        self.attributes[Attributes.SOURCE] = source_name
        self.attributes[Attributes.MEDIA_TITLE] = source_name
        
        self._update_remote_state()
        
        await asyncio.sleep(0.1)
        
        if self.is_on():
            LOG.info(f"Entity is ON, starting stream for selected camera: {source_name}")
            await self.start_image_streaming()
        else:
            LOG.info(f"Entity is OFF, camera selected but not streaming: {source_name}")
        
        return StatusCodes.OK
    
    def _update_remote_state(self) -> None:
        """Update entity state on remote."""
        if not self._api or not self._api.configured_entities.contains(self.id):
            LOG.debug(f"Entity {self.id} not subscribed, skipping state update")
            return
        
        attrs_to_update = {
            Attributes.STATE: self.attributes[Attributes.STATE],
            Attributes.SOURCE: self.attributes[Attributes.SOURCE],
            Attributes.MEDIA_TITLE: self.attributes[Attributes.MEDIA_TITLE],
            Attributes.MEDIA_IMAGE_URL: self.attributes.get(Attributes.MEDIA_IMAGE_URL, ""),
            Attributes.MEDIA_ARTIST: self.attributes.get(Attributes.MEDIA_ARTIST, "Camera View")
        }
        
        self._api.configured_entities.update_attributes(self.id, attrs_to_update)
        LOG.debug(f"Remote state updated: {self.attributes[Attributes.STATE]}")
    
    async def start_image_streaming(self) -> None:
        """Start streaming camera snapshots."""
        LOG.info(f"start_image_streaming called - is_streaming={self.is_streaming}, current_client={self.current_client is not None}")
        
        if self.is_streaming:
            LOG.warning("Already streaming, skipping start")
            return
            
        if not self.current_client:
            LOG.error("No current client available, cannot start streaming")
            return
        
        self.is_streaming = True
        self.stream_task = asyncio.create_task(self._image_stream_loop())
        LOG.info(f"Started snapshot streaming for {self.current_source} (10s refresh)")
    
    async def stop_image_streaming(self) -> None:
        """Stop streaming camera snapshots."""
        LOG.info(f"Stopping image streaming for {self.current_source}")
        self.is_streaming = False
        
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
            self.stream_task = None
        
        LOG.info(f"Stopped snapshot streaming for {self.current_source}")
    
    async def _image_stream_loop(self) -> None:
        """Main loop for updating camera snapshots."""
        LOG.info(f"Image stream loop started for {self.current_source}")
        
        consecutive_failures = 0
        max_failures = 5
        
        while self.is_streaming and self.current_client:
            try:
                if not self.is_on():
                    LOG.info(f"Entity turned OFF during streaming, stopping loop for {self.current_source}")
                    break
                
                LOG.debug(f"Fetching snapshot from {self.current_source}")
                image_data = await self.current_client.get_snapshot()
                
                if image_data:
                    LOG.debug(f"Got snapshot: {len(image_data)} bytes")
                    optimized_image = await self.current_client.optimize_image_for_remote(
                        image_data, 
                        max_size_kb=80
                    )
                    
                    if optimized_image:
                        self.attributes[Attributes.MEDIA_IMAGE_URL] = f"data:image/jpeg;base64,{optimized_image}"
                        self.last_image_update = time.time()
                        
                        self._update_remote_state()
                        
                        consecutive_failures = 0
                        LOG.info(f"Snapshot updated for {self.current_source} ({len(optimized_image)} base64 chars)")
                    else:
                        consecutive_failures += 1
                        LOG.warning(f"Failed to optimize image for {self.current_source} (failure {consecutive_failures}/{max_failures})")
                else:
                    consecutive_failures += 1
                    LOG.warning(f"Failed to get snapshot from {self.current_source} (failure {consecutive_failures}/{max_failures})")
                
                if consecutive_failures >= max_failures:
                    LOG.error(f"Too many consecutive failures for {self.current_source}, marking unavailable but continuing integration")
                    await self._handle_stream_failure()
                    break
                
                LOG.debug(f"Sleeping for {self.refresh_rate} seconds")
                await asyncio.sleep(self.refresh_rate)
                
            except asyncio.CancelledError:
                LOG.info("Stream loop cancelled")
                break
            except Exception as e:
                LOG.error(f"Error in snapshot stream loop for {self.current_source}: {e}", exc_info=True)
                consecutive_failures += 1
                
                if consecutive_failures >= max_failures:
                    await self._handle_stream_failure()
                    break
                
                await asyncio.sleep(5)
        
        LOG.info(f"Image stream loop ended for {self.current_source}")
    
    async def _handle_stream_failure(self) -> None:
        """Handle stream failure."""
        LOG.error(f"Handling stream failure for {self.current_source}")
        self.attributes[Attributes.STATE] = States.UNAVAILABLE
        self.attributes[Attributes.MEDIA_ARTIST] = "Camera Offline"
        self.attributes[Attributes.MEDIA_IMAGE_URL] = ""
        
        self._update_remote_state()
        
        self.is_streaming = False
    
    async def disconnect(self) -> None:
        """Disconnect from all cameras."""
        await self.stop_image_streaming()
        
        for client in self.clients.values():
            await client.close()
        
        LOG.info("Disconnected all cameras")


class CameraEntityFactory:
    """Factory for creating camera entities."""
    
    @staticmethod
    def create_camera_entity(integration: Any, cameras_config: List[Dict[str, Any]]) -> SecurityCameraMediaPlayer:
        """Create a multi-source camera entity."""
        return SecurityCameraMediaPlayer(integration, cameras_config)
    
    @staticmethod
    def validate_cameras_config(cameras_config: List[Dict[str, Any]]) -> tuple[bool, Optional[str]]:
        """Validate cameras configuration."""
        if not cameras_config:
            return False, "At least one camera must be configured"
        
        required_fields = ["name", "snapshot_url"]
        
        for i, config in enumerate(cameras_config):
            for field in required_fields:
                if field not in config or not config[field]:
                    return False, f"Camera {i+1}: Missing required field '{field}'"
            
            url = config["snapshot_url"]
            if not (url.startswith('http://') or url.startswith('https://')):
                return False, f"Camera {i+1}: Invalid URL format"
        
        return True, None