
# Security Camera Integration for Unfolded Circle Remote

[![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-cctv?style=flat-square)](https://github.com/mase1981/uc-intg-cctv/releases)
![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)
[![GitHub Issues](https://img.shields.io/github/issues/mase1981/uc-intg-cctv?style=flat-square)](https://github.com/mase1981/uc-intg-cctv/issues)
[![GitHub Discussions](https://img.shields.io/github/discussions/mase1981/uc-intg-cctv?style=flat-square)](https://github.com/mase1981/uc-intg-cctv/discussions)
![cctv](https://img.shields.io/badge/Security-Cameras-red)
[![Community Forum](https://img.shields.io/badge/community-forum-blue?style=flat-square)](https://community.unfoldedcircle.com/)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-cctv/total?style=flat-square)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg?style=flat-square)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA&style=flat-square)](https://github.com/sponsors/mase1981)

**Author:** Meir Miyara  
**Version:** 1.0.0

---

## 💖 Support This Project

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

Your support helps maintain this integration. Thank you! ❤️
---

## Overview

Universal security camera integration for **Unfolded Circle Remote 2/3** that displays camera snapshots directly on your remote's screen with automatic 10-second refresh. This integration works with **any camera or NVR system** that provides an HTTP/HTTPS snapshot URL - no complex configuration or manufacturer-specific setup required.

### Key Features

✅ **Universal Compatibility** - Works with ANY camera or NVR (Reolink, Hikvision, Dahua, Synology, Blue Iris, Amcrest, Axis, etc.)  
✅ **Simple Setup** - Just provide camera name and snapshot URL  
✅ **Multi-Camera Support** - Support for up to 50 cameras in a single integration entity  
✅ **Automatic Refresh** - 10-second snapshot updates when viewing  
✅ **Self-Signed SSL Support** - Works with HTTPS cameras using self-signed certificates  
✅ **Resource Efficient** - Automatically stops pulling snapshots when not viewing  
✅ **Easy Source Switching** - Change between cameras with the source selector  
✅ **Reboot Persistent** - Configuration survives remote reboots

---

## Requirements

### Hardware
- **Unfolded Circle Remote 2 or Remote 3**
- IP cameras or NVR system with HTTP/HTTPS snapshot capability
- Network connectivity between Remote and cameras

### Camera Requirements
Your camera or NVR **must provide**:
- HTTP or HTTPS snapshot URL that returns a JPEG or PNG image
- Network accessibility from the Remote
- Authentication (if required) embedded in the URL

# CRITICAL - MUST FOLLOW THIS STEP
### Testing Your Camera URL

**CRITICAL**: Before adding cameras to the integration, test your snapshot URL in a web browser:

You must find your specific camera absoloute path URL, google, read your camera documentation etc. Without first validating you can actually see your camera image via your browser, it will 100% guarantee to not work in this integration.
1. Open your browser (Chrome, Firefox, Edge, Safari)
2. Paste your complete snapshot URL (including username/password if needed)
3. You should see a **single still image** (NOT a video stream)
4. The image should load each time you refresh the page

Exmaples below in this README file for several camera brands.

**Example of what you should see:**
- ✅ **Correct**: A JPEG/PNG image that loads instantly
- ❌ **Incorrect**: Video player, streaming video, or error message

If you see a video stream or player instead of a static image, you need to find your camera's **snapshot endpoint**, not the streaming URL. 

**This will be the first trobuleshooting question: are you able to view your snapshot url in a browser? before any support will be given**

---

## Installation

### Method 1: Direct Installation (Recommended for Testing)

1. **Download** the latest `.tar.gz` release from [GitHub Releases](https://github.com/mase1981/uc-intg-cctv/releases)
2. **Upload** via Remote Web Configurator:
   - Go to `Integrations` → `Add Integration` → `Upload`
3. **Configure** using the setup wizard

### Method 2: Docker Compose (Recommended for Production)

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  cctv-integration:
    image: ghcr.io/mase1981/uc-intg-cctv:latest
    container_name: uc-intg-cctv
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./data:/data
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - UC_INTEGRATION_HTTP_PORT=9092
      - UC_DISABLE_MDNS_PUBLISH=false
```
**Docker Run:**
```bash
docker run -d --name=uc-intg-cctv --network host -v </local/path>:/data -e UC_CONFIG_HOME=/data -e UC_INTEGRATION_HTTP_PORT=9090 --restart unless-stopped ghcr.io/mase1981/uc-intg-cctv:latest
```
Start the integration:
```bash
docker-compose up -d
```

### Method 3: Manual Installation (Development)

```bash
# Clone the repository
git clone https://github.com/mase1981/uc-intg-cctv.git
cd uc-intg-cctv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run the integration
python -m uc_intg_cctv.driver
```

---

## Configuration

### Step 1: Find Your Camera Snapshot URLs

Every camera manufacturer has different snapshot URLs. Here are examples for popular brands:

#### Reolink Cameras
```
https://192.168.1.100/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=wuuPhkmUCeI9WG7C&user=admin&password=yourpassword
```

#### Hikvision Cameras
```
http://192.168.1.101/ISAPI/Streaming/channels/101/picture?auth=YWRtaW46cGFzc3dvcmQ=
```
*Note: auth parameter is base64 encoded `username:password`*

#### Dahua Cameras
```
http://192.168.1.102/cgi-bin/snapshot.cgi?channel=1&user=admin&password=yourpassword
```

#### Amcrest Cameras
```
http://192.168.1.103/cgi-bin/snapshot.cgi?channel=0&user=admin&password=yourpassword
```

#### Axis Cameras
```
http://192.168.1.104/axis-cgi/jpg/image.cgi?resolution=640x480
```

#### Generic MJPEG/Snapshot
```
http://192.168.1.105/snapshot.jpg
http://192.168.1.106/cgi-bin/snapshot.cgi
```

#### Synology Surveillance Station
```
http://192.168.1.107:5000/webapi/entry.cgi?api=SYNO.SurveillanceStation.Camera&method=GetSnapshot&cameraId=1&version=1
```

#### Blue Iris NVR
```
http://192.168.1.108:81/image/CAM1?q=100&s=100&user=admin&pw=yourpassword
```

#### UniFi Protect
```
https://192.168.1.109/proxy/protect/api/cameras/CAMERA_ID/snapshot?ts=0
```

### Step 2: Integration Setup Wizard

1. **Access Web Configurator**: `http://your-remote-ip:8080`
2. **Add Integration**: Go to `Integrations` → `Add Integration`
3. **Select "Security Camera Integration"**

4. **Camera Count Selection**:
   - Choose number of cameras (1-50)
   - Click **NEXT**

5. **Camera Configuration**:
   - For each camera, provide:
     - **Camera Name**: Friendly name (e.g., "Front Door", "Backyard")
     - **Snapshot URL**: Complete HTTP/HTTPS URL including authentication

6. **Connection Test**:
   - Integration will test each camera URL
   - ✅ Green check = Camera online and working
   - ⚠️ Warning = Camera offline or URL incorrect
   - **Note**: You can still save cameras with warnings to fix later

7. **Confirmation**:
   - Review summary
   - Click **CONFIRM** to save

### Step 3: Add Entity to Remote

1. Open Remote UI
2. Go to entity settings
3. Find "Security Cameras" entity
4. Add to your activity/page
5. Done! Select cameras via source selector

---

## Usage

### Viewing Camera Feeds

1. **Open Entity**: Tap the "Security Cameras" tile on your Remote
2. **Select Camera**: Use the **SOURCE** button to choose a camera
3. **Automatic Display**: Camera snapshot appears and refreshes every 10 seconds
4. **Switch Cameras**: Select different source to view another camera
5. **Stop Viewing**: Press **OFF** or exit to stop snapshot updates

### Enabled Controls

- **ON/OFF Button**: Start/stop camera viewing
- **SOURCE Selector**: Switch between configured cameras

### What's NOT Available

This is a **snapshot-based viewer**, not a video player, so these features are disabled:
- ❌ Play/Pause controls
- ❌ Volume controls  
- ❌ Fast forward/rewind
- ❌ PTZ (Pan/Tilt/Zoom) controls
- ❌ Recording functions

---

## Finding Your Camera's Snapshot URL

### Method 1: Camera Web Interface

1. Access your camera's web interface
2. Look in settings for:
   - "Snapshot URL"
   - "CGI API"
   - "Image Capture"
   - "Still Image URL"

### Method 2: Camera Documentation

Search for:
- Camera model + "snapshot URL"
- Camera model + "CGI API"
- NVR model + "API documentation"

### Method 3: Network Monitor

1. Open camera in web browser
2. Open Developer Tools (F12)
3. Go to **Network** tab
4. Click camera snapshot/refresh
5. Look for URLs ending in `.jpg`, `.jpeg`, or containing "snapshot"

### Method 4: ONVIF Browser

If your camera supports ONVIF:
1. Use ONVIF Device Manager
2. Browse to "Media" → "Snapshot URI"
3. Copy the snapshot URL

---

## Troubleshooting

### Camera Not Connecting

**Problem**: Camera shows "Connection refused" or "Timeout"

**Solutions**:
- ✅ Verify URL works in a web browser first
- ✅ Check camera is powered on and network-accessible
- ✅ Confirm firewall allows access from Remote's IP
- ✅ Test with HTTP first (if HTTPS fails)
- ✅ Ensure credentials are correct in URL
- ✅ Check camera's network settings allow external access

### Authentication Errors

**Problem**: HTTP 401 or 403 errors

**Solutions**:
- ✅ Verify username/password in URL
- ✅ Some cameras need base64 encoded credentials
- ✅ Check if camera requires session/token authentication
- ✅ Enable "allow anonymous access" if available

### HTTPS/SSL Certificate Issues

**Problem**: SSL verification errors

**Solutions**:
- ✅ This integration **supports self-signed certificates**
- ✅ If still failing, try HTTP instead of HTTPS
- ✅ Check if camera has valid SSL certificate
- ✅ Ensure camera's SSL/TLS settings allow connections

### No Image Displayed

**Problem**: Entity opens but shows "Nothing is playing"

**Solutions**:
- ✅ Test URL returns actual image (JPEG/PNG), not HTML page
- ✅ Check image file size isn't too large (>5MB)
- ✅ Verify camera returns proper Content-Type header
- ✅ Try different image quality/resolution settings on camera
- ✅ Check Remote logs for specific errors

### Slow Refresh or Lag

**Problem**: Images update slowly or lag behind

**Solutions**:
- Fixed 10-second refresh (by design)
- ✅ Check network latency to camera
- ✅ Reduce camera image quality/resolution
- ✅ Verify camera isn't overloaded with connections
- ✅ Check Remote's WiFi signal strength

### Entity Shows "OFF" After Setup

**Problem**: Entity visible but shows OFF state

**Solutions**:
- ✅ Select a camera from SOURCE list first
- ✅ Entity auto-starts when source is selected
- ✅ Check logs for initialization errors
- ✅ Try restarting Remote
- ✅ Reconfigure integration if issue persists

---

## Supported Camera Types

This integration works with **any** device that provides HTTP/HTTPS snapshot URLs:

### IP Cameras
- Reolink (all models)
- Hikvision (all models)
- Dahua (all models)
- Axis (all models)
- Amcrest (all models)
- Foscam (all models)
- TP-Link/Tapo
- Wyze (with RTSP firmware)
- And virtually any other IP camera

### NVR/DVR Systems
- Blue Iris
- Synology Surveillance Station
- QNAP Surveillance
- UniFi Protect
- Milestone XProtect
- Genetec Security Center
- Any NVR with HTTP API

### Home Automation Platforms
- Home Assistant camera entities (via proxy)
- Frigate NVR
- MotionEye
- ZoneMinder
- iSpy/Agent DVR

### Video Doorbells
- Ring (via Home Assistant)
- Nest (via Home Assistant)
- Arlo (via Home Assistant)
- Eufy (via Home Assistant)

---

## Technical Details

### Integration Specifications

| Feature | Value |
|---------|-------|
| Refresh Rate | 10 seconds (fixed) |
| Image Format | JPEG/PNG |
| Max Image Size | 80KB (auto-optimized) |
| Target Resolution | 320x240 (optimized for remote) |
| Max Cameras | 50 per integration instance |
| SSL Support | Yes (including self-signed) |
| Authentication | Embedded in URL |

### Network Requirements

- HTTP/HTTPS access to cameras
- Port access to camera snapshot endpoints
- No special firewall rules needed
- mDNS discovery supported

### Resource Usage

- **Idle**: Minimal (no active connections)
- **Viewing**: One HTTP request every 10 seconds
- **Multiple Cameras**: Only active camera pulls data
- **Auto-stop**: Stops pulling when entity is OFF or not viewing

---

## Advanced Configuration

### Multiple Integration Instances

You can install multiple instances of this integration:
- Each instance supports up to 50 cameras
- Useful for organizing cameras by location/type
- Each instance appears as a separate entity

### Docker Environment Variables

```yaml
environment:
  - UC_CONFIG_HOME=/data              # Config file location
  - UC_INTEGRATION_INTERFACE=0.0.0.0  # Network interface
  - UC_INTEGRATION_HTTP_PORT=9092     # Integration port
  - UC_DISABLE_MDNS_PUBLISH=false     # mDNS discovery
```

### Development Mode

Run locally for testing:
```bash
python -m uc_intg_cctv.driver
```

Configuration saves to: `./config.json` (project root)

### Reconfiguration

To change camera settings:
1. Go to Remote Web Configurator
2. Select integration
3. Click **Reconfigure**
4. Update camera settings
5. Save

**Note**: Reconfiguration replaces existing cameras completely.

---

## Security Considerations

### URL Security

**⚠️ IMPORTANT**: Snapshot URLs often contain credentials in plain text.

**Best Practices**:
- Use dedicated camera user accounts with minimal permissions
- Don't use admin credentials in URLs
- Create "snapshot-only" users if camera supports it
- Use HTTPS when possible
- Secure your Remote's network access

### Network Security

- Place cameras on isolated VLAN if possible
- Use firewall rules to restrict camera access
- Keep camera firmware updated
- Change default passwords
- Disable unused camera features/ports

---

## Support

### Getting Help

- **GitHub Issues**: [Report bugs or request features](https://github.com/mase1981/uc-intg-cctv/issues)
- **GitHub Discussions**: [Ask questions and share tips](https://github.com/mase1981/uc-intg-cctv/discussions)
- **Discord**: best to join Unfolded  Circle Discord Channel

### Before Reporting Issues

Please provide:
1. Integration version
2. Remote model (Remote 2 or 3)
3. Camera brand/model
4. Snapshot URL format (mask credentials)
5. Error messages from logs
6. Steps to reproduce

### Logs Location

**Development**:
```
Terminal/console output
```

**Docker**:
```bash
docker logs uc-intg-cctv
```

---


## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## License

This project is licensed under the **Mozilla Public License 2.0 (MPL-2.0)**.

See [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Unfolded Circle** for the amazing Remote 2/3 hardware and ucapi framework
- **Community contributors** who tested and provided feedback
- **Camera manufacturers** whose APIs made this integration possible

---

## Disclaimer

This integration is provided "as is" without warranty of any kind. The author is not responsible for any damage or issues arising from its use. Always test with non-critical cameras first.

---

**Made with ❤️ by [Meir Miyara](https://github.com/mase1981)**

*If this integration helps you, please consider [sponsoring](https://github.com/sponsors/mase1981)! 🙏*