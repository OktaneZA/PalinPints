# PalinPints — Pi setup from scratch

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
- **Set hostname**: `palinpints` (Pi will be reachable as `palinpints.local`)
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
ssh pi@palinpints.local
```

(Replace `pi` with whatever username you chose. If `palinpints.local` doesn't resolve on Windows, install [Bonjour Print Services](https://support.apple.com/en-us/106380) or use the Pi's IP address directly — find it via your router's admin page or `ping palinpints.local`.)

Confirm the host fingerprint, enter the password you set in the Imager, and you should land in `~`.

---

## 4. Install PalinPints

In the SSH session:

```bash
# Get the latest OS patches first (recommended, ~5 min)
sudo apt update && sudo apt full-upgrade -y

# Clone and install
git clone https://github.com/OktaneZA/PalinPints.git ~/PalinPints
cd ~/PalinPints
bash scripts/install.sh
```

`install.sh` does:
1. `apt install` of Python, Pillow build deps, Chromium, supporting tools
2. Creates a Python virtualenv in `~/PalinPints/.venv` and installs `requirements.txt`
3. Installs a `systemd --user` service (`palibeerview.service`) that runs the Flask app on port 8080 and restarts on failure
4. Enables user lingering so the service starts at boot without anyone logging in
5. Drops a Chromium kiosk launcher into `~/.config/autostart/` so the display appears on every boot
6. Optionally sets up Raspberry Pi Connect for browser-based remote management (see §6)

When it finishes, the script prints both URLs:

- **Admin (LAN)**: `http://palinpints.local:8080/admin` or `http://<pi-ip>:8080/admin`
- **Display**: `http://localhost:8080/` (auto-launches in Chromium kiosk on next reboot)

Reboot once to bring up the kiosk:

```bash
sudo reboot
```

---

## 5. Updating

When new commits land on `main`, SSH into the Pi and run:

```bash
cd ~/PalinPints
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

If the Pi is in a venue you can't easily reach and WiFi has changed, the lowest-friction option is to pop the SD card out, plug it into your laptop, open Raspberry Pi Imager, choose *Use latest setup* with the new WiFi credentials in OS customisation, and overwrite. You'll lose the local DB and uploaded brewery logos, so back up `~/PalinPints/data/` first if you've configured anything important.

---

## 8. Service management cheat-sheet

```bash
# Tail the Flask app log
journalctl --user -u palibeerview.service -f

# Status
systemctl --user status palibeerview.service

# Restart the app (after editing settings or pulling code manually)
systemctl --user restart palibeerview.service

# Stop / disable
systemctl --user stop palibeerview.service
systemctl --user disable palibeerview.service
```

The kiosk Chromium window is started by `~/.config/autostart/palinpints-kiosk.desktop`. If the display freezes:

```bash
pkill chromium
DISPLAY=:0 bash ~/palinpints-kiosk.sh &
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
The autostart desktop file didn't fire. SSH in and run `bash ~/palinpints-kiosk.sh` manually to confirm the script works, then check that the Pi boots into a desktop session (not console) — `sudo raspi-config` → *System Options* → *Boot / Auto Login* → *Desktop Autologin*.

**Admin URL works but display URL hangs**
Flask app crashed. Check the log: `journalctl --user -u palibeerview.service -n 100`.

**Chromium uses too much RAM on a 2 GB Pi**
Increase the swap in `/etc/dphys-swapfile` (`CONF_SWAPSIZE=1024`) and `sudo systemctl restart dphys-swapfile`. Long-term: a 4 GB Pi is more comfortable.
