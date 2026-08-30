"""
Configuration for the Security Camera integration.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from dataclasses import dataclass, field

from uc_intg_cctv.const import DEFAULT_REFRESH_RATE, SOURCE_MANUAL, SYNOLOGY_DEFAULT_HTTPS_PORT


@dataclass
class CCTVConfig:
    """Security camera device configuration."""

    identifier: str = ""
    name: str = ""
    source_type: str = SOURCE_MANUAL
    cameras: list = field(default_factory=list)
    host: str = ""
    port: int = SYNOLOGY_DEFAULT_HTTPS_PORT
    username: str = ""
    password: str = ""
    use_https: bool = True
    otp_enabled: bool = False
    synology_sid: str = ""
    synology_device_id: str = ""
    synology_syno_token: str = ""
    refresh_rate: int = DEFAULT_REFRESH_RATE
