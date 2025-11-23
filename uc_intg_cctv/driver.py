#!/usr/bin/env python3
"""
Security Camera Integration Driver for Unfolded Circle Remote.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ucapi import IntegrationAPI, StatusCodes, Events, DeviceStates

from uc_intg_cctv.client import SecurityCameraClient
from uc_intg_cctv.media_player import SecurityCameraMediaPlayer, CameraEntityFactory
from uc_intg_cctv.config import CameraConfig
from uc_intg_cctv.setup import SecurityCameraSetup

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

api: IntegrationAPI = None
_config: CameraConfig = None
_camera_entity: SecurityCameraMediaPlayer = None
_setup_manager: SecurityCameraSetup = None


async def _on_connect():
    """Handle remote connection."""
    LOG.info("Remote connected")
    await api.set_device_state(DeviceStates.CONNECTED)


async def _on_disconnect():
    """Handle remote disconnection."""
    LOG.info("Remote disconnected")
    await api.set_device_state(DeviceStates.DISCONNECTED)
    
    if _camera_entity and _camera_entity.is_streaming:
        LOG.info("Stopping camera snapshot streaming")
        await _camera_entity.stop_image_streaming()


async def _on_subscribe_entities(entity_ids: list[str]):
    """Handle entity subscription - push initial state."""
    LOG.info(f"Entities subscribed: {entity_ids}")
    
    if _camera_entity and _camera_entity.id in entity_ids:
        LOG.info(f"Pushing initial state for {_camera_entity.id}")
        await _camera_entity.push_initial_state()


async def _init_integration(force_recreate: bool = False) -> bool:
    """Initialize the integration with existing config."""
    global _camera_entity
    
    LOG.info(f"Initializing Security Camera Integration (force_recreate={force_recreate})")
    
    # Reload config from disk (critical for post-setup initialization)
    _config._load_config()
    
    cameras_config = _config.get_cameras()
    
    if not cameras_config:
        LOG.warning("No cameras configured")
        return False
    
    try:
        is_valid, error_msg = CameraEntityFactory.validate_cameras_config(cameras_config)
        if not is_valid:
            LOG.error(f"Invalid camera configuration: {error_msg}")
            return False
        
        # If reconfiguring, completely clean up old entity
        if force_recreate and _camera_entity:
            LOG.info("Removing old entity for reconfiguration")
            old_entity_id = _camera_entity.id
            
            # Stop streaming and disconnect
            await _camera_entity.disconnect()
            
            # Remove from both available and configured
            if api.available_entities.contains(old_entity_id):
                api.available_entities.remove(old_entity_id)
                LOG.info(f"Removed old entity from available_entities: {old_entity_id}")
            
            if api.configured_entities.contains(old_entity_id):
                api.configured_entities.remove(old_entity_id)
                LOG.info(f"Removed old entity from configured_entities: {old_entity_id}")
            
            _camera_entity = None
            
            # Give ucapi time to fully clean up
            await asyncio.sleep(0.5)
        
        # Log the camera names we're about to create
        camera_names = [cam["name"] for cam in cameras_config]
        LOG.info(f"Creating entity with cameras: {camera_names}")
        
        # Create new entity
        _camera_entity = CameraEntityFactory.create_camera_entity(
            integration=api,
            cameras_config=cameras_config
        )
        
        # Add to available entities
        api.available_entities.add(_camera_entity)
        
        LOG.info(f"Created camera entity with {len(cameras_config)} cameras")
        LOG.info(f"Entity clients: {list(_camera_entity.clients.keys())}")
        
        await _test_all_cameras(cameras_config)
        
        return True
        
    except Exception as e:
        LOG.error(f"Failed to setup camera entity: {e}", exc_info=True)
        return False


async def _test_all_cameras(cameras_config: List[Dict[str, Any]]) -> None:
    """Test connections to all configured cameras."""
    LOG.info("Testing connections to all cameras...")
    
    test_tasks = []
    for camera_config in cameras_config:
        client = SecurityCameraClient(camera_config)
        test_tasks.append(_test_single_camera(client, camera_config["name"]))
    
    results = await asyncio.gather(*test_tasks, return_exceptions=True)
    
    success_count = sum(1 for result in results if result is True)
    total_count = len(cameras_config)
    
    LOG.info(f"Camera connection test: {success_count}/{total_count} cameras online")


async def _test_single_camera(client: SecurityCameraClient, camera_name: str) -> bool:
    """Test connection to a single camera."""
    try:
        result = await client.test_connection()
        await client.close()
        
        if result:
            LOG.info(f"✓ Camera '{camera_name}' online")
        else:
            LOG.warning(f"✗ Camera '{camera_name}' offline")
        
        return result
    except Exception as e:
        LOG.error(f"✗ Camera '{camera_name}' test error: {e}")
        await client.close()
        return False


async def setup_handler(msg) -> Any:
    """Handle the setup flow for camera configuration."""
    global _setup_manager, _config
    
    if not _setup_manager:
        _setup_manager = SecurityCameraSetup(_config, api)
    
    action = await _setup_manager.handle_setup(msg)
    
    from ucapi import SetupComplete
    if isinstance(action, SetupComplete):
        LOG.info("Setup complete, reinitializing integration with new config")
        # Force recreate to replace old entity with new configuration
        success = await _init_integration(force_recreate=True)
        if success:
            LOG.info("Integration reinitialized successfully with new configuration")
        else:
            LOG.error("Failed to reinitialize integration after setup")
    
    return action


async def main() -> None:
    """Main entry point for the integration."""
    global api, _config
    
    LOG.info("Starting Security Camera Integration")
    
    try:
        loop = asyncio.get_event_loop()
        api = IntegrationAPI(loop)
        _config = CameraConfig()
        
        api.add_listener(Events.CONNECT, _on_connect)
        api.add_listener(Events.DISCONNECT, _on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, _on_subscribe_entities)
        
        await _init_integration(force_recreate=False)
        
        await api.init("driver.json", setup_handler)
        
        LOG.info("Driver ready and listening for connections...")
        
        if hasattr(api, '_server_task') and api._server_task:
            await api._server_task
        else:
            while True:
                await asyncio.sleep(3600)
        
    except KeyboardInterrupt:
        LOG.info("Integration stopped by user")
    except Exception as e:
        LOG.error(f"Integration failed: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOG.info("Integration stopped by user")