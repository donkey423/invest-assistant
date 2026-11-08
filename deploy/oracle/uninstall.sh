#!/usr/bin/env bash
# 停掉並移除盤中警報排程（程式資料夾與設定檔保留，要刪自己刪）
set -euo pipefail
sudo systemctl disable --now invest-alerts.timer invest-alerts-update.timer 2>/dev/null || true
sudo rm -f /etc/systemd/system/invest-alerts{,-update}.{service,timer}
sudo systemctl daemon-reload
echo "已移除排程。設定檔 /etc/invest-alerts.env 與 ~/invest-assistant 仍保留。"
