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
SYNOLOGY_QUERY_API = "/webapi/query.cgi"
SYNOLOGY_DEFAULT_HTTP_PORT = 5000
SYNOLOGY_DEFAULT_HTTPS_PORT = 5001

SYNOLOGY_DEVICE_NAME = "UnfoldedCircle"
SYNOLOGY_AUTH_VERSION = 7
SYNOLOGY_AUTH_VERSION_FALLBACK = 6
SYNOLOGY_DEVICE_TOKEN_FLOOR = 6

# Surveillance Station error codes that mean the session is dead and a silent
# re-login should be attempted: 105 no-permission, 106 timeout, 107 duplicate
# login, 119 invalid session. NOT 400/401/402 - those are DSM login-response
# codes (or, inside the Surveillance API, parameter/execution errors such as
# GetSnapshot returning 401 for cameras that do not support it), so re-authing
# on them would trigger a needless re-login storm and DSM auto-block.
SYNOLOGY_REAUTH_CODES = frozenset({105, 106, 107, 119})
# Error codes that mean retrying is pointless (auto-block / locked account).
SYNOLOGY_TERMINAL_CODES = frozenset({407, 411})

CODEC_H264 = 3
CODEC_H265 = 6

