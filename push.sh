#!/usr/bin/env bash
# ============================================================
#  StreamStation — Easy GitHub Push (run this on your PC/WSL)
#  Usage: bash push.sh
#  Run from inside your StreamStation folder on your PC.
# ============================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

echo -e "\n${CYAN}${BOLD}  📡 StreamStation — Push to GitHub${NC}\n"

# ── Check we're in the right place ───────────────────────────────────────────
if [ ! -f "streamstation.py" ]; then
  echo -e "${RED}Error: Run this from inside your StreamStation folder.${NC}"
  echo -e "Example: ${CYAN}cd ~/StreamStation && bash push.sh${NC}"
  exit 1
fi

# ── Initialize git if needed ──────────────────────────────────────────────────
if [ ! -d ".git" ]; then
  echo -e "${YELLOW}Setting up git for the first time...${NC}"
  git init
  git branch -M main
fi

# ── Get or save GitHub credentials ───────────────────────────────────────────
CREDS_FILE="$HOME/.streamstation_github"

if [ -f "$CREDS_FILE" ]; then
  source "$CREDS_FILE"
else
  echo -e "${BOLD}First time setup — enter your GitHub details:${NC}\n"
  read -p "  GitHub username: " GH_USER
  echo -e "  ${YELLOW}GitHub token (paste it — nothing will appear, that's normal):${NC}"
  read -s -p "  Token: " GH_TOKEN
  echo ""
  read -p "  Repo name (e.g. StreamStation): " GH_REPO
  echo ""
  cat > "$CREDS_FILE" << EOF
GH_USER="$GH_USER"
GH_TOKEN="$GH_TOKEN"
GH_REPO="$GH_REPO"
EOF
  chmod 600 "$CREDS_FILE"
  echo -e "${GREEN}✓ Credentials saved — you won't need to enter these again${NC}"
  echo -e "${YELLOW}  (Stored at $CREDS_FILE)${NC}\n"
fi

# ── Set remote ────────────────────────────────────────────────────────────────
REMOTE_URL="https://${GH_USER}:${GH_TOKEN}@github.com/${GH_USER}/${GH_REPO}.git"
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

# ── Ask for description ───────────────────────────────────────────────────────
echo -e "${BOLD}What changed in this update?${NC}"
echo -e "${YELLOW}(Press Enter to use: 'Update StreamStation')${NC}"
read -p "  Description: " MSG
MSG="${MSG:-Update StreamStation}"

# ── Ask for version tag ───────────────────────────────────────────────────────
echo ""
read -p "  Version number (e.g. 1.4) or press Enter to skip: " VER

# ── Commit and push ───────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}Pushing to GitHub...${NC}"

git add .
git commit -m "$MSG" 2>/dev/null || echo -e "${YELLOW}(Nothing new to commit — pushing anyway)${NC}"
git branch -M main
git push -u origin main --force

if [ $? -eq 0 ]; then
  if [ -n "$VER" ]; then
    git tag -a "v$VER" -m "StreamStation v$VER" 2>/dev/null || git tag -f "v$VER" -m "StreamStation v$VER"
    git push origin "v$VER" --force 2>/dev/null
    echo -e "\n${GREEN}${BOLD}  ✓ Pushed and tagged as v$VER${NC}"
  else
    echo -e "\n${GREEN}${BOLD}  ✓ Pushed successfully!${NC}"
  fi
  echo -e "  ${CYAN}View at: https://github.com/${GH_USER}/${GH_REPO}${NC}"
  echo -e "\n  ${YELLOW}Now go to the StreamStation web UI and click 'Check for Updates'${NC}\n"
else
  echo -e "\n${RED}Push failed. Your token may have expired.${NC}"
  echo -e "Reset saved credentials and try again:"
  echo -e "  ${CYAN}rm $CREDS_FILE && bash push.sh${NC}\n"
  exit 1
fi
