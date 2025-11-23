"""
Configuration utilities for Security Camera Integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

_LOG = logging.getLogger(__name__)


def create_entity_id(name: str) -> str:
    """Create a valid entity ID from a camera name"""
    entity_id = re.sub(r'[^a-z0-9]+', '_', name.lower())
    entity_id = entity_id.strip('_')
    
    if entity_id and entity_id[0].isdigit():
        entity_id = f"camera_{entity_id}"
    
    if not entity_id:
        entity_id = "camera"
    
    return entity_id


def validate_url(url: str) -> bool:
    """Validate snapshot URL format"""
    if not url:
        return False
    
    return url.startswith('http://') or url.startswith('https://')


def build_camera_config(camera_name: str, snapshot_url: str) -> Dict[str, Any]:
    """Build camera configuration from name and URL"""
    return {
        "name": camera_name,
        "snapshot_url": snapshot_url,
        "refresh_rate": 10
    }


class CameraConfig:
    """Configuration manager for camera integration."""

    def __init__(self):
        """Initialize configuration manager."""
        # Use UC_CONFIG_HOME if set (production/Docker), otherwise use project root (development)
        if os.getenv("UC_CONFIG_HOME"):
            self._config_dir = os.getenv("UC_CONFIG_HOME")
        else:
            # Development: save in project root (one level up from uc_intg_cctv/)
            current_file_dir = os.path.dirname(os.path.abspath(__file__))
            self._config_dir = os.path.dirname(current_file_dir)
        
        self._config_file = Path(self._config_dir) / "config.json"
        self._config_data = {}
        self._load_config()
        
        _LOG.info(f"Config path: {self._config_file}")

    def _load_config(self) -> bool:
        """Load configuration from file."""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    self._config_data = json.load(f)
                _LOG.info(f"Configuration loaded from {self._config_file}")
                return True
        except Exception as e:
            _LOG.error(f"Failed to load configuration: {e}")
        
        return False

    def save_config(self, config_data: Dict[str, Any] = None) -> bool:
        """Save configuration to file."""
        try:
            # Create config directory if it doesn't exist
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            
            if config_data:
                self._config_data = config_data
            
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=2)
            
            _LOG.info(f"Configuration saved to {self._config_file}")
            return True
        except Exception as e:
            _LOG.error(f"Failed to save configuration: {e}")
            return False

    def get_cameras(self):
        """Get list of configured cameras."""
        return self._config_data.get("cameras", [])

    def get_enabled_apps(self):
        """Get list of enabled cameras (compatibility method)."""
        cameras = self.get_cameras()
        return [cam["name"] for cam in cameras] if cameras else []