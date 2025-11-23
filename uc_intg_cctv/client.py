"""
Security Camera Client for Unfolded Circle integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import ssl
import aiohttp
import base64
import io
from typing import Optional, Dict, Any
from PIL import Image

LOG = logging.getLogger(__name__)


class SecurityCameraClient:
    """Simple client for fetching camera snapshots"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.snapshot_url = config["snapshot_url"]
        self.camera_name = config["name"]
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self) -> bool:
        """Establish HTTP session with SSL verification disabled for self-signed certs"""
        if self.session:
            return True
            
        try:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(
                limit=5,
                limit_per_host=2,
                keepalive_timeout=30,
                ssl=ssl_context
            )
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector
            )
            
            LOG.debug(f"Connected to camera: {self.camera_name}")
            return True
            
        except Exception as e:
            LOG.error(f"Failed to connect to camera {self.camera_name}: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            LOG.debug(f"Disconnected from camera: {self.camera_name}")
    
    async def test_connection(self) -> bool:
        """Test if camera snapshot URL is accessible"""
        try:
            if not await self.connect():
                return False
                
            image_data = await self.get_snapshot()
            
            if image_data and len(image_data) > 1000:
                LOG.info(f"✓ Camera '{self.camera_name}' test successful ({len(image_data)} bytes)")
                return True
            else:
                LOG.warning(f"✗ Camera '{self.camera_name}' test failed - invalid image data")
                return False
                
        except Exception as e:
            LOG.error(f"✗ Camera '{self.camera_name}' test failed: {e}")
            return False
        finally:
            await self.disconnect()
    
    async def get_snapshot(self) -> Optional[bytes]:
        """Get a snapshot image from the camera"""
        if not self.session:
            if not await self.connect():
                return None
        
        try:
            async with self.session.get(self.snapshot_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    
                    if self._is_valid_image(image_data):
                        return image_data
                    else:
                        LOG.warning(f"Invalid image data from {self.camera_name}")
                        return None
                else:
                    LOG.error(f"HTTP {response.status} from {self.camera_name}")
                    return None
                    
        except asyncio.TimeoutError:
            LOG.warning(f"Timeout getting snapshot from {self.camera_name}")
            return None
        except Exception as e:
            LOG.error(f"Error getting snapshot from {self.camera_name}: {e}")
            return None
    
    def _is_valid_image(self, data: bytes) -> bool:
        """Check if data is a valid image"""
        try:
            if data.startswith(b'\xff\xd8\xff'):
                return len(data) > 1000
            elif data.startswith(b'\x89PNG\r\n\x1a\n'):
                return len(data) > 1000
            else:
                return False
        except:
            return False
    
    async def optimize_image_for_remote(self, image_data: bytes, max_size_kb: int = 80) -> Optional[str]:
        """Optimize camera image for display on remote"""
        try:
            image = Image.open(io.BytesIO(image_data))
            
            target_width = 320
            target_height = 240
            
            img_ratio = image.width / image.height
            screen_ratio = target_width / target_height
            
            if img_ratio > screen_ratio:
                new_width = target_width
                new_height = int(target_width / img_ratio)
            else:
                new_height = target_height
                new_width = int(target_height * img_ratio)
            
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            if resized_image.mode != 'RGB':
                resized_image = resized_image.convert('RGB')
            
            quality = 85
            output_buffer = io.BytesIO()
            
            while quality > 20:
                output_buffer.seek(0)
                output_buffer.truncate()
                
                resized_image.save(
                    output_buffer, 
                    format='JPEG', 
                    quality=quality, 
                    optimize=True,
                    progressive=True
                )
                
                size_kb = output_buffer.tell() / 1024
                if size_kb <= max_size_kb:
                    break
                    
                quality -= 10
            
            output_buffer.seek(0)
            optimized_data = output_buffer.read()
            
            base64_image = base64.b64encode(optimized_data).decode('utf-8')
            
            LOG.debug(f"Image optimized: {len(optimized_data)/1024:.1f}KB (quality={quality})")
            
            return base64_image
            
        except Exception as e:
            LOG.error(f"Error optimizing image: {e}")
            return None
    
    async def close(self) -> None:
        """Close the client and clean up resources"""
        await self.disconnect()