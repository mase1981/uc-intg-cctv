"""
CCTV device implementation using PollingDevice.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi_framework import DeviceEvents, PollingDevice

from uc_intg_cctv.client import CCTVClient, optimize_image
from uc_intg_cctv.config import CCTVConfig
from uc_intg_cctv.const import MAX_CONSECUTIVE_FAILURES

_LOG = logging.getLogger(__name__)


RECONNECT_INTERVAL = 30


class CCTVDevice(PollingDevice):
    """Security camera device using polling for snapshot refresh."""

    def __init__(self, device_config: CCTVConfig, **kwargs: Any) -> None:
        super().__init__(device_config, poll_interval=device_config.refresh_rate, **kwargs)
        self._config = device_config
        self._client: CCTVClient | None = None
        self._state: str = "UNAVAILABLE"
        self._streaming: bool = False
        self._current_camera_index: int = 0
        self._snapshot_base64: str = ""
        self._camera_names: list[str] = [c.get("name", "") for c in device_config.cameras]
        self._consecutive_failures: int = 0
        self._reconnect_poll_count: int = 0
        self._was_streaming: bool = False

    @property
    def identifier(self) -> str:
        return self._config.identifier

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def address(self) -> str:
        return self._config.host or "manual"

    @property
    def log_id(self) -> str:
        return f"[{self.name}]"

    @property
    def state(self) -> str:
        return self._state

    @property
    def camera_names(self) -> list[str]:
        return self._camera_names

    @property
    def current_camera_index(self) -> int:
        return self._current_camera_index

    @property
    def current_camera_name(self) -> str:
        if 0 <= self._current_camera_index < len(self._camera_names):
            return self._camera_names[self._current_camera_index]
        return ""

    @property
    def snapshot_base64(self) -> str:
        return self._snapshot_base64

    @property
    def streaming(self) -> bool:
        return self._streaming

    async def establish_connection(self) -> CCTVClient:
        """Connect to camera source (validate manual URLs or authenticate Synology)."""
        stored_sid = self._config.synology_sid if self._config.source_type == "synology" else None
        device_id = self._config.synology_device_id if self._config.source_type == "synology" else None
        self._client = CCTVClient(self._config, stored_sid=stored_sid, device_id=device_id)
        if not await self._client.connect():
            await self._client.close()
            self._client = None
            raise ConnectionError(f"Cannot connect to {self._config.source_type} camera source")

        if self._config.source_type == "synology":
            if self._client.session_id:
                self._config.synology_sid = self._client.session_id
            if self._client.device_id:
                self._config.synology_device_id = self._client.device_id

        _LOG.info("%s Connected to %s source with %d cameras",
                  self.log_id, self._config.source_type, len(self._camera_names))

        self._state = "ON"
        self._consecutive_failures = 0
        self.push_update()
        return self._client

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect to the camera source."""
        _LOG.info("%s Attempting reconnection", self.log_id)
        if self._client:
            try:
                await self._client.close(logout=False)
            except Exception:
                pass
            self._client = None

        try:
            await self.establish_connection()
            _LOG.info("%s Reconnected successfully", self.log_id)
            if self._was_streaming:
                await self.start_streaming()
            return True
        except Exception as err:
            _LOG.warning("%s Reconnection failed: %s", self.log_id, err)
            return False

    async def poll_device(self) -> None:
        """Fetch snapshot for current camera if streaming is active."""
        if self._state == "UNAVAILABLE":
            self._reconnect_poll_count += 1
            polls_needed = RECONNECT_INTERVAL // max(self._config.refresh_rate, 1)
            if self._reconnect_poll_count >= max(polls_needed, 3):
                self._reconnect_poll_count = 0
                await self._try_reconnect()
            return

        if not self._client:
            return

        if not self._streaming:
            self.push_update()
            return

        cameras = self._config.cameras
        if not cameras or self._current_camera_index >= len(cameras):
            return

        camera = cameras[self._current_camera_index]
        snapshot_data = await self._client.get_snapshot(camera)

        if snapshot_data:
            optimized = optimize_image(snapshot_data)
            if optimized:
                self._snapshot_base64 = optimized
                self._consecutive_failures = 0
                self.push_update()
                return

        self._consecutive_failures += 1
        _LOG.warning("%s Snapshot failure %d/%d for %s",
                     self.log_id, self._consecutive_failures, MAX_CONSECUTIVE_FAILURES,
                     self.current_camera_name)

        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            _LOG.error("%s Max failures reached, will attempt reconnection", self.log_id)
            self._was_streaming = self._streaming
            self._state = "UNAVAILABLE"
            self._streaming = False
            self._snapshot_base64 = ""
            self._reconnect_poll_count = 0
            self.push_update()

    async def start_streaming(self) -> None:
        """Start fetching snapshots on each poll cycle."""
        self._streaming = True
        self._state = "PLAYING"
        self._consecutive_failures = 0
        self._snapshot_base64 = ""
        _LOG.info("%s Started streaming camera: %s", self.log_id, self.current_camera_name)
        await self.poll_device()

    async def stop_streaming(self) -> None:
        """Stop fetching snapshots."""
        self._streaming = False
        self._state = "ON"
        self._snapshot_base64 = ""
        _LOG.info("%s Stopped streaming", self.log_id)
        self.push_update()

    async def select_camera(self, index: int) -> None:
        """Switch to a different camera by index."""
        if 0 <= index < len(self._camera_names):
            self._current_camera_index = index
            self._consecutive_failures = 0
            self._snapshot_base64 = ""
            _LOG.info("%s Switched to camera: %s", self.log_id, self.current_camera_name)
            if self._streaming:
                await self.poll_device()
            else:
                self.push_update()

    async def disconnect(self) -> None:
        """Disconnect from camera source. Keep Synology session alive for reconnection."""
        self._was_streaming = self._streaming
        self._streaming = False
        self._snapshot_base64 = ""
        if self._client:
            await self._client.close(logout=False)
            self._client = None
        self._state = "UNAVAILABLE"
        await super().disconnect()
