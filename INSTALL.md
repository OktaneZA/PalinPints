# PaliPints — Pi setup from scratch

End-to-end guide: a blank SD card → a TV showing the draft list, with remote admin from your laptop.

---

## 1. Hardware checklist

- Raspberry Pi 4 (2 GB minimum, 4 GB recommended) or Pi 5
- microSD card, 32 GB+, Class 10 / A1 or better
- Official Pi power supply (USB-C, 5 V / 3 A for Pi 4, 5 A for Pi 5)
- HDMI cable (micro-HDMI to HDMI for Pi 4 / 5)
- TV with an HDMI input (mounted horizontally — the display is designed for 1920×1080 landscape)
- Network: WiFi or Ethernet on the Pi
- A laptop on the same network for first-time setup and admin access

Optional but useful for first boot: keyboard + mouse, but not required if you use SSH.

---

## 2. Flash the SD card with Raspberry Pi Imager

### 2.1 Install the Imager
Download from https://www.raspberrypi.com/software/ (Windows / macOS / Linux) and install it.

### 2.2 Pick the OS
Open Raspberry Pi Imager.

- **Device**: choose your model (e.g. *Raspberry Pi 4*).
- **Operating System** → *Raspberry Pi OS (64-bit)* — the **Bookworm with desktop** image. (The "Lite" variant won't work because the kiosk uses Chromium with a desktop session.)
- **Storage**: select your SD card.

### 2.3 Apply OS customisation (this is where WiFi goes)
Click **Next**, then **Edit Settings** when it asks if you want to apply OS customisation. This is the step that bakes WiFi credentials, hostname, and SSH access into the image so the Pi works on first boot without a keyboard.

In the *General* tab:
- **Set hostname**: `palipints` (Pi will be reachable as `palipints.local`)
- **Set username and password**: pick any username (e.g. `pi`) and a strong password — note it down
- **Configure wireless LAN**:
  - SSID: your WiFi network name
  - Password: your WiFi password
  - Wireless LAN country: e.g. *GB*
- **Locale settings**: timezone *Europe/London*, keyboard layout *gb*

In the *Services* tab:
- **Enable SSH**: tick it. Choose *Use password authentication* (or paste an SSH public key if you prefer).

Click **Save**, then **Yes** to apply, then confirm the SD card erase warning. Wait for write + verify (~5 minutes).

### 2.4 Boot the Pi
Eject the SD card, insert into the Pi, connect HDMI to the TV, then power on. First boot takes 2–3 minutes (it resizes the filesystem and applies the customisation). It'll connect to your WiFi automatically.

---

## 3. Connect to the Pi

From your laptop (same network):

```bash
ssh pi@palipints.local
```

(Replace `pi` with whatever username you chose. If `palipints.local` doesn't resolve on Windows, install [Bonjour Print Services](https://support.apple.com/en-us/106380) or use the Pi's IP address directly — find it via your router's admin page or `ping palipints.local`.)

Confirm the host fingerprint, enter the password you set in the Imager, and you should land in `~`.

---

## 4. Install PaliPints

In the SSH session:

```bash
# Get the latest OS patches first (recommended, ~5 min)
sudo apt update && sudo apt full-upgrade -y

# Clone and install
git clone https://github.com/OktaneZA/PalinPints.git ~/PaliPints
cd ~/PaliPints
bash scripts/install.sh
```

`install.sh` does:
1. `apt install` of Python, Pillow build deps, Chromium, supporting tools
2. Creates a Python virtualenv in `~/PaliPints/.venv` and installs `requirements.txt`
3. Installs a `systemd --user` service (`palipints.service`) that runs the Flask app on port 8080 and restarts on failure
4. Enables user lingering so the service starts at boot without anyone logging in
5. Drops a Chromium kiosk launcher into `~/.config/autostart/` so the display appears on every boot
6. Optionally sets up Raspberry Pi Connect for browser-based remote management (see §6)

When it finishes, the script prints both URLs:

- **Admin (LAN)**: `http://palipints.local:8080/admin` or `http://<pi-ip>:8080/admin`
- **Display**: `http://localhost:8080/` (auto-launches in Chromium kiosk on next reboot)

### Brand fonts (Palindrome 4 / 5 / 6 only)

The themes Palindrome 4, 5, and 6 use the commercial typeface **PP Fragment Glare ExtraBold**. The git repo ships a copy under `app/static/fonts/` for the operator's convenience, but **anyone forking this repo needs to source their own copy under their own licence**:

- Free personal-use trial (sign-up required): https://pangrampangram.com/products/fragment-glare
- Commercial licence (required for any customer-facing display): same page, "Buy" tab

If the `.otf` is missing, themes 4-6 fall back to the locally-bundled `Archivo Black` automatically — the app still works, just without the licensed brand typography. All the other typefaces (Bebas Neue, Inter, Playfair Display, Caveat, Special Elite, Archivo Black, Alegreya Sans) are open-source OFL fonts bundled in the repo too — no internet required to render any theme.

See [`app/static/fonts/README.md`](app/static/fonts/README.md) for the full sourcing + licensing breakdown.

### Offline operation

**The kiosk is fully offline-capable for normal day-to-day operation.** The display polls `/api/state` over the LAN, all images are cached on disk, all fonts are self-hosted (~1 MB under `app/static/fonts/`), and the SQLite DB is local. The Pi can be unplugged from the internet for days and the TV keeps showing taps, holidays, specials, events, and QR codes correctly.

The features that **do** need internet are:

- **Search the web** button on the Tap page (Untappd scrape)
- **Auto-detect location** button on the Settings page (IP geolocation)
- **Weekly sunrise/sunset refresh** for the Day/night auto-switch — the result is cached for 7 days so an outage that long would have to elapse before the day/night cutover times got stale
- **External beer-library sync** if configured against a network source

Everything else, including all typography, works untethered. This is intentional — the brewery shouldn't be at the mercy of a CDN or ISP for the menu board to look right.

### Reboot

Reboot once to bring up the kiosk:

```bash
sudo reboot
```

---

## 5. Updating

When new commits land on `main`, SSH into the Pi and run:

```bash
cd ~/PaliPints
bash scripts/update.sh
```

This does `git pull --ff-only`, refreshes Python deps if `requirements.txt` changed, and restarts the service. It does *not* restart Chromium — no need, the page polls for changes and reloads itself within 5 seconds.

If a CSS/HTML change doesn't appear on the TV, force a Chromium reload by either rebooting the Pi or:

```bash
DISPLAY=:0 xdotool search --name "Chromium" key --window %@ ctrl+shift+r
```

---

## 6. Raspberry Pi Connect (optional, recommended)

[Raspberry Pi Connect](https://www.raspberrypi.com/documentation/services/connect.html) is a free service that gives you remote shell + screen sharing through a browser — handy for managing the kiosk from anywhere without exposing SSH to the internet.

`install.sh` installs the `rpi-connect` package automatically (set `SKIP_RPI_CONNECT=1` if you don't want it). To complete the sign-in, run on the Pi:

```bash
rpi-connect signin
```

It prints a URL. Open the URL on any device, sign in with a free Raspberry Pi ID account, and the Pi will appear at https://connect.raspberrypi.com/devices. From there you can open a remote shell or share the kiosk's screen.

---

## 7. Changing the WiFi SSID / password

Raspberry Pi OS Bookworm uses **NetworkManager** by default. There are three easy ways to change networks. Pick whichever you prefer.

### 7.1 Interactive menu (easiest, no commands to memorise)

```bash
sudo nmtui
```

Choose *Edit a connection* to update an existing network, or *Activate a connection* to join a new one. Use Tab / arrows to navigate, *OK* to save.

### 7.2 One-liner for a new network

```bash
sudo nmcli device wifi list                  # see what's nearby
sudo nmcli device wifi connect "MySSID" password "mypassword"
```

This both creates the connection profile and connects. Future boots reconnect automatically.

### 7.3 Edit the saved profile

If you want to change the password on an existing saved network:

```bash
sudo nmcli connection show                                        # find the name
sudo nmcli connection modify "<NAME>" wifi-sec.psk "newpassword"
sudo nmcli connection up "<NAME>"
```

### 7.4 Last resort: re-flash the SD card

If the Pi is in a venue you can't easily reach and WiFi has changed, the lowest-friction option is to pop the SD card out, plug it into your laptop, open Raspberry Pi Imager, choose *Use latest setup* with the new WiFi credentials in OS customisation, and overwrite. You'll lose the local DB and uploaded brewery logos, so back up `~/PaliPints/data/` first if you've configured anything important.

---

## 8. Service management cheat-sheet

```bash
# Tail the Flask app log
journalctl --user -u palipints.service -f

# Status
systemctl --user status palipints.service

# Restart the app (after editing settings or pulling code manually)
systemctl --user restart palipints.service

# Stop / disable
systemctl --user stop palipints.service
systemctl --user disable palipints.service
```

The kiosk Chromium window is started by `~/.config/autostart/palipints-kiosk.desktop`. If the display freezes:

```bash
pkill chromium
DISPLAY=:0 bash ~/palipints-kiosk.sh &
```

---

## 9. Troubleshooting

**Pi never appears on the network**
The customisation didn't take. Re-flash the SD card and double-check the WiFi country code, SSID (case-sensitive), and password in *Edit Settings*.

**Display stays black after reboot**
- TV is set to the wrong HDMI input.
- Pi 4 needs the cable in the HDMI port closest to the USB-C power socket (HDMI0).
- Force a known good resolution by editing `/boot/firmware/config.txt`:
  ```
  hdmi_force_hotplug=1
  hdmi_group=2
  hdmi_mode=82          # 1080p @ 60 Hz
  ```
  Then `sudo reboot`.

**Display shows the page but Chromium isn't fullscreen**
The autostart desktop file didn't fire. SSH in and run `bash ~/palipints-kiosk.sh` manually to confirm the script works, then check that the Pi boots into a desktop session (not console) — `sudo raspi-config` → *System Options* → *Boot / Auto Login* → *Desktop Autologin*.

**Admin URL works but display URL hangs**
Flask app crashed. Check the log: `journalctl --user -u palipints.service -n 100`.

**Chromium uses too much RAM on a 2 GB Pi**
Increase the swap in `/etc/dphys-swapfile` (`CONF_SWAPSIZE=1024`) and `sudo systemctl restart dphys-swapfile`. Long-term: a 4 GB Pi is more comfortable.

---

## 10. Second monitor (Pi Zero 2 W client)

To add a second TV showing the same draft list, point a **second Pi** at the primary Pi's URL. This Pi runs nothing but a Chromium kiosk — no Flask, no database, no extra config to manage on the brewery side.

The reference hardware for the second screen is a **Raspberry Pi Zero 2 W** (cheap, low-power, mini-HDMI), but any Pi works the same way.

### 10.1 Hardware checklist

- Raspberry Pi Zero 2 W (Zero 2 W has a quad-core CPU + 512 MB RAM — the original Zero is too slow for Chromium)
- microSD card, 16 GB+, Class 10 / A1 or better
- USB-C **micro-USB** power supply (the Zero takes micro-USB, not USB-C — easy to get wrong)
- **mini-HDMI to HDMI** cable or adapter (the Zero 2 W has a mini-HDMI port; a regular HDMI cable won't fit)
- Second TV with an HDMI input
- WiFi reachable from the same network as the primary Pi (the Zero 2 W has no Ethernet)

### 10.2 Flash the SD card

Exactly the same flow as §2 with two changes when you click *Edit Settings* in Raspberry Pi Imager:

- **Set hostname**: `palipints-client` (so it doesn't collide with the primary's `palipints`)
- Everything else (username, WiFi, locale, SSH) — same as the primary.

Boot the Zero 2 W with HDMI plugged into the second TV.

### 10.3 SSH in and install

```bash
ssh pi@palipints-client.local
sudo apt update && sudo apt full-upgrade -y
git clone https://github.com/OktaneZA/PalinPints.git ~/PaliPints
cd ~/PaliPints
bash scripts/install-client.sh
```

The installer prompts for the **primary Pi's URL**. Defaults to `http://palipints.local:8080/`, which works on most home LANs via mDNS. If your router blocks mDNS or you prefer pinning to an IP, paste `http://<primary-pi-ip>:8080/` instead — find the primary's IP via your router's admin page or `ssh pi@palipints.local 'hostname -I'`.

The installer skips Python, Flask, the venv, and the systemd service — only Chromium and a kiosk autostart are configured. Takes about a minute.

Reboot to bring up the kiosk:

```bash
sudo reboot
```

Both TVs should now show the identical PaliPints display.

### 10.4 Changing the primary URL later

The URL the kiosk targets lives in **`~/.palipints-client-url`** on the client. To repoint:

```bash
ssh pi@palipints-client.local
nano ~/.palipints-client-url        # edit the URL line, save
sudo reboot                          # or: pkill chromium; DISPLAY=:0 bash ~/palipints-kiosk.sh &
```

The `install-client.sh` script does not need to be re-run.

### 10.5 Updating

```bash
ssh pi@palipints-client.local
cd ~/PaliPints
bash scripts/update.sh
```

`update.sh` auto-detects the client install (no `.venv` + `~/.palipints-client-url` present) and refreshes only the kiosk launcher script. No code refresh needed — the display HTML/CSS/JS is fetched from the primary on every boot.

### 10.6 Page rotation drift

The two TVs run their own Chromium instances with independent page-rotation timers, so on long tap lists the screens can drift out of sync over time (e.g. TV A on page 2, TV B on page 1). This is expected — synced rotation is on the roadmap but not yet implemented. If drift bothers you, set `Beers per page` high enough to avoid pagination, or reboot both Pis together so they restart in lockstep.

### 10.7 Troubleshooting

**Black screen / Chromium shows "This site can't be reached"**
The client can't reach the primary. SSH in and:

```bash
cat ~/.palipints-client-url                # check the configured URL
curl -fsS "$(cat ~/.palipints-client-url)" -o /dev/null && echo OK || echo UNREACHABLE
ping -c 3 palipints.local                  # mDNS resolution test
```

If `ping` fails on `palipints.local` but the primary is up, your network is blocking mDNS — change the URL file to use the primary's IP address.

**Chromium is sluggish on the Zero 2 W**
The Zero 2 W has only 512 MB RAM. The display page is moderate but Chromium itself is heavy. If it stutters during page rotation:
- Increase swap (`/etc/dphys-swapfile` → `CONF_SWAPSIZE=1024` → `sudo systemctl restart dphys-swapfile`).
- Bump `Beers per page` on the Settings page so fewer rotations happen.
- Long-term: a Pi 3 / Pi 4 makes a happier client.

**Updating the primary doesn't change the client display**
Press `Ctrl+Shift+R` in the kiosk window (via `xdotool`) or reboot the client. The display polls `/api/state` every 5 s and re-renders on state changes, but a full page reload picks up any CSS/HTML edits too.

```bash
ssh pi@palipints-client.local
DISPLAY=:0 xdotool search --name "Chromium" key --window %@ ctrl+shift+r
```
