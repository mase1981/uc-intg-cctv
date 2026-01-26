# Security Camera Integration for Unfolded Circle Remote 2/3

Universal security camera integration that displays camera snapshots directly on your remote's screen with automatic refresh. Works with **any camera or NVR system** that provides an HTTP/HTTPS snapshot URL.

[![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-cctv?style=flat-square)](https://github.com/mase1981/uc-intg-cctv/releases)
![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)
[![GitHub Issues](https://img.shields.io/github/issues/mase1981/uc-intg-cctv?style=flat-square)](https://github.com/mase1981/uc-intg-cctv/issues)
[![GitHub Discussions](https://img.shields.io/github/discussions/mase1981/uc-intg-cctv?style=flat-square)](https://github.com/mase1981/uc-intg-cctv/discussions)
![cctv](https://img.shields.io/badge/Security-Cameras-red)
[![Community Forum](https://img.shields.io/badge/community-forum-blue?style=flat-square)](https://unfolded.community/)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-cctv/total?style=flat-square)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg?style=flat-square)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA&style=flat-square)](https://github.com/sponsors/mase1981)

---

## ❤️ Support Development ❤️

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

Your support helps maintain this integration. Thank you! ❤️

---

## Features

### Key Features

✅ **Universal Compatibility** - Works with ANY camera or NVR (Reolink, Hikvision, Dahua, Synology, Blue Iris, Amcrest, Axis, etc.)
✅ **Simple Setup** - Just provide camera name and snapshot URL
✅ **Multi-Camera Support** - Support for up to 50 cameras in a single integration entity
✅ **Automatic Refresh** - 10-second snapshot updates when viewing
✅ **Self-Signed SSL Support** - Works with HTTPS cameras using self-signed certificates
✅ **Resource Efficient** - Automatically stops pulling snapshots when not viewing
✅ **Easy Source Switching** - Change between cameras with the source selector
✅ **Reboot Persistent** - Configuration survives remote reboots

### Requirements

#### Hardware
- Unfolded Circle Remote 2 or Remote 3
- IP cameras or NVR system with HTTP/HTTPS snapshot capability
- Network connectivity between Remote and cameras

#### Camera Requirements
Your camera or NVR **must provide**:
- HTTP or HTTPS snapshot URL that returns a JPEG or PNG image
- Network accessibility from the Remote
- Authentication (if required) embedded in the URL

### CRITICAL - Testing Your Camera URL

**CRITICAL**: Before adding cameras to the integration, test your snapshot URL in a web browser:

You must find your specific camera absolute path URL. Without first validating you can actually see your camera image via your browser, it will 100% guarantee to not work in this integration.

1. Open your browser (Chrome, Firefox, Edge, Safari)
2. Paste your complete snapshot URL (including username/password if needed)
3. You should see a **single still image** (NOT a video stream)
4. The image should load each time you refresh the page

**Example of what you should see:**
- ✅ **Correct**: A JPEG/PNG image that loads instantly
- ❌ **Incorrect**: Video player, streaming video, or error message

If you see a video stream or player instead of a static image, you need to find your camera's **snapshot endpoint**, not the streaming URL.

## Installation

### Option 1: Remote Web Interface (Recommended)

1. Navigate to the [**Releases**](https://github.com/mase1981/uc-intg-cctv/releases) page
2. Download the latest `uc-intg-cctv-<version>-aarch64.tar.gz` file
3. Open your remote's web interface (`http://your-remote-ip`)
4. Go to **Settings** → **Integrations** → **Add Integration**
5. Click **Upload** and select the downloaded `.tar.gz` file

### Option 2: Docker (Advanced Users)

The integration is available as a pre-built Docker image from GitHub Container Registry:

**Docker Compose:**
```yaml
services:
  uc-intg-cctv:
    image: ghcr.io/mase1981/uc-intg-cctv:latest
    container_name: uc-intg-cctv
    network_mode: host
    volumes:
      - </local/path>:/data
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_HTTP_PORT=9092
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - PYTHONPATH=/app
    restart: unless-stopped
```

**Docker Run:**
```bash
docker run -d --name uc-cctv --restart unless-stopped --network host -v cctv-config:/app/config -e UC_CONFIG_HOME=/app/config -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9092 -e PYTHONPATH=/app ghcr.io/mase1981/uc-intg-cctv:latest
```

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

## Using the Integration

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

## Credits

- **Developer**: Meir Miyara
- **Unfolded Circle**: Remote 2/3 integration framework (ucapi)
- **Camera Manufacturers**: For providing HTTP/HTTPS snapshot APIs
- **Community**: Testing and feedback from UC community

## License

This project is licensed under the Mozilla Public License 2.0 (MPL-2.0) - see LICENSE file for details.

## Support & Community

- **GitHub Issues**: [Report bugs and request features](https://github.com/mase1981/uc-intg-cctv/issues)
- **GitHub Discussions**: [Community discussions](https://github.com/mase1981/uc-intg-cctv/discussions)
- **UC Community Forum**: [General discussion and support](https://unfolded.community/)
- **Developer**: [Meir Miyara](https://www.linkedin.com/in/meirmiyara)

---

**Made with ❤️ for the Unfolded Circle Community**

**Thank You**: Meir Miyara
