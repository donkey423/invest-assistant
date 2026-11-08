#!/usr/bin/env bash
# 在 Oracle Cloud（Always Free）主機上安裝盤中警報。Ubuntu 與 Oracle Linux 都可以。
#   bash install.sh https://github.com/<你的帳號>/invest-assistant.git
# 重跑也安全：已安裝會更新程式與排程，不會覆蓋你填好的 /etc/invest-alerts.env。
set -euo pipefail

REPO_URL="${1:-}"
APP_DIR="${APP_DIR:-$HOME/invest-assistant}"
STATE_DIR="${STATE_DIR:-$HOME/.local/state/invest-alerts}"
INTERVAL_MIN="${INTERVAL_MIN:-5}"
ENV_FILE=/etc/invest-alerts.env
RUN_USER="$(id -un)"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

say "1/5 安裝 git 與 Python"
if command -v apt-get >/dev/null; then
  sudo apt-get update -y -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3 python3-venv
elif command -v dnf >/dev/null; then
  sudo dnf install -y -q git python3.11 python3.11-pip || sudo dnf install -y -q git python3 python3-pip
else
  echo "找不到 apt-get 或 dnf，請改用 Ubuntu 或 Oracle Linux 映像" >&2; exit 1
fi
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
  || { echo "需要 Python 3.10 以上（目前 $("$PY" -V)）" >&2; exit 1; }

say "2/5 下載程式到 $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  [ -n "$REPO_URL" ] || { echo "第一次安裝要給 repo 網址：bash install.sh https://github.com/xxx/invest-assistant.git" >&2; exit 1; }
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi

say "3/5 建立 Python 環境（第一次約 2–5 分鐘）"
[ -x "$APP_DIR/.venv/bin/python" ] || "$PY" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
mkdir -p "$STATE_DIR"

say "4/5 設定檔 $ENV_FILE"
if [ ! -f "$ENV_FILE" ]; then
  sudo install -m 600 -o "$RUN_USER" "$APP_DIR/deploy/oracle/invest-alerts.env.example" "$ENV_FILE"
  echo "已建立，請用 nano 填入 Email 設定：sudo nano $ENV_FILE"
else
  echo "已存在，保留你的設定"
fi

say "5/5 安裝排程（每 $INTERVAL_MIN 分鐘檢查一次，只在台股／美股開盤時抓行情）"
sudo tee /etc/systemd/system/invest-alerts.service >/dev/null <<UNIT
[Unit]
Description=投資助手 盤中警報檢查
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python -m alerts check --market-hours --state $STATE_DIR/alerts_state.json
TimeoutStartSec=240
UNIT

sudo tee /etc/systemd/system/invest-alerts.timer >/dev/null <<UNIT
[Unit]
Description=每 $INTERVAL_MIN 分鐘檢查盤中警報

[Timer]
OnCalendar=*:0/$INTERVAL_MIN
AccuracySec=15s

[Install]
WantedBy=timers.target
UNIT

# 每小時自動更新程式、rules.json 與早報資料（月營收提醒要用）
sudo tee /etc/systemd/system/invest-alerts-update.service >/dev/null <<UNIT
[Unit]
Description=投資助手 警報程式更新

[Service]
Type=oneshot
User=$RUN_USER
ExecStart=/usr/bin/git -C $APP_DIR pull --ff-only
ExecStartPost=$APP_DIR/.venv/bin/pip install -q -r $APP_DIR/requirements.txt
UNIT

sudo tee /etc/systemd/system/invest-alerts-update.timer >/dev/null <<UNIT
[Unit]
Description=每小時更新警報程式

[Timer]
OnCalendar=hourly
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now invest-alerts.timer invest-alerts-update.timer

cat <<DONE

完成。接下來：
  1. 填 Email 設定：   sudo nano $ENV_FILE
  2. 寄測試信：         cd $APP_DIR && set -a && . $ENV_FILE && set +a && .venv/bin/python -m alerts test
  3. 看最近執行紀錄：   journalctl -u invest-alerts -n 30 --no-pager
  4. 看下次執行時間：   systemctl list-timers 'invest-alerts*'
DONE
