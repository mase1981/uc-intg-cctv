"""
CCTV setup flow for manual URLs and Synology Surveillance Station.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import RequestUserInput
from ucapi_framework import BaseSetupFlow

from uc_intg_cctv.client import CCTVClient
from uc_intg_cctv.config import CCTVConfig
from uc_intg_cctv.const import (
    DEFAULT_REFRESH_RATE,
    SOURCE_MANUAL,
    SOURCE_SYNOLOGY,
    SYNOLOGY_DEFAULT_HTTPS_PORT,
)

_LOG = logging.getLogger(__name__)


class CCTVSetupFlow(BaseSetupFlow[CCTVConfig]):
    """Multi-step setup flow for security camera integration."""

    def get_manual_entry_form(self) -> RequestUserInput:
        """Step 1: Choose camera source type."""
        return RequestUserInput(
            {"en": "Security Camera Setup"},
            [
                {
                    "id": "source_type",
                    "label": {"en": "Camera Source"},
                    "field": {
                        "dropdown": {
                            "value": SOURCE_MANUAL,
                            "items": [
                                {"id": SOURCE_MANUAL, "label": {"en": "Manual Snapshot URL"}},
                                {"id": SOURCE_SYNOLOGY, "label": {"en": "Synology Surveillance Station"}},
                            ],
                        }
                    },
                }
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> CCTVConfig | RequestUserInput:
        """Process setup input through multiple steps."""
        if "source_type" in input_values or not hasattr(self, "_setup_state"):
            self._setup_state: dict[str, Any] = {}
        self._setup_state.update(input_values)
        state = self._setup_state

        source_type = state.get("source_type", SOURCE_MANUAL)

        if source_type == SOURCE_SYNOLOGY:
            return await self._handle_synology_flow(state)
        return await self._handle_manual_flow(state)

    # --- Manual URL Flow ---

    async def _handle_manual_flow(
        self, input_values: dict[str, Any]
    ) -> CCTVConfig | RequestUserInput:
        """Handle manual camera URL setup."""
        if "camera_count" not in input_values:
            return RequestUserInput(
                {"en": "Manual Camera Setup"},
                [
                    {
                        "id": "name",
                        "label": {"en": "Device Name"},
                        "field": {"text": {"value": "Security Cameras"}},
                    },
                    {
                        "id": "camera_count",
                        "label": {"en": "Number of Cameras"},
                        "field": {
                            "number": {
                                "value": 1,
                                "min": 1,
                                "max": 10,
                                "steps": 1,
                                "decimals": 0,
                            }
                        },
                    },
                ],
            )

        if "camera_1_url" not in input_values:
            return self._build_camera_url_form(input_values)

        return self._build_manual_config(input_values)

    def _build_camera_url_form(self, input_values: dict[str, Any]) -> RequestUserInput:
        """Build dynamic form for camera name + URL pairs."""
        camera_count = int(input_values.get("camera_count", 1))

        fields: list[dict] = []
        for i in range(1, camera_count + 1):
            fields.append({
                "id": f"camera_{i}_name",
                "label": {"en": f"Camera {i} Name"},
                "field": {"text": {"value": f"Camera {i}"}},
            })
            fields.append({
                "id": f"camera_{i}_url",
                "label": {"en": f"Camera {i} Snapshot URL"},
                "field": {"text": {"value": ""}},
            })

        return RequestUserInput({"en": "Camera Snapshot URLs"}, fields)

    def _build_manual_config(self, input_values: dict[str, Any]) -> CCTVConfig:
        """Validate and build config from manual camera inputs."""
        name = input_values.get("name", "Security Cameras").strip()
        camera_count = int(input_values.get("camera_count", 1))

        cameras: list[dict] = []
        for i in range(1, camera_count + 1):
            cam_name = input_values.get(f"camera_{i}_name", f"Camera {i}").strip()
            cam_url = input_values.get(f"camera_{i}_url", "").strip()

            if not cam_name:
                raise ValueError(f"Camera {i} name is required")
            if not cam_url:
                raise ValueError(f"Camera {i} URL is required")
            if not cam_url.startswith(("http://", "https://")):
                raise ValueError(f"Camera {i} URL must start with http:// or https://")

            cameras.append({"name": cam_name, "url": cam_url})

        if not cameras:
            raise ValueError("At least one camera must be configured")

        identifier = f"cctv_{name.lower().replace(' ', '_').replace('.', '_')}"

        _LOG.info("Manual setup complete: %s with %d cameras", name, len(cameras))

        self._setup_state = {}

        return CCTVConfig(
            identifier=identifier,
            name=name,
            source_type=SOURCE_MANUAL,
            cameras=cameras,
            refresh_rate=DEFAULT_REFRESH_RATE,
        )

    # --- Synology Flow ---

    async def _handle_synology_flow(
        self, input_values: dict[str, Any]
    ) -> CCTVConfig | RequestUserInput:
        """Handle Synology Surveillance Station setup."""
        if "host" not in input_values:
            return RequestUserInput(
                {"en": "Synology NAS Connection"},
                [
                    {
                        "id": "host",
                        "label": {"en": "NAS IP Address"},
                        "field": {"text": {"value": ""}},
                    },
                    {
                        "id": "port",
                        "label": {"en": "Port"},
                        "field": {
                            "number": {"value": SYNOLOGY_DEFAULT_HTTPS_PORT}
                        },
                    },
                    {
                        "id": "username",
                        "label": {"en": "Username"},
                        "field": {"text": {"value": ""}},
                    },
                    {
                        "id": "password",
                        "label": {"en": "Password"},
                        "field": {"password": {"value": ""}},
                    },
                    {
                        "id": "use_https",
                        "label": {"en": "Use HTTPS"},
                        "field": {"checkbox": {"value": True}},
                    },
                    {
                        "id": "otp_code",
                        "label": {"en": "2FA Code (leave empty if not enabled)"},
                        "field": {"text": {"value": ""}},
                    },
                ],
            )

        return await self._validate_synology(input_values)

    async def _validate_synology(
        self, input_values: dict[str, Any]
    ) -> CCTVConfig:
        """Authenticate to Synology, discover cameras, return config."""
        host = input_values.get("host", "").strip()
        port = int(input_values.get("port", SYNOLOGY_DEFAULT_HTTPS_PORT))
        username = input_values.get("username", "").strip()
        password = input_values.get("password", "").strip()
        use_https = input_values.get("use_https", True)
        otp_code = input_values.get("otp_code", "").strip()

        if isinstance(use_https, str):
            use_https = use_https.lower() in ("true", "1", "yes")

        if not host:
            raise ValueError("NAS IP address is required")
        if not username:
            raise ValueError("Username is required")
        if not password:
            raise ValueError("Password is required")

        otp_enabled = bool(otp_code)

        existing = self.selected_config_entry
        stored_device_id = getattr(existing, "synology_device_id", "") if existing else ""

        temp_config = CCTVConfig(
            identifier="temp",
            name="temp",
            source_type=SOURCE_SYNOLOGY,
            host=host,
            port=port,
            username=username,
            password=password,
            use_https=use_https,
            otp_enabled=otp_enabled,
            synology_device_id=stored_device_id,
        )

        client = CCTVClient(
            temp_config,
            otp_code=otp_code if otp_code else None,
            device_id=stored_device_id or None,
        )
        try:
            if not await client.connect():
                raise ValueError(f"Cannot authenticate to Synology NAS at {host}:{port}")

            cameras = await client.discover_cameras()
            if not cameras:
                raise ValueError("No cameras found in Synology Surveillance Station")

            camera_list = [
                {"id": c["id"], "name": c["name"], "video_codec": c.get("video_codec", 0)}
                for c in cameras
            ]
            identifier = f"synology_{host.replace('.', '_')}"
            name = f"Synology ({host})"
            sid = client.session_id or ""
            device_id = client.device_id or ""
            syno_token = client.syno_token or ""

            _LOG.info("Synology setup complete: %s with %d cameras", name, len(camera_list))

            self._setup_state = {}

            return CCTVConfig(
                identifier=identifier,
                name=name,
                source_type=SOURCE_SYNOLOGY,
                cameras=camera_list,
                host=host,
                port=port,
                username=username,
                password=password,
                use_https=use_https,
                otp_enabled=otp_enabled,
                synology_sid=sid,
                synology_device_id=device_id,
                synology_syno_token=syno_token,
                refresh_rate=DEFAULT_REFRESH_RATE,
            )

        finally:
            await client.close(logout=False)
