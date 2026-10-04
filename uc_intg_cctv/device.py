"""
CCTV device implementation using PollingDevice.

Connecting never raises: the framework does not retry a connect that raised, so a
Remote waking before its Wi-Fi is back (or a NAS still booting) used to leave the
cameras unavailable until the next reboot. Instead the device stays UNAVAILABLE
and the poll loop reconnects with backoff. A login DSM rejects (password, 2FA,
disabled account) is not retried at all: every failed login counts towards DSM's
auto-block. Running setup again (Update) fixes it without removing anything.
While idle, a keep-alive every few minutes keeps the Synology session warm.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import time
from typing import Any

from ucapi_framework import PollingDevice

from uc_intg_cctv.client import CCTVClient, CredentialError, optimize_image
from uc_intg_cctv.config import CCTVConfig
from uc_intg_cctv.const import MAX_CONSECUTIVE_FAILURES

_LOG = logging.getLogger(__name__)


RECONNECT_MIN = 30
RECONNECT_MAX = 600
STARTUP_ATTEMPTS = 3  # the Remote's Wi-Fi may still be coming back after standby
STARTUP_RETRY_DELAY = 5.0
KEEPALIVE_INTERVAL = 300  # seconds between Synology keep-alives while not streaming


class CCTVDevice(PollingDevice):
    """Security camera device using polling for snapshot refresh."""

    def __init__(self, device_config: CCTVConfig, **kwargs: Any) -> None:
        super().__init__(device_config, poll_interval=device_config.refresh_rate, **kwargs)
        self._config = device_config
        self._client: CCTVClient | None = None
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._state: str = "UNAVAILABLE"
        self._streaming: bool = False
        self._snapshot_lock = asyncio.Lock()  # one snapshot fetch at a time
        self._current_camera_index: int = 0
        self._snapshot_base64: str = ""
        self._camera_names: list[str] = [c.get("name", "") for c in device_config.cameras]
        self._consecutive_failures: int = 0
        self._reconnect_poll_count: int = 0
        self._reconnect_delay: int = RECONNECT_MIN
        self._last_auth_terminal: bool = False
        self._was_streaming: bool = False
        self._needs_setup: str = ""  # why DSM rejected the login (setup > Update fixes it)
        self._last_keepalive: float = time.monotonic()

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

    @property
    def needs_setup(self) -> str:
        return self._needs_setup

    def _persist_auth(self, sid: str | None, device_id: str | None, syno_token: str | None) -> None:
        """Persist refreshed Synology credentials to disk so they survive reboots."""
        if self._config.source_type != "synology":
            return
        changes: dict[str, str] = {}
        if sid and sid != self._config.synology_sid:
            changes["synology_sid"] = sid
        if device_id and device_id != self._config.synology_device_id:
            changes["synology_device_id"] = device_id
        if (syno_token or "") != self._config.synology_syno_token:
            changes["synology_syno_token"] = syno_token or ""
        if not changes:
            return
        try:
            self.update_config(**changes)
        except Exception as err:
            _LOG.warning("%s Failed to persist Synology credentials: %s", self.log_id, err)

    async def establish_connection(self) -> CCTVClient | None:
        """Connect to the camera source; never raises (see module docstring)."""
        for attempt in range(1, STARTUP_ATTEMPTS + 1):
            if await self._connect_once():
                break
            if self._needs_setup or self._last_auth_terminal or attempt == STARTUP_ATTEMPTS:
                break
            await asyncio.sleep(STARTUP_RETRY_DELAY)
        self.push_update()
        return self._client

    async def _connect_once(self) -> bool:
        """One connect attempt (validate manual URLs or log in to Synology). Returns success.

        Concurrent-safe (the framework may call connect twice): one client per device,
        guarded by the connect lock.
        """
        async with self._connect_lock:
            if self._client is None:
                synology = self._config.source_type == "synology"
                self._client = CCTVClient(
                    self._config,
                    stored_sid=self._config.synology_sid if synology else None,
                    device_id=self._config.synology_device_id if synology else None,
                    stored_syno_token=self._config.synology_syno_token if synology else None,
                    on_auth=self._persist_auth,
                )

            try:
                connected = await self._client.connect()
            except CredentialError as err:
                self._set_needs_setup(str(err))
                connected = False
            except ValueError as err:  # e.g. DSM auto-blocked this device
                _LOG.error("%s %s", self.log_id, err)
                connected = False

            if not connected:
                self._last_auth_terminal = self._client.last_error_terminal
                await self._client.close(logout=False)
                self._client = None
                self._state = "UNAVAILABLE"
                return False

            self._last_auth_terminal = False
            self._needs_setup = ""
            if self._config.source_type == "synology":
                self._persist_auth(
                    self._client.session_id, self._client.device_id, self._client.syno_token
                )

            _LOG.info("%s Connected to %s source with %d cameras",
                      self.log_id, self._config.source_type, len(self._camera_names))

            self._state = "ON"
            self._consecutive_failures = 0
            self._reconnect_delay = RECONNECT_MIN
            self._last_keepalive = time.monotonic()
            self.push_update()
            return True

    def _set_needs_setup(self, reason: str) -> None:
        if self._needs_setup != reason:
            _LOG.error(
                "%s DSM rejected the login: %s. Automatic retries are paused so DSM does not "
                "block this Remote. Fix it by running the integration setup again and choosing "
                "Update (no need to remove the integration).",
                self.log_id, reason,
            )
        self._needs_setup = reason
        self._state = "UNAVAILABLE"
        self._streaming = False

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect to the camera source."""
        _LOG.info("%s Attempting reconnection", self.log_id)
        if await self._connect_once():
            _LOG.info("%s Reconnected successfully", self.log_id)
            if self._was_streaming:
                self._was_streaming = False
                await self.start_streaming()
            return True
        _LOG.warning("%s Reconnection failed", self.log_id)
        return False

    async def poll_device(self) -> None:
        """Fetch snapshot for current camera if streaming is active."""
        if self._state == "UNAVAILABLE":
            if self._needs_setup:
                return  # waiting for setup > Update; retrying would risk a DSM auto-block
            self._reconnect_poll_count += 1
            polls_needed = max(self._reconnect_delay // max(self._config.refresh_rate, 1), 3)
            if self._reconnect_poll_count >= polls_needed:
                self._reconnect_poll_count = 0
                if await self._try_reconnect():
                    self._reconnect_delay = RECONNECT_MIN
                elif self._last_auth_terminal:
                    _LOG.error("%s DSM blocked/locked this device; backing off %ds",
                               self.log_id, RECONNECT_MAX)
                    self._reconnect_delay = RECONNECT_MAX
                else:
                    self._reconnect_delay = min(self._reconnect_delay * 2, RECONNECT_MAX)
            return

        if not self._client:
            return

        if not self._streaming:
            await self._keep_alive()
            self.push_update()
            return

        cameras = self._config.cameras
        if not cameras or self._current_camera_index >= len(cameras):
            return

        # A camera switch also fetches right away; don't run a second fetch next to the poll's.
        if self._snapshot_lock.locked():
            return
        async with self._snapshot_lock:
            index = self._current_camera_index
            snapshot_data = await self._client.get_snapshot(cameras[index])
            if index != self._current_camera_index:
                return  # the user switched camera meanwhile; the next poll fetches the new one
            if not snapshot_data and self._client and self._client.rtsp_busy:
                return  # an earlier frame grab is still finishing: not a failure, try next poll
            await self._handle_snapshot(snapshot_data)

    async def _handle_snapshot(self, snapshot_data: bytes | None) -> None:
        if self._client and self._client.credential_error:
            self._set_needs_setup(str(self._client.credential_error))
            self._snapshot_base64 = ""
            self.push_update()
            return

        if snapshot_data:
            # Image decoding/resizing is CPU work: keep it off the event loop so the
            # connection to the Remote stays responsive.
            optimized = await asyncio.to_thread(optimize_image, snapshot_data)
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

    async def _keep_alive(self) -> None:
        """Keep the Synology session warm while nobody is watching (silent re-login if needed)."""
        if self._config.source_type != "synology" or not self._client:
            return
        if time.monotonic() - self._last_keepalive < KEEPALIVE_INTERVAL:
            return
        self._last_keepalive = time.monotonic()
        if await self._client.keep_alive():
            return
        if self._client.credential_error:
            self._set_needs_setup(str(self._client.credential_error))
        else:
            _LOG.warning("%s Keep-alive failed, will reconnect", self.log_id)
            self._state = "UNAVAILABLE"
            self._reconnect_poll_count = 0

    async def start_streaming(self) -> bool:
        """Start fetching snapshots on each poll cycle. Returns False if the source is unavailable."""
        if self._client is None or self._state == "UNAVAILABLE":
            # Pressing play is the best moment to reconnect (unless DSM rejected the login).
            if self._needs_setup or not await self._try_reconnect():
                self.push_update()
                return False
        self._streaming = True
        self._state = "PLAYING"
        self._consecutive_failures = 0
        self._snapshot_base64 = ""
        _LOG.info("%s Started streaming camera: %s", self.log_id, self.current_camera_name)
        await self.poll_device()
        return True

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
        async with self._connect_lock:
            if self._client:
                await self._client.close(logout=False)
                self._client = None
        self._state = "UNAVAILABLE"
        await super().disconnect()
