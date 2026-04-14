"""
Unified snapshot client for manual HTTP cameras and Synology Surveillance Station.

H.264 cameras: GetSnapshot API (direct JPEG from Synology).
H.265 cameras: RTSP frame extraction via PyAV (GetLiveViewPath provides auth'd RTSP URL).

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import base64
import io
import json as _json
import logging
import ssl
from typing import Any

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
    SYNOLOGY_ENTRY_API,
)

_LOG = logging.getLogger(__name__)


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
    ) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._synology_sid: str | None = stored_sid or None
        self._otp_code: str | None = otp_code
        self._device_id: str | None = device_id or None
        self._reauth_lock = asyncio.Lock()

    @property
    def session_id(self) -> str | None:
        return self._synology_sid

    @property
    def device_id(self) -> str | None:
        return self._device_id

    async def connect(self) -> bool:
        """Create HTTP session and authenticate if Synology."""
        try:
            connector = aiohttp.TCPConnector(
                limit=5, limit_per_host=2, ssl=_create_ssl_context()
            )
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15, connect=5),
                connector=connector,
            )

            if self._config.source_type == SOURCE_SYNOLOGY:
                if self._synology_sid:
                    if await self._synology_test_sid():
                        _LOG.info("Reusing stored Synology session for %s", self._config.host)
                        return True
                    _LOG.warning("Stored SID expired, re-authenticating")
                    self._synology_sid = None
                return await self._synology_authenticate()

            return True
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
        Synology H.264: GetSnapshot first, RTSP fallback (with re-auth on 401).
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
            url = self._synology_url(SYNOLOGY_ENTRY_API)
            params = {
                "api": "SYNO.SurveillanceStation.Camera",
                "method": "List",
                "version": "9",
                "_sid": self._synology_sid,
            }

            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    _LOG.error("Camera list request failed: HTTP %d", resp.status)
                    return []

                data = await resp.json(content_type=None)
                if not data.get("success"):
                    _LOG.error("Camera list API error: %s", data.get("error"))
                    return []

                cameras_raw = data.get("data", {}).get("cameras", [])
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

    async def _synology_test_sid(self) -> bool:
        """Test if stored SID is still valid."""
        if not self._session or not self._synology_sid:
            return False
        try:
            url = self._synology_url(SYNOLOGY_ENTRY_API)
            params = {
                "api": "SYNO.SurveillanceStation.Camera",
                "method": "List",
                "version": "1",
                "limit": "1",
                "_sid": self._synology_sid,
            }
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json(content_type=None)
                return data.get("success", False)
        except Exception:
            return False

    async def _synology_authenticate(self) -> bool:
        if not self._session:
            return False

        try:
            url = self._synology_url(SYNOLOGY_AUTH_API)
            params = {
                "api": "SYNO.API.Auth",
                "method": "Login",
                "version": "6",
                "account": self._config.username,
                "passwd": self._config.password,
                "session": "SurveillanceStation",
                "enable_device_token": "yes",
                "device_name": "UnfoldedCircle",
            }

            if self._otp_code:
                params["otp_code"] = self._otp_code
            elif self._device_id:
                params["device_id"] = self._device_id

            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    _LOG.error("Synology auth failed: HTTP %d", resp.status)
                    return False

                data = await resp.json(content_type=None)
                if not data.get("success"):
                    error = data.get("error", {})
                    code = error.get("code", 0)
                    _LOG.error("Synology auth error: code %s", code)
                    if code == 403:
                        raise ValueError("2FA is enabled but no OTP code was provided")
                    if code == 400:
                        raise ValueError("Invalid username or password")
                    if code == 401:
                        raise ValueError("Account disabled or locked")
                    if code == 404:
                        raise ValueError("OTP code is incorrect")
                    return False

                resp_data = data["data"]
                self._synology_sid = resp_data["sid"]
                if "did" in resp_data:
                    self._device_id = resp_data["did"]
                    _LOG.debug("Synology device token obtained for %s", self._config.host)
                _LOG.info("Synology authenticated to %s", self._config.host)
                return True

        except ValueError:
            raise
        except Exception as err:
            _LOG.error("Synology authentication failed: %s", err)
            return False

    async def _synology_logout(self) -> None:
        if not self._session or not self._synology_sid:
            return

        url = self._synology_url(SYNOLOGY_AUTH_API)
        params = {
            "api": "SYNO.API.Auth",
            "method": "Logout",
            "version": "6",
            "session": "SurveillanceStation",
            "_sid": self._synology_sid,
        }

        try:
            async with self._session.get(url, params=params):
                pass
        except Exception:
            pass

    async def _try_reauth(self) -> bool:
        """Re-authenticate with Synology when session expires."""
        async with self._reauth_lock:
            if await self._synology_test_sid():
                return True
            _LOG.info("Synology session expired, re-authenticating")
            self._synology_sid = None
            return await self._synology_authenticate()

    async def _synology_get_snapshot(self, camera_id: int) -> bytes | None:
        """Get snapshot via Synology GetSnapshot API (works for H.264 cameras)."""
        if not self._session or not self._synology_sid:
            return None

        data = await self._synology_try_snapshot_api(camera_id)
        if data:
            return data

        if data is False:
            if not await self._try_reauth():
                return None
            data = await self._synology_try_snapshot_api(camera_id)
            if data:
                return data

        data = await self._synology_try_snapshot_api(camera_id, cam_stm=2)
        if data:
            return data

        data = await self._synology_take_snapshot(camera_id)
        if data:
            return data

        return None

    async def _synology_try_snapshot_api(
        self, camera_id: int, cam_stm: int = 1
    ) -> bytes | None | bool:
        """Try the GetSnapshot API. Returns bytes on success, False on auth error, None on other failure."""
        url = self._synology_url(SYNOLOGY_ENTRY_API)
        params = {
            "api": "SYNO.SurveillanceStation.Camera",
            "method": "GetSnapshot",
            "version": "9",
            "cameraId": camera_id,
            "camStm": cam_stm,
            "profileType": 0,
            "_sid": self._synology_sid,
        }

        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    _LOG.debug("GetSnapshot(stm=%d) HTTP %d for camera %d",
                               cam_stm, resp.status, camera_id)
                    return None

                content_type = resp.headers.get("Content-Type", "")
                data = await resp.read()

                if not data:
                    _LOG.debug("GetSnapshot(stm=%d) empty for camera %d", cam_stm, camera_id)
                    return None

                if "json" in content_type:
                    try:
                        err = _json.loads(data)
                        error_code = err.get("error", {}).get("code", 0)
                        _LOG.debug("GetSnapshot(stm=%d) error for camera %d: %s",
                                   cam_stm, camera_id, err)
                        if error_code == 401:
                            return False
                    except Exception:
                        pass
                    return None

                if "image" in content_type or _is_valid_image(data):
                    _LOG.debug("GetSnapshot(stm=%d) success for camera %d: %d bytes",
                               cam_stm, camera_id, len(data))
                    return data

                _LOG.debug("GetSnapshot(stm=%d) invalid data for camera %d: %d bytes, type=%s",
                           cam_stm, camera_id, len(data), content_type)
                return None

        except Exception as err:
            _LOG.debug("GetSnapshot(stm=%d) exception for camera %d: %s", cam_stm, camera_id, err)
            return None

    async def _synology_take_snapshot(self, camera_id: int) -> bytes | None:
        """Two-step snapshot: TakeSnapshot then LoadSnapshot."""
        if not self._session or not self._synology_sid:
            return None

        url = self._synology_url(SYNOLOGY_ENTRY_API)

        take_params = {
            "api": "SYNO.SurveillanceStation.SnapShot",
            "method": "TakeSnapshot",
            "version": "1",
            "camId": camera_id,
            "blSave": "false",
            "dsId": 0,
            "_sid": self._synology_sid,
        }

        try:
            async with self._session.get(url, params=take_params) as resp:
                if resp.status != 200:
                    _LOG.debug("TakeSnapshot HTTP %d for camera %d", resp.status, camera_id)
                    return None

                result = await resp.json(content_type=None)
                if not result.get("success"):
                    _LOG.debug("TakeSnapshot failed for camera %d: %s",
                               camera_id, result.get("error"))
                    return None

                snapshot_data = result.get("data", {})
                snapshot_id = snapshot_data.get("id")
                if not snapshot_id:
                    _LOG.debug("TakeSnapshot no ID for camera %d", camera_id)
                    return None

        except Exception as err:
            _LOG.debug("TakeSnapshot exception for camera %d: %s", camera_id, err)
            return None

        load_params = {
            "api": "SYNO.SurveillanceStation.SnapShot",
            "method": "LoadSnapshot",
            "version": "1",
            "id": snapshot_id,
            "imgSize": 0,
            "_sid": self._synology_sid,
        }

        try:
            async with self._session.get(url, params=load_params) as resp:
                if resp.status != 200:
                    _LOG.debug("LoadSnapshot HTTP %d for camera %d", resp.status, camera_id)
                    return None

                data = await resp.read()
                if data and _is_valid_image(data):
                    _LOG.debug("TakeSnapshot+Load success for camera %d: %d bytes",
                               camera_id, len(data))
                    return data

                _LOG.debug("LoadSnapshot invalid data for camera %d", camera_id)
                return None

        except Exception as err:
            _LOG.debug("LoadSnapshot exception for camera %d: %s", camera_id, err)
            return None

    # --- RTSP Frame Extraction (H.265 cameras) ---

    async def _get_rtsp_for_camera_id(self, camera_id: int) -> str | None:
        """Get RTSP URL for a camera via GetLiveViewPath API."""
        if not self._session or not self._synology_sid:
            return None
        try:
            url = self._synology_url(SYNOLOGY_ENTRY_API)
            params = {
                "api": "SYNO.SurveillanceStation.Camera",
                "method": "GetLiveViewPath",
                "version": "9",
                "idList": str(camera_id),
                "_sid": self._synology_sid,
            }
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                if not data.get("success"):
                    return None
                for p in data.get("data", []):
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
