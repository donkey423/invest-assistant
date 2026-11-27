# 盤中警報搬到 Oracle Cloud 主機

GitHub Actions 的排程常常晚 10–30 分鐘，盤中警報不準。改在你的 Oracle Cloud Always Free 主機上，用 systemd 每 5 分鐘準時檢查一次：
- 只在**台股 09:00–13:30**、**美股開盤時間**（夏令／冬令自動換算）抓行情，其他時間不抓。
- 新聞關鍵字每 30 分鐘看一次。
- 觸發時寄 **Email**，也記在主機的 `~/.local/state/invest-alerts/alerts_history.json`。LINE 目前不推。
- 月營收轉折提醒（`rules.json` 的 `revenue`）也一起檢查，資料來自早報，主機每小時自動更新一次。
- 同一檔同一種條件一天只通知一次，和 GitHub 版相同。

> Yahoo 的台股報價約有 15–20 分鐘延遲，美股多半是即時的。這是資料來源的限制，不是排程的問題。

## 需要準備
- Oracle 主機一台：Ubuntu 22.04／24.04 或 Oracle Linux 8／9 都可以，最小的 Always Free 規格就夠（警報每次只跑幾秒）。
- 能用 SSH 登入（或用 Oracle 網頁主控台右上角的 **Cloud Shell** 再 `ssh` 進去）。
- GitHub repo 網址。repo 是公開的就直接用；私人 repo 見文末。

## 安裝（約 10 分鐘）
SSH 登入主機後，一行一行貼上：

```bash
sudo apt-get install -y git 2>/dev/null || sudo dnf install -y git
git clone https://github.com/donkey423/invest-assistant.git ~/invest-assistant
bash ~/invest-assistant/deploy/oracle/install.sh
```

接著填 Email 設定（Gmail 應用程式密碼，和早報用的一樣）：

```bash
sudo nano /etc/invest-alerts.env      # 填好後 Ctrl+O、Enter 存檔，Ctrl+X 離開
```

寄一封測試信確認：

```bash
cd ~/invest-assistant && set -a && . /etc/invest-alerts.env && set +a && .venv/bin/python -m alerts test
```

收到「投資警報｜測試」就完成了。

## 停掉 GitHub 上的舊排程（避免重複寄信）
GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **Variables** 頁籤 → **New repository variable**：
名稱 `ALERTS_RUNNER`，值 `oracle`。之後 GitHub 只在你手動按 Run workflow 時才跑警報。

## 平常會用到的指令
| 想做什麼 | 指令 |
|---|---|
| 看最近幾次檢查 | `journalctl -u invest-alerts -n 30 --no-pager` |
| 看下次什麼時候跑 | `systemctl list-timers 'invest-alerts*'` |
| 馬上跑一次 | `sudo systemctl start invest-alerts` |
| 只看會觸發什麼、不寄信 | `cd ~/invest-assistant && .venv/bin/python -m alerts check --dry-run` |
| 立刻更新程式 | `bash ~/invest-assistant/deploy/oracle/install.sh` |
| 移除排程 | `bash ~/invest-assistant/deploy/oracle/uninstall.sh` |

改警報條件：在 GitHub 改 `alerts/rules.json` 並 commit，主機每小時會自動更新；想馬上生效就跑一次 install.sh。
想改檢查頻率：`INTERVAL_MIN=10 bash ~/invest-assistant/deploy/oracle/install.sh`。

## 常見問題
- **Oracle 回收閒置主機**：Oracle 會回收長期幾乎沒在用的 Always Free 主機。警報很省資源，若主機上沒有其他服務，留意 Oracle 寄來的閒置通知。
- **私人 repo**：在主機上 `ssh-keygen -t ed25519` 產生金鑰，把 `~/.ssh/id_ed25519.pub` 加到 GitHub repo → Settings → **Deploy keys**（只要讀取權限），然後 clone 改用 `git@github.com:donkey423/invest-assistant.git`。
- **沒收到信**：先跑上面的測試指令；看到 `沒有設定 Email` 是設定檔沒填好，看到 `Username and Password not accepted` 是要用 Gmail 的「應用程式密碼」而不是登入密碼。
