# Security Camera Integration for Unfolded Circle Remote 2/3

Display camera snapshots directly on your remote's screen with automatic refresh. Supports **Synology Surveillance Station** with auto-discovery and **any camera or NVR** that provides an HTTP/HTTPS snapshot URL.

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

## Support Development

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

---

## Features

- **Synology Surveillance Station** - Auto-discovers all cameras, supports both H.264 and H.265 codecs, 2FA authentication
- **Manual URL** - Works with any camera or NVR (Reolink, Hikvision, Dahua, Blue Iris, Amcrest, Axis, UniFi, etc.)
- **Multi-Camera** - Up to 50 cameras per integration, switch via source selector or dedicated select entity
- **Auto Refresh** - 6-second snapshot updates while viewing
- **Reboot Persistent** - Survives remote reboots with automatic reconnection
- **Self-Signed SSL** - Works with HTTPS cameras using self-signed certificates
- **Resource Efficient** - Stops pulling snapshots when not viewing

## Requirements

- Unfolded Circle Remote 2 or Remote 3
- For Synology: Surveillance Station installed on your NAS
- For Manual: IP cameras or NVR with HTTP/HTTPS snapshot URLs accessible from the Remote

## Installation

### Option 1: Upload to Remote (Recommended)

1. Download the latest `uc-intg-cctv-<version>-aarch64.tar.gz` from [Releases](https://github.com/mase1981/uc-intg-cctv/releases)
2. Open your remote's web interface (`http://your-remote-ip`)
3. Go to **Settings** > **Integrations** > **Add Integration**
4. Click **Upload** and select the downloaded file

### Option 2: Docker

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
docker run -d --name uc-cctv --restart unless-stopped --network host -v cctv-config:/data -e UC_CONFIG_HOME=/data -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9092 -e PYTHONPATH=/app ghcr.io/mase1981/uc-intg-cctv:latest
```

## Setup

### Synology Surveillance Station

1. Add the integration on your Remote
2. Select **Synology** as source type
3. Enter your NAS connection details:
   - **Host**: NAS IP address (e.g., `192.168.1.100`)
   - **Port**: Web interface port (default: 5000 HTTP, 5001 HTTPS)
   - **HTTPS**: Enable if using HTTPS
   - **Username/Password**: Synology account with Surveillance Station access
   - **2FA Code**: If two-factor authentication is enabled
4. All cameras are auto-discovered with names from Surveillance Station
5. H.264 cameras use Synology's snapshot API, H.265 cameras use RTSP frame extraction

### Manual URL

1. Add the integration on your Remote
2. Select **Manual** as source type
3. Enter the number of cameras
4. For each camera provide a name and snapshot URL

**Test your URL first** - paste it in a browser, you should see a still JPEG image (not a video stream).

#### Example Snapshot URLs

| Brand | URL Format |
|-------|-----------|
| Reolink | `https://IP/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=abc&user=admin&password=pass` |
| Hikvision | `http://IP/ISAPI/Streaming/channels/101/picture?auth=base64` |
| Dahua | `http://IP/cgi-bin/snapshot.cgi?channel=1&user=admin&password=pass` |
| Amcrest | `http://IP/cgi-bin/snapshot.cgi?channel=0&user=admin&password=pass` |
| Axis | `http://IP/axis-cgi/jpg/image.cgi?resolution=640x480` |
| Blue Iris | `http://IP:81/image/CAM1?q=100&s=100&user=admin&pw=pass` |
| UniFi | `https://IP/proxy/protect/api/cameras/ID/snapshot?ts=0` |

## Usage

- **ON** - Start viewing the selected camera
- **OFF** - Stop viewing
- **Source Selector** - Switch between cameras (snapshot loads immediately)
- **Camera Select Entity** - Dedicated entity with next/previous camera support

Snapshots refresh every 6 seconds while viewing. Tapping the screen (play/pause) is suppressed as this is a snapshot viewer, not a video player.

## Entities Created

| Entity | Type | Purpose |
|--------|------|---------|
| Media Player | `media_player` | Displays camera snapshots on screen |
| Camera Select | `select` | Switch cameras with next/previous support |

## License

Mozilla Public License 2.0 (MPL-2.0) - see LICENSE file.

## Support & Community

- [GitHub Issues](https://github.com/mase1981/uc-intg-cctv/issues) - Bug reports and feature requests
- [GitHub Discussions](https://github.com/mase1981/uc-intg-cctv/discussions) - Community discussions
- [UC Community Forum](https://unfolded.community/) - General support
