#!/usr/bin/env bash
# ============================================================
#  StreamStation Installer
#  Run as root or with sudo:
#    curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/StreamStation/main/install.sh | bash
#  Or after cloning:
#    sudo bash install.sh
# ============================================================

set -e

REPO_URL="https://github.com/GuinnessStache/StreamStation.git"
INSTALL_DIR="/opt/streamstation"
SERVICE_USER="pi"
VENV_DIR="$INSTALL_DIR/venv"
PYTHON="python3"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}▶ $1${NC}"; }
ok()     { echo -e "  ${GREEN}✓ $1${NC}"; }
warn()   { echo -e "  ${YELLOW}⚠ $1${NC}"; }
err()    { echo -e "  ${RED}✗ $1${NC}"; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "Please run as root: sudo bash install.sh"
fi

echo -e "\n${BOLD}${CYAN}"
echo "  ┌─────────────────────────────────────┐"
echo "  │        STREAMSTATION INSTALLER       │"
echo "  │   Live Stream Cable Box for Pi       │"
echo "  └─────────────────────────────────────┘"
echo -e "${NC}"

# ── Detect user ───────────────────────────────────────────────────────────────
if id "pi" &>/dev/null; then
  SERVICE_USER="pi"
elif [[ -n "$SUDO_USER" ]]; then
  SERVICE_USER="$SUDO_USER"
fi
ok "Running services as: $SERVICE_USER"

# ── System update ─────────────────────────────────────────────────────────────
banner "Updating system packages"
apt-get update -qq
apt-get upgrade -y -qq
ok "System up to date"

# ── Install system dependencies ───────────────────────────────────────────────
banner "Installing system dependencies"
PKGS=(
  mpv
  python3 python3-pip python3-venv python3-dev
  git ffmpeg curl
  avahi-daemon avahi-utils        # mDNS: streamstation.local
  openssh-server                  # SSH access
  python3-rpi.gpio                # GPIO (Pi only, may skip on non-Pi)
  i2c-tools                       # I2C for LCD display
  libjpeg-dev libpng-dev          # image deps
)
for pkg in "${PKGS[@]}"; do
  apt-get install -y -qq "$pkg" 2>/dev/null && ok "$pkg" || warn "$pkg (skipped)"
done

# ── Enable services ───────────────────────────────────────────────────────────
banner "Enabling system services"
systemctl enable --now avahi-daemon  && ok "avahi-daemon (mDNS)"
systemctl enable --now ssh           && ok "SSH"
# Enable I2C on Pi
if command -v raspi-config &>/dev/null; then
  raspi-config nonint do_i2c 0 && ok "I2C enabled via raspi-config"
fi

# ── Clone or update repo ──────────────────────────────────────────────────────
banner "Installing StreamStation"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  warn "Existing install found — pulling latest"
  cd "$INSTALL_DIR" && git pull -q
  ok "Updated to latest"
elif [[ -f "$(dirname "$0")/streamstation.py" ]]; then
  # Running from inside the already-cloned repo
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
    cp -r "$SCRIPT_DIR" "$INSTALL_DIR"
    ok "Copied local repo to $INSTALL_DIR"
  else
    ok "Already in $INSTALL_DIR"
  fi
else
  git clone -q "$REPO_URL" "$INSTALL_DIR"
  ok "Cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Python virtual environment ────────────────────────────────────────────────
banner "Setting up Python environment"
$PYTHON -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

PY_PKGS=(
  flask
  flask-socketio
  "simple-websocket"
  requests
  yt-dlp
  tm1637
  RPLCD
  smbus2
)
for pkg in "${PY_PKGS[@]}"; do
  pip install -q "$pkg" && ok "$pkg" || warn "$pkg (failed — non-critical)"
done

# ── Runtime directory ─────────────────────────────────────────────────────────
banner "Creating runtime directories"
mkdir -p "$INSTALL_DIR/runtime"
touch "$INSTALL_DIR/runtime/current_channel.json"
echo '{"channel":null,"state":"idle","name":null,"updated_at":null}' \
  > "$INSTALL_DIR/runtime/current_channel.json"
ok "runtime/"

# ── Permissions ───────────────────────────────────────────────────────────────
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
ok "Ownership set to $SERVICE_USER"

# ── Set hostname ──────────────────────────────────────────────────────────────
banner "Configuring hostname"
CURRENT_HOST=$(hostname)
if [[ "$CURRENT_HOST" != "streamstation" ]]; then
  hostnamectl set-hostname streamstation
  sed -i "s/$CURRENT_HOST/streamstation/g" /etc/hosts 2>/dev/null || true
  ok "Hostname set to: streamstation"
  ok "Access at: http://streamstation.local:8080"
else
  ok "Hostname already: streamstation"
fi

# ── Install systemd services ──────────────────────────────────────────────────
banner "Installing systemd services"
SERVICES=(
  streamstation.service
  streamstation-web.service
  streamstation-display.service
  streamstation-keypad.service
)
for svc in "${SERVICES[@]}"; do
  # Patch the user in service files
  sed -i "s/User=pi/User=$SERVICE_USER/g" "$INSTALL_DIR/services/$svc"
  cp "$INSTALL_DIR/services/$svc" "/etc/systemd/system/$svc"
  ok "Installed: $svc"
done

systemctl daemon-reload

# Enable core services (display/keypad optional)
systemctl enable streamstation.service
systemctl enable streamstation-web.service
ok "Core services enabled (engine + web)"

echo ""
warn "Hardware display service not auto-enabled (enable when hardware connected):"
echo "    sudo systemctl enable --now streamstation-display"
warn "Hardware keypad service not auto-enabled:"
echo "    sudo systemctl enable --now streamstation-keypad"

# ── Start services ────────────────────────────────────────────────────────────
banner "Starting StreamStation"
systemctl restart streamstation.service     && ok "Engine started" || warn "Engine failed to start — check: journalctl -u streamstation"
systemctl restart streamstation-web.service && ok "Web server started" || warn "Web server failed — check: journalctl -u streamstation-web"

# ── Detect IP ─────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     STREAMSTATION INSTALLED SUCCESSFULLY  ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}Web Interface:${NC}"
echo -e "    Manage:  ${GREEN}http://$IP:8080/manage${NC}"
echo -e "    Guide:   ${GREEN}http://$IP:8080/guide${NC}"
echo -e "    Remote:  ${GREEN}http://$IP:8080/remote${NC}  ← open on your phone"
echo ""
echo -e "  ${BOLD}mDNS (same network):${NC}"
echo -e "    ${GREEN}http://streamstation.local:8080${NC}"
echo ""
echo -e "  ${BOLD}SSH Access:${NC}"
echo -e "    ${GREEN}ssh $SERVICE_USER@$IP${NC}"
echo ""
echo -e "  ${BOLD}Logs:${NC}"
echo -e "    Engine:  ${CYAN}journalctl -fu streamstation${NC}"
echo -e "    Web:     ${CYAN}journalctl -fu streamstation-web${NC}"
echo ""
echo -e "  ${BOLD}Manage services:${NC}"
echo -e "    ${CYAN}sudo systemctl restart streamstation${NC}"
echo -e "    ${CYAN}sudo systemctl status streamstation-web${NC}"
echo ""
echo -e "  ${YELLOW}Add channels at /manage, then enjoy your cable box!${NC}"
echo ""
