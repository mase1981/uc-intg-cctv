"""
CCTV integration driver.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging

from ucapi_framework import BaseIntegrationDriver

from uc_intg_cctv.config import CCTVConfig
from uc_intg_cctv.device import CCTVDevice
from uc_intg_cctv.media_player import CCTVMediaPlayer
from uc_intg_cctv.select import CameraSelect

_LOG = logging.getLogger(__name__)


class CCTVDriver(BaseIntegrationDriver[CCTVDevice, CCTVConfig]):
    """Security camera integration driver."""

    def __init__(self):
        super().__init__(
            device_class=CCTVDevice,
            entity_classes=[
                CCTVMediaPlayer,
                lambda cfg, dev: [CameraSelect(cfg, dev)] if len(cfg.cameras) > 1 else [],
            ],
            driver_id="uc-intg-cctv",
        )
