"""推播通道。沒設定對應的環境變數就安靜略過，不會讓排程失敗。

LINE Notify 已於 2025 年停止服務，這裡用 LINE Messaging API：
  LINE_CHANNEL_TOKEN  官方帳號的 Channel access token（長期）
  LINE_TO             要推給誰的 userId（U 開頭）；不填就改用 broadcast 推給所有好友
Email 沿用早報的設定：EMAIL_SENDER、EMAIL_PASSWORD（Gmail 應用程式密碼）、EMAIL_RECEIVERS
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

LINE_API = "https://api.line.me/v2/bot/message"
LINE_TEXT_LIMIT = 5000  # LINE 單則文字上限
LINE_MAX_MESSAGES = 5   # 一次 push 最多 5 則


def _post(url: str, token: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def split_text(text: str, limit: int = LINE_TEXT_LIMIT) -> list[str]:
    """把長訊息依換行切成 LINE 能接受的大小。"""
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) > limit:
            chunks.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        chunks.append(cur)
    return [c.rstrip("\n") for c in chunks]


def send_line(text: str, post=_post) -> bool:
    token = os.environ.get("LINE_CHANNEL_TOKEN")
    if not token:
        log.info("沒有設定 LINE_CHANNEL_TOKEN，略過 LINE")
        return False
    to = os.environ.get("LINE_TO", "").strip()
    msgs = [{"type": "text", "text": c} for c in split_text(text)][:LINE_MAX_MESSAGES]
    if to:
        post(f"{LINE_API}/push", token, {"to": to, "messages": msgs})
    else:
        post(f"{LINE_API}/broadcast", token, {"messages": msgs})
    log.info("已推送 LINE（%d 則）", len(msgs))
    return True


def send_email(subject: str, html_body: str, smtp_cls=smtplib.SMTP_SSL) -> bool:
    sender, password = os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_PASSWORD")
    if not sender or not password:
        log.info("沒有設定 Email，略過寄送")
        return False
    to = os.environ.get("EMAIL_RECEIVERS") or sender
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    with smtp_cls("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())
    log.info("已寄出 Email 給 %s", to)
    return True
