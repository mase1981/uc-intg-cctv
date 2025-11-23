"""
Security Camera Integration for Unfolded Circle Remote.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import json
import os

def _get_version_from_driver_json():
    """Get version from driver.json file."""
    try:
        driver_json_path = os.path.join(os.path.dirname(__file__), "..", "driver.json")
        with open(driver_json_path, "r", encoding="utf-8") as f:
            driver_data = json.load(f)
            return driver_data.get("version", "unknown")
    except Exception:
        return "unknown"

__version__ = _get_version_from_driver_json()