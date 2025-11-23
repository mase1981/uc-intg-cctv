"""
Setup flow for Security Camera Integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import ssl
from typing import Any

import aiohttp
from ucapi import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    RequestUserInput,
    UserDataResponse,
    RequestUserConfirmation,
    SetupAction,
    SetupComplete,
    SetupError,
    UserConfirmationResponse,
)

from uc_intg_cctv.config import build_camera_config, validate_url, CameraConfig

_LOG = logging.getLogger(__name__)


class SecurityCameraSetup:
    """Setup flow handler for Security Camera integration."""

    def __init__(self, config: CameraConfig, api):
        """Initialize setup handler."""
        self._config = config
        self._api = api
        self._camera_count = 0
        self._cameras_data = []

    async def handle_setup(self, msg_data: Any) -> SetupAction:
        """Handle setup request."""
        try:
            if isinstance(msg_data, DriverSetupRequest):
                return await self._handle_driver_setup_request(msg_data)
            elif isinstance(msg_data, UserDataResponse):
                return await self._handle_user_data_response(msg_data)
            elif isinstance(msg_data, UserConfirmationResponse):
                return await self._handle_user_confirmation_response(msg_data)
            elif isinstance(msg_data, AbortDriverSetup):
                _LOG.info("Setup aborted by user or system.")
                return SetupError(msg_data.error)
            else:
                _LOG.error("Unknown setup message type: %s", type(msg_data))
                return SetupError(IntegrationSetupError.OTHER)

        except Exception as ex:
            _LOG.error("An unexpected error occurred during setup: %s", ex, exc_info=True)
            return SetupError(IntegrationSetupError.OTHER)

    async def _handle_driver_setup_request(self, request: DriverSetupRequest) -> SetupAction:
        """Handle initial driver setup request - get camera count."""
        _LOG.info("Starting Security Camera setup (reconfigure: %s)", request.reconfigure)
        _LOG.info(f"Setup data received: {request.setup_data}")

        camera_count_value = request.setup_data.get("camera_count")
        
        if camera_count_value is None:
            _LOG.error("camera_count field missing from setup_data")
            return SetupError(IntegrationSetupError.OTHER)

        try:
            self._camera_count = int(camera_count_value)
        except (ValueError, TypeError):
            _LOG.error(f"Invalid camera_count value: {camera_count_value}")
            return SetupError(IntegrationSetupError.OTHER)

        if self._camera_count < 1 or self._camera_count > 50:
            _LOG.error(f"Camera count out of range: {self._camera_count}")
            return SetupError(IntegrationSetupError.OTHER)

        _LOG.info(f"User requested {self._camera_count} cameras")

        return self._build_camera_input_form()

    def _build_camera_input_form(self) -> RequestUserInput:
        """Build dynamic form for camera details based on count."""
        settings = []

        for i in range(self._camera_count):
            settings.extend([
                {
                    "id": f"camera_{i}_name",
                    "label": {
                        "en": f"Camera {i+1} Name"
                    },
                    "field": {
                        "text": {
                            "value": f"Camera {i+1}"
                        }
                    }
                },
                {
                    "id": f"camera_{i}_url",
                    "label": {
                        "en": f"Camera {i+1} Snapshot URL"
                    },
                    "field": {
                        "text": {
                            "value": ""
                        }
                    }
                }
            ])

        return RequestUserInput(
            title={"en": "Configure Cameras"},
            settings=settings
        )

    async def _handle_user_data_response(self, response: UserDataResponse) -> SetupAction:
        """Handle camera configuration input from user."""
        _LOG.info(f"Received camera configuration data: {response.input_values}")

        self._cameras_data = []
        connection_results = {}

        for i in range(self._camera_count):
            camera_name = response.input_values.get(f"camera_{i}_name", f"Camera {i+1}").strip()
            camera_url = response.input_values.get(f"camera_{i}_url", "").strip()

            if not camera_name or not camera_url:
                _LOG.error(f"Camera {i+1}: Missing name or URL")
                return SetupError(IntegrationSetupError.OTHER)

            if not validate_url(camera_url):
                _LOG.error(f"Camera {i+1}: Invalid URL format (must start with http:// or https://)")
                return SetupError(IntegrationSetupError.OTHER)

            camera_config = build_camera_config(camera_name, camera_url)
            self._cameras_data.append(camera_config)

            test_result = await self._test_camera_connection(camera_name, camera_url)
            connection_results[camera_name] = test_result
            _LOG.info(f"Connection test for '{camera_name}': {test_result}")

        return await self._show_setup_summary(connection_results)

    async def _test_camera_connection(self, camera_name: str, snapshot_url: str) -> dict:
        """Test connection to camera snapshot URL with SSL verification disabled."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                _LOG.debug(f"Testing '{camera_name}' at {snapshot_url}")
                
                async with session.get(snapshot_url) as response:
                    _LOG.debug(f"'{camera_name}' response: HTTP {response.status}")
                    
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        data = await response.read()
                        
                        if len(data) > 1000 and ('image' in content_type.lower() or 
                                                   data.startswith(b'\xff\xd8\xff') or 
                                                   data.startswith(b'\x89PNG')):
                            return {"success": True, "status": response.status, "size": len(data)}
                        else:
                            return {"success": False, "error": "URL does not return a valid image"}
                    else:
                        return {"success": False, "error": f"HTTP {response.status}"}

        except aiohttp.ClientConnectorError:
            return {"success": False, "error": "Connection refused"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Connection timeout"}
        except Exception as ex:
            error_msg = str(ex)[:50]
            return {"success": False, "error": f"Error: {error_msg}"}

    async def _show_setup_summary(self, connection_results: dict) -> RequestUserConfirmation:
        """Show setup summary for user confirmation."""
        summary_lines = ["📹 Security Camera Setup Summary\n"]

        for camera_config in self._cameras_data:
            camera_name = camera_config["name"]
            result = connection_results[camera_name]

            if result["success"]:
                size_kb = result.get("size", 0) / 1024
                summary_lines.append(f"✅ {camera_name}: Connected ({size_kb:.1f} KB)")
            else:
                error = result.get("error", "Unknown error")
                summary_lines.append(f"⚠️ {camera_name}: {error}")

        summary_lines.extend([
            "",
            "📝 Configuration will be saved and camera entity created.",
            "⚠️ Cameras with connection issues will still be configured."
        ])

        return RequestUserConfirmation(
            title={"en": "Confirm Camera Setup"},
            header={"en": "Setup Complete!"},
            footer={"en": "\n".join(summary_lines)}
        )

    async def _handle_user_confirmation_response(self, response: UserConfirmationResponse) -> SetupAction:
        """Handle user confirmation response."""
        if response.confirm:
            return await self._save_configuration()
        else:
            return AbortDriverSetup(IntegrationSetupError.USER_ABORT)

    async def _save_configuration(self) -> SetupAction:
        """Save configuration and complete setup."""
        try:
            config_data = {
                "cameras": self._cameras_data,
                "entity_id": "security_cameras",
                "entity_name": "Security Cameras",
                "refresh_rate": 10
            }

            if not self._config.save_config(config_data):
                _LOG.error("Failed to save configuration")
                return SetupError(IntegrationSetupError.OTHER)

            _LOG.info(f"Configuration saved successfully for {len(self._cameras_data)} cameras")
            return SetupComplete()

        except Exception as ex:
            _LOG.error("Failed to save configuration: %s", ex)
            return SetupError(IntegrationSetupError.OTHER)