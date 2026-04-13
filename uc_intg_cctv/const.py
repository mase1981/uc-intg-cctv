"""
Constants for the Security Camera integration.

:copyright: (c) 2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

SOURCE_MANUAL = "manual"
SOURCE_SYNOLOGY = "synology"

DEFAULT_REFRESH_RATE = 6
MAX_IMAGE_SIZE_KB = 80
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
MAX_CONSECUTIVE_FAILURES = 5

SYNOLOGY_AUTH_API = "/webapi/auth.cgi"
SYNOLOGY_ENTRY_API = "/webapi/entry.cgi"
SYNOLOGY_DEFAULT_HTTP_PORT = 5000
SYNOLOGY_DEFAULT_HTTPS_PORT = 5001

CODEC_H264 = 3
CODEC_H265 = 6

