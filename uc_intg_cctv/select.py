"""
Camera select entity for switching between cameras.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import StatusCodes, select
from ucapi_framework import SelectEntity

from uc_intg_cctv.config import CCTVConfig
from uc_intg_cctv.device import CCTVDevice

_LOG = logging.getLogger(__name__)


class CameraSelect(SelectEntity):
    """Select entity for switching between configured cameras."""

    def __init__(self, device_config: CCTVConfig, device: CCTVDevice) -> None:
        self._device = device
        entity_id = f"select.{device_config.identifier}.camera"
        super().__init__(
            entity_id,
            f"{device_config.name} Camera",
            {
                select.Attributes.STATE: select.States.UNKNOWN,
                select.Attributes.OPTIONS: [],
                select.Attributes.CURRENT_OPTION: "",
            },
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Sync select entity state from device."""
        if self._device.state == "UNAVAILABLE":
            self.update({select.Attributes.STATE: select.States.UNAVAILABLE})
            return

        names = self._device.camera_names
        current = self._device.current_camera_name

        self.update({
            select.Attributes.STATE: select.States.ON,
            select.Attributes.OPTIONS: names,
            select.Attributes.CURRENT_OPTION: current,
        })

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle select commands."""
        names = self._device.camera_names
        if not names:
            return StatusCodes.SERVER_ERROR

        match cmd_id:
            case select.Commands.SELECT_OPTION:
                option = params.get("option", "") if params else ""
                if option in names:
                    await self._device.select_camera(names.index(option))
                    return await self._ensure_streaming()
                return StatusCodes.BAD_REQUEST
            case select.Commands.SELECT_NEXT:
                idx = (self._device.current_camera_index + 1) % len(names)
                await self._device.select_camera(idx)
                return await self._ensure_streaming()
            case select.Commands.SELECT_PREVIOUS:
                idx = (self._device.current_camera_index - 1) % len(names)
                await self._device.select_camera(idx)
                return await self._ensure_streaming()
            case _:
                return StatusCodes.NOT_IMPLEMENTED

    async def _ensure_streaming(self) -> StatusCodes:
        if self._device.streaming or await self._device.start_streaming():
            return StatusCodes.OK
        return StatusCodes.SERVICE_UNAVAILABLE
