# 📺 StreamStation

> A retro-style live streaming cable box for Raspberry Pi — inspired by [FieldStation42](https://github.com/shane-mason/FieldStation42), built for the internet age.

StreamStation turns a Raspberry Pi into a fully functional cable box that streams live internet content — news, sports, YouTube Live, Twitch, IPTV, and any direct HLS/M3U8 stream — presented through a retro cable TV experience complete with channel numbers, a classic TV guide, a phone remote, and optional physical hardware.

![StreamStation Web Remote](docs/remote-preview.png)

---

## ✨ Features

- **Live internet streams** — YouTube Live, Twitch, HLS/M3U8, RTMP, and 1000+ sites via yt-dlp
- **Channel management web UI** — add, edit, reorder, enable/disable channels from any browser
- **TV Guide** — retro grid-style channel guide accessible on your LAN
- **Phone remote** — mobile-first web remote that mimics a 1990s cable box remote
- **M3U playlist import** — bulk-import IPTV playlists with one paste or URL
- **Categories** — News, Sports, Entertainment, Weather, Movies, and custom categories
- **Physical hardware support** — TM1637 7-segment display and 4×4 matrix keypad
- **Stream health monitoring** — auto-retry on stream failure, fallback no-signal screen
- **One-command install** — full setup via a single shell script
- **SSH-ready** — full root-level access over SSH for advanced configuration

---

## 🚀 Quick Install

Flash **Raspberry Pi OS Lite (64-bit)** to your SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Enable SSH in the imager settings.

Then SSH in and run:

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/StreamStation/main/install.sh | sudo bash
```

That's it. The installer will:
1. Update the system
2. Install MPV, Python, ffmpeg, avahi (mDNS), SSH, and all dependencies
3. Clone StreamStation to `/opt/streamstation`
4. Create a Python virtual environment and install all pip packages
5. Set the hostname to `streamstation` (accessible as `streamstation.local`)
6. Install and start all systemd services

---

## 🌐 Web Interface

Once installed, open a browser on any device on the same network:

| Page | URL | Purpose |
|---|---|---|
| Manager | `http://streamstation.local:8080/manage` | Add/edit/delete channels |
| Guide | `http://streamstation.local:8080/guide` | TV guide grid |
| Remote | `http://streamstation.local:8080/remote` | Phone remote control |

> If mDNS doesn't work on your network, use the Pi's IP directly: `http://192.168.x.x:8080`

---

## 📱 Phone Remote

Open `http://streamstation.local:8080/remote` on any phone browser. No app needed.

**Controls:**
- **Number pad** — type a channel number (2-3 digits, auto-tunes after pause)
- **CH ▲ / CH ▼** — channel up/down
- **↩ LAST** — return to previous channel
- **VOL + / −** — volume control
- **MUTE** — toggle mute
- **INFO** — show current channel info overlay
- **Category buttons** — jump to first channel in a category
- **Channel list drawer** — full channel list, tap to tune

---

## ➕ Adding Channels

**Via Web UI (recommended):**
1. Go to `/manage`
2. Click **+ ADD CHANNEL**
3. Enter channel number, name, category, and stream URL
4. Click **TEST** to verify the stream is reachable
5. Click **SAVE CHANNEL**

**Via M3U Import:**
1. Click **⬇ IMPORT M3U**
2. Paste an M3U URL or raw playlist content
3. Click **IMPORT** — channels are added automatically

**Supported URL types:**
- Direct HLS: `https://example.com/stream.m3u8`
- Direct DASH: `https://example.com/manifest.mpd`
- YouTube Live: `https://www.youtube.com/watch?v=LIVE_VIDEO_ID`
- Twitch: `https://www.twitch.tv/channel_name`
- Any site supported by yt-dlp

**Via JSON (advanced):**

Edit `/opt/streamstation/streams/channels.json` directly:

```json
{
  "channels": [
    {
      "id": 10,
      "number": 10,
      "name": "My Stream",
      "category": "News",
      "url": "https://example.com/stream.m3u8",
      "logo": "",
      "enabled": true,
      "notes": ""
    }
  ]
}
```

---

## 🔧 Configuration

Edit `/opt/streamstation/config/system.json`:

```json
{
  "volume": 80,
  "fullscreen": true,
  "buffer_seconds": 10,
  "stream_retries": 3,
  "startup_channel": 2,
  "web": { "port": 8080 },
  "hardware": {
    "display_type": "tm1637",
    "tm1637_clk": 23,
    "tm1637_dio": 24,
    "keypad_rows": [5, 6, 13, 19],
    "keypad_cols": [12, 16, 20, 21]
  }
}
```

Or update via the API: `PUT http://streamstation.local:8080/api/config`

---

## 🔌 Hardware — 3D Printed Cable Box

### TM1637 7-Segment Display (Channel Number)

```
Pi GPIO → TM1637
3.3V    → VCC
GND     → GND
GPIO23  → CLK
GPIO24  → DIO
```

Enable the display service:
```bash
sudo systemctl enable --now streamstation-display
```

### 4×4 Matrix Keypad

Default GPIO pin mapping (BCM):

| Keypad | GPIO |
|--------|------|
| Row 1  | 5    |
| Row 2  | 6    |
| Row 3  | 13   |
| Row 4  | 19   |
| Col 1  | 12   |
| Col 2  | 16   |
| Col 3  | 20   |
| Col 4  | 21   |

**Keypad functions:**
- `0–9` → channel entry (type digits, auto-tunes after 2.5 seconds or 3 digits)
- `*` → channel down
- `#` → channel up
- `A` → last channel

Enable the keypad service:
```bash
sudo systemctl enable --now streamstation-keypad
```

Custom pins:
```bash
sudo systemctl edit streamstation-keypad
# Add: ExecStart=... --rows 5 6 13 19 --cols 12 16 20 21
```

### I2C LCD Display (optional)

Set `"display_type": "lcd"` in `system.json`. Wire your I2C LCD:
```
Pi GPIO → LCD I2C backpack
3.3V/5V → VCC
GND     → GND
GPIO2   → SDA
GPIO3   → SCL
```

Find your LCD's I2C address: `sudo i2cdetect -y 1`
Update `"lcd_address"` in config.

---

## 🛠️ Service Management

```bash
# Status
sudo systemctl status streamstation
sudo systemctl status streamstation-web

# Restart
sudo systemctl restart streamstation
sudo systemctl restart streamstation-web

# Logs (live)
journalctl -fu streamstation
journalctl -fu streamstation-web

# Manual channel control
cd /opt/streamstation
./venv/bin/python3 streamstation.py --tune 7
./venv/bin/python3 streamstation.py --up
./venv/bin/python3 streamstation.py --status
```

---

## 📡 REST API Reference

All endpoints at `http://streamstation.local:8080`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Current channel and engine state |
| POST | `/api/tune/{n}` | Tune to channel number |
| POST | `/api/channel/up` | Channel up |
| POST | `/api/channel/down` | Channel down |
| POST | `/api/channel/last` | Last channel |
| POST | `/api/volume/{0-100}` | Set volume |
| GET | `/api/channels` | All channels |
| POST | `/api/channels` | Add channel |
| PUT | `/api/channels/{id}` | Update channel |
| DELETE | `/api/channels/{id}` | Delete channel |
| POST | `/api/channels/{id}/toggle` | Enable/disable |
| POST | `/api/import/m3u` | Import M3U playlist |
| GET | `/api/categories` | All categories |
| POST | `/api/categories` | Add category |
| GET | `/api/config` | System config |
| PUT | `/api/config` | Update config |
| POST | `/api/test_stream` | Test if URL is reachable |

---

## 🔑 SSH Access

```bash
ssh pi@streamstation.local
# or
ssh pi@192.168.x.x
```

The install enables SSH automatically. Change the default password:
```bash
passwd
```

---

## 🐞 Troubleshooting

**No video output:**
- Check MPV is installed: `mpv --version`
- Verify HDMI output is connected before boot
- Check logs: `journalctl -fu streamstation`

**Stream won't play:**
- Test the URL: `POST /api/test_stream {"url": "..."}`
- Try resolving manually: `yt-dlp --get-url "YOUR_URL"`
- Some streams require yt-dlp cookies for geo-restricted content

**Web UI not loading:**
- Check web service: `sudo systemctl status streamstation-web`
- Verify firewall: `sudo ufw allow 8080` (if ufw enabled)

**mDNS not resolving:**
- Ensure avahi is running: `sudo systemctl status avahi-daemon`
- Try the IP address directly instead: `hostname -I`

**Display not working:**
- Check wiring against the pin table above
- Enable I2C: `sudo raspi-config → Interface Options → I2C`
- Find I2C devices: `sudo i2cdetect -y 1`

---

## 📁 Project Structure

```
StreamStation/
├── streamstation.py          # Channel engine daemon
├── install.sh                # One-command installer
├── requirements.txt          # Python dependencies
├── web/
│   ├── app.py                # Flask web server + REST API
│   ├── templates/
│   │   ├── manage.html       # Channel management UI
│   │   ├── guide.html        # TV Guide
│   │   └── remote.html       # Phone remote
│   └── static/
│       ├── css/              # Stylesheets
│       └── js/               # JavaScript
├── streams/
│   └── channels.json         # Channel database
├── config/
│   └── system.json           # System configuration
├── hardware/
│   ├── display.py            # TM1637 / LCD driver
│   └── keypad.py             # Matrix keypad driver
├── services/                 # systemd unit files
└── runtime/                  # Socket, status, logs (auto-created)
```

---

## 🤝 Contributing

Pull requests welcome. Please open an issue first for major changes.

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## Credits

Inspired by [FieldStation42](https://github.com/shane-mason/FieldStation42) by Shane Mason.
Stream playback powered by [MPV](https://mpv.io) and [yt-dlp](https://github.com/yt-dlp/yt-dlp).
