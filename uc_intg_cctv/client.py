"""
Unified snapshot client for manual HTTP cameras and Synology Surveillance Station.

H.264 cameras: GetSnapshot API (direct JPEG from Synology).
H.265 cameras: RTSP frame extraction via PyAV (GetLiveViewPath provides auth'd RTSP URL).

Session recovery mirrors the MiyaraHub synology-manager mobile app: every Synology
call runs through a single choke point that silently re-authenticates on session-expiry
codes and retries once, uses a persisted device token to skip 2FA on re-login, sends the
SynoToken on every request, and treats auto-block/locked codes as terminal (no retry).

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import base64
import io
import json as _json
import logging
import ssl
from typing import Any, Callable

import aiohttp
import av
from PIL import Image

from uc_intg_cctv.const import (
    CODEC_H265,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    MAX_IMAGE_SIZE_KB,
    SOURCE_SYNOLOGY,
    SYNOLOGY_AUTH_API,
    SYNOLOGY_AUTH_VERSION,
    SYNOLOGY_AUTH_VERSION_FALLBACK,
    SYNOLOGY_DEVICE_NAME,
    SYNOLOGY_DEVICE_TOKEN_FLOOR,
    SYNOLOGY_ENTRY_API,
    SYNOLOGY_QUERY_API,
    SYNOLOGY_REAUTH_CODES,
    SYNOLOGY_TERMINAL_CODES,
)

_LOG = logging.getLogger(__name__)


class SynologyError(Exception):
    """A Synology API call returned success=false with an error code."""

    def __init__(self, code: int, message: str = "") -> None:
        self.code = code
        super().__init__(f"Synology API error {code}: {message}" if message else f"Synology API error {code}")


def _create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def optimize_image(data: bytes, max_size_kb: int = MAX_IMAGE_SIZE_KB) -> str | None:
    """Resize and compress image to fit remote display, return as base64 data URI."""
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")

        for quality in range(85, 15, -10):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= max_size_kb * 1024:
                break

        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as err:
        _LOG.error("Image optimization failed: %s", err)
        return None


def _is_valid_image(data: bytes) -> bool:
    if not data or len(data) < 100:
        return False
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"


class CCTVClient:
    """Unified client for fetching camera snapshots from manual URLs or Synology NAS."""

    def __init__(
        self,
        config: Any,
        otp_code: str | None = None,
        stored_sid: str | None = None,
        device_id: str | None = None,
        stored_syno_token: str | None = None,
        on_auth: Callable[[str, str | None, str | None], None] | None = None,
    ) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._synology_sid: str | None = stored_sid or None
        self._synology_syno_token: str | None = stored_syno_token or None
        self._otp_code: str | None = otp_code
        self._device_id: str | None = device_id or None
        self._on_auth = on_auth
        self._auth_version: int | None = None
        self._reauth_lock = asyncio.Lock()
        self._last_error_terminal: bool = False

    @property
    def session_id(self) -> str | None:
        return self._synology_sid

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def syno_token(self) -> str | None:
        return self._synology_syno_token

    @property
    def last_error_terminal(self) -> bool:
        """True when the last auth failure was an auto-block/locked account (do not hammer)."""
        return self._last_error_terminal

    async def connect(self) -> bool:
        """Create HTTP session and authenticate if Synology."""
        try:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=5, limit_per_host=2, ssl=_create_ssl_context()
                )
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=15, connect=5),
                    connector=connector,
                )

            if self._config.source_type == SOURCE_SYNOLOGY:
                if self._synology_sid and await self._synology_test_sid():
                    _LOG.info("Reusing stored Synology session for %s", self._config.host)
                    self._notify_auth()
                    return True
                if self._synology_sid:
                    _LOG.warning("Stored SID expired, re-authenticating")
                self._synology_sid = None
                return await self._synology_authenticate()

            return True
        except ValueError:
            raise
        except Exception as err:
            _LOG.error("Client connect failed: %s", err)
            return False

    async def close(self, logout: bool = True) -> None:
        """Close session and optionally logout from Synology."""
        if logout and self._synology_sid and self._session:
            try:
                await self._synology_logout()
            except Exception:
                pass
            self._synology_sid = None

        if self._session:
            await self._session.close()
            self._session = None

    async def get_snapshot(self, camera: dict) -> bytes | None:
        """Fetch snapshot for a camera entry.

        Synology H.265: RTSP first, GetSnapshot fallback.
        Synology H.264: GetSnapshot first, RTSP fallback.
        Manual: HTTP GET to snapshot URL.
        """
        if not self._session:
            return None

        if self._config.source_type == SOURCE_SYNOLOGY:
            camera_id = camera.get("id", 0)
            video_codec = camera.get("video_codec", 0)

            if video_codec == CODEC_H265:
                data = await self._rtsp_frame_grab(camera_id)
                if data:
                    return data
                _LOG.debug("RTSP failed for H.265 camera %d, trying GetSnapshot fallback", camera_id)
                return await self._synology_get_snapshot(camera_id)

            data = await self._synology_get_snapshot(camera_id)
            if data:
                return data

            _LOG.debug("GetSnapshot failed for H.264 camera %d, trying RTSP fallback", camera_id)
            return await self._rtsp_frame_grab(camera_id)

        return await self._http_get_snapshot(camera.get("url", ""))

    async def discover_cameras(self) -> list[dict]:
        """Discover cameras from Synology Surveillance Station (v9 for codec info)."""
        if not self._session or not self._synology_sid:
            return []

        try:
            data = await self._synology_json(
                "SYNO.SurveillanceStation.Camera",
                "List",
                9,
                {},
            )
            cameras_raw = data.get("cameras", [])
            cameras = []
            for cam in cameras_raw:
                cameras.append({
                    "id": cam.get("id"),
                    "name": cam.get("newName", cam.get("name", f"Camera {cam.get('id')}")),
                    "status": cam.get("status", 0),
                    "model": cam.get("model", ""),
                    "video_codec": cam.get("videoCodec", 0),
                })

            _LOG.info("Discovered %d cameras from Synology", len(cameras))
            return cameras

        except Exception as err:
            _LOG.error("Camera discovery failed: %s", err)
            return []

    # --- Manual HTTP ---

    async def _http_get_snapshot(self, url: str) -> bytes | None:
        if not url or not self._session:
            return None
        try:
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    _LOG.warning("HTTP %d from %s", resp.status, url)
                    return None
                data = await resp.read()
                if _is_valid_image(data):
                    return data
                _LOG.warning("Invalid image from %s", url)
                return None
        except Exception as err:
            _LOG.warning("Snapshot fetch failed for %s: %s", url, err)
            return None

    # --- Synology API ---

    def _synology_url(self, path: str) -> str:
        scheme = "https" if self._config.use_https else "http"
        return f"{scheme}://{self._config.host}:{self._config.port}{path}"

    def _auth_headers(self) -> dict[str, str]:
        if self._synology_syno_token:
            return {"X-SYNO-TOKEN": self._synology_syno_token}
        return {}

    def _session_params(self, base: dict[str, Any]) -> dict[str, Any]:
        params = dict(base)
        if self._synology_sid:
            params["_sid"] = self._synology_sid
        if self._synology_syno_token:
            params["SynoToken"] = self._synology_syno_token
        return params

    def _notify_auth(self) -> None:
        if self._on_auth:
            try:
                self._on_auth(self._synology_sid, self._device_id, self._synology_syno_token)
            except Exception as err:
                _LOG.debug("on_auth callback failed: %s", err)

    async def _negotiate_auth_version(self) -> int:
        """Query SYNO.API.Info for the server-supported SYNO.API.Auth version."""
        if not self._session:
            return SYNOLOGY_AUTH_VERSION_FALLBACK
        try:
            url = self._synology_url(SYNOLOGY_QUERY_API)
            params = {
                "api": "SYNO.API.Info",
                "method": "query",
                "version": "1",
                "query": "SYNO.API.Auth",
            }
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return SYNOLOGY_AUTH_VERSION_FALLBACK
                data = await resp.json(content_type=None)
            auth = data.get("data", {}).get("SYNO.API.Auth", {})
            max_version = auth.get("maxVersion")
            min_version = auth.get("minVersion")
            if not isinstance(max_version, int):
                return SYNOLOGY_AUTH_VERSION_FALLBACK
            version = min(SYNOLOGY_AUTH_VERSION, max_version)
            if isinstance(min_version, int) and version < min_version:
                version = min_version
            if max_version >= SYNOLOGY_DEVICE_TOKEN_FLOOR and version < SYNOLOGY_DEVICE_TOKEN_FLOOR:
                version = SYNOLOGY_DEVICE_TOKEN_FLOOR
            version = min(version, max_version)
            _LOG.info("Negotiated SYNO.API.Auth v%d (server min=%s max=%s)",
                      version, min_version, max_version)
            return max(version, 1)
        except Exception as err:
            _LOG.debug("Auth version negotiation failed: %s, using v%d",
                       err, SYNOLOGY_AUTH_VERSION_FALLBACK)
            return SYNOLOGY_AUTH_VERSION_FALLBACK

    async def _synology_test_sid(self) -> bool:
        """Test if stored SID is still valid."""
        if not self._session or not self._synology_sid:
            return False
        try:
            data = await self._synology_json(
                "SYNO.SurveillanceStation.Camera",
                "List",
                1,
                {"limit": "1"},
                allow_reauth=False,
            )
            return data is not None
        except Exception:
            return False

    async def _synology_authenticate(self) -> bool:
        if not self._session:
            return False

        if self._auth_version is None:
            self._auth_version = await self._negotiate_auth_version()

        url = self._synology_url(SYNOLOGY_AUTH_API)
        params = {
            "api": "SYNO.API.Auth",
            "method": "login",
            "version": str(self._auth_version),
            "account": self._config.username,
            "passwd": self._config.password,
            "session": "SurveillanceStation",
            "format": "sid",
            "enable_device_token": "yes",
            "enable_syno_token": "yes",
            "device_name": SYNOLOGY_DEVICE_NAME,
        }

        if self._otp_code:
            params["otp_code"] = self._otp_code
        if self._device_id:
            params["device_id"] = self._device_id

        async with self._session.get(url, params=params) as resp:
            if resp.status != 200:
                _LOG.error("Synology auth failed: HTTP %d", resp.status)
                raise SynologyError(0, f"HTTP {resp.status}")

            data = await resp.json(content_type=None)

        if not data.get("success"):
            code = data.get("error", {}).get("code", 0)
            self._last_error_terminal = code in SYNOLOGY_TERMINAL_CODES
            _LOG.error("Synology auth error: code %s", code)
            if code == 403:
                raise ValueError("2FA is enabled but no OTP code was provided")
            if code == 404:
                raise ValueError("OTP code is incorrect")
            if code == 400:
                raise ValueError("Invalid username or password")
            if code in (401, 411):
                raise ValueError("Account disabled or locked")
            if code == 407:
                raise ValueError(
                    "Too many failed attempts - DSM temporarily blocked this device. "
                    "Wait for the block to clear or unblock it in DSM."
                )
            raise SynologyError(code)

        resp_data = data["data"]
        self._synology_sid = resp_data["sid"]
        did = resp_data.get("did") or resp_data.get("device_id")
        if did:
            self._device_id = did
        syno_token = resp_data.get("synotoken")
        if syno_token is not None:
            self._synology_syno_token = syno_token
        self._last_error_terminal = False
        _LOG.info("Synology authenticated to %s", self._config.host)
        self._notify_auth()
        return True

    async def _synology_logout(self) -> None:
        if not self._session or not self._synology_sid:
            return

        url = self._synology_url(SYNOLOGY_AUTH_API)
        params = self._session_params({
            "api": "SYNO.API.Auth",
            "method": "logout",
            "version": str(self._auth_version or SYNOLOGY_AUTH_VERSION_FALLBACK),
            "session": "SurveillanceStation",
        })

        try:
            async with self._session.get(url, params=params, headers=self._auth_headers()):
                pass
        except Exception:
            pass

    async def _reauth(self, stale_sid: str | None) -> bool:
        """Re-authenticate when the session expires. Single-flight via the reauth lock."""
        async with self._reauth_lock:
            if self._synology_sid and self._synology_sid != stale_sid:
                return True
            _LOG.info("Synology session expired, re-authenticating")
            self._synology_sid = None
            try:
                return await self._synology_authenticate()
            except (ValueError, SynologyError) as err:
                _LOG.warning("Re-authentication failed: %s", err)
                return False

    async def _synology_json(
        self,
        api: str,
        method: str,
        version: int,
        params: dict[str, Any],
        *,
        allow_reauth: bool = True,
        _retrying: bool = False,
    ) -> dict[str, Any]:
        """JSON Synology API call funnelled through the single session-recovery choke point.

        Returns the ``data`` object on success. Raises SynologyError on failure (after one
        silent re-login + retry for session-expiry codes).
        """
        if not self._session:
            raise SynologyError(0, "No HTTP session")

        stale_sid = self._synology_sid
        url = self._synology_url(SYNOLOGY_ENTRY_API)
        query = self._session_params({
            "api": api,
            "method": method,
            "version": str(version),
        })
        query.update(params)

        async with self._session.get(url, params=query, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise SynologyError(0, f"HTTP {resp.status}")
            data = await resp.json(content_type=None)

        if data.get("success"):
            return data.get("data", {}) or {}

        code = data.get("error", {}).get("code", 0)
        if code in SYNOLOGY_TERMINAL_CODES:
            self._last_error_terminal = True
        if (
            allow_reauth
            and not _retrying
            and code in SYNOLOGY_REAUTH_CODES
            and await self._reauth(stale_sid)
        ):
            return await self._synology_json(
                api, method, version, params, allow_reauth=True, _retrying=True
            )
        raise SynologyError(code)

    async def _synology_binary(
        self,
        api: str,
        method: str,
        version: int,
        params: dict[str, Any],
        *,
        _retrying: bool = False,
    ) -> bytes | None:
        """Binary (image) Synology API call with the same session-recovery choke point."""
        if not self._session:
            return None

        stale_sid = self._synology_sid
        url = self._synology_url(SYNOLOGY_ENTRY_API)
        query = self._session_params({
            "api": api,
            "method": method,
            "version": str(version),
        })
        query.update(params)

        try:
            async with self._session.get(url, params=query, headers=self._auth_headers()) as resp:
                if resp.status != 200:
                    _LOG.debug("%s.%s HTTP %d", api, method, resp.status)
                    return None
                content_type = resp.headers.get("Content-Type", "")
                data = await resp.read()
        except Exception as err:
            _LOG.debug("%s.%s exception: %s", api, method, err)
            return None

        if not data:
            return None

        if "json" in content_type:
            code = 0
            try:
                code = _json.loads(data).get("error", {}).get("code", 0)
            except Exception:
                pass
            if code in SYNOLOGY_TERMINAL_CODES:
                self._last_error_terminal = True
            if not _retrying and code in SYNOLOGY_REAUTH_CODES and await self._reauth(stale_sid):
                return await self._synology_binary(api, method, version, params, _retrying=True)
            _LOG.debug("%s.%s error code %s", api, method, code)
            return None

        if "image" in content_type or _is_valid_image(data):
            return data

        _LOG.debug("%s.%s invalid data (%d bytes, type=%s)", api, method, len(data), content_type)
        return None

    async def _synology_get_snapshot(self, camera_id: int) -> bytes | None:
        """Get snapshot via GetSnapshot API, falling back to a lower stream then TakeSnapshot."""
        if not self._session or not self._synology_sid:
            return None

        for cam_stm in (1, 2):
            data = await self._synology_binary(
                "SYNO.SurveillanceStation.Camera",
                "GetSnapshot",
                9,
                {"cameraId": camera_id, "camStm": cam_stm, "profileType": 0},
            )
            if data:
                _LOG.debug("GetSnapshot(stm=%d) success for camera %d: %d bytes",
                           cam_stm, camera_id, len(data))
                return data

        return await self._synology_take_snapshot(camera_id)

    async def _synology_take_snapshot(self, camera_id: int) -> bytes | None:
        """Two-step snapshot: TakeSnapshot then LoadSnapshot."""
        if not self._session or not self._synology_sid:
            return None

        try:
            result = await self._synology_json(
                "SYNO.SurveillanceStation.SnapShot",
                "TakeSnapshot",
                1,
                {"camId": camera_id, "blSave": "false", "dsId": 0},
            )
        except SynologyError as err:
            _LOG.debug("TakeSnapshot failed for camera %d: %s", camera_id, err)
            return None

        snapshot_id = result.get("id")
        if not snapshot_id:
            _LOG.debug("TakeSnapshot no ID for camera %d", camera_id)
            return None

        data = await self._synology_binary(
            "SYNO.SurveillanceStation.SnapShot",
            "LoadSnapshot",
            1,
            {"id": snapshot_id, "imgSize": 0},
        )
        if data:
            _LOG.debug("TakeSnapshot+Load success for camera %d: %d bytes", camera_id, len(data))
        return data

    # --- RTSP Frame Extraction (H.265 cameras) ---

    async def _get_rtsp_for_camera_id(self, camera_id: int) -> str | None:
        """Get RTSP URL for a camera via GetLiveViewPath API."""
        if not self._session or not self._synology_sid:
            return None
        try:
            data = await self._synology_json(
                "SYNO.SurveillanceStation.Camera",
                "GetLiveViewPath",
                9,
                {"idList": str(camera_id)},
            )
            paths = data.get("_list") if isinstance(data, dict) else None
            if paths is None and isinstance(data, list):
                paths = data
            for p in paths or []:
                rtsp = p.get("rtspPath", "")
                if rtsp:
                    return rtsp
        except Exception as err:
            _LOG.debug("GetLiveViewPath failed for camera %d: %s", camera_id, err)
        return None

    async def _rtsp_frame_grab(self, camera_id: int) -> bytes | None:
        """Extract a single JPEG frame from RTSP stream via PyAV."""
        rtsp_url = await self._get_rtsp_for_camera_id(camera_id)
        if not rtsp_url:
            _LOG.debug("No RTSP URL for camera %d", camera_id)
            return None

        loop = asyncio.get_event_loop()
        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(None, self._rtsp_grab_sync, rtsp_url, camera_id),
                timeout=15,
            )
            return data
        except asyncio.TimeoutError:
            _LOG.debug("RTSP frame grab timeout for camera %d", camera_id)
            return None
        except Exception as err:
            _LOG.debug("RTSP frame grab failed for camera %d: %s", camera_id, err)
            return None

    @staticmethod
    def _rtsp_grab_sync(rtsp_url: str, camera_id: int) -> bytes | None:
        """Synchronous RTSP frame grab using PyAV (runs in executor)."""
        container = None
        try:
            container = av.open(
                rtsp_url,
                options={"rtsp_transport": "tcp", "stimeout": "10000000"},
            )
            for frame in container.decode(video=0):
                pil_image = frame.to_image()
                buf = io.BytesIO()
                pil_image.save(buf, format="JPEG", quality=85)
                jpeg_bytes = buf.getvalue()
                _LOG.debug("RTSP frame grab success for camera %d: %d bytes", camera_id, len(jpeg_bytes))
                return jpeg_bytes
            _LOG.debug("RTSP stream yielded no frames for camera %d", camera_id)
            return None
        except Exception as err:
            _LOG.debug("RTSP grab error for camera %d: %s", camera_id, err)
            return None
        finally:
            if container:
                container.close()
