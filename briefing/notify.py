"""用 Gmail 寄早報。沒設定 EMAIL_SENDER / EMAIL_PASSWORD 就不寄。"""
from __future__ import annotations

import html
import logging
import os
import smtplib
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def _pct(v) -> str:
    if v is None:
        return "—"
    color = "#c62828" if v > 0 else "#2e7d32" if v < 0 else "#555"  # 台股習慣：紅漲綠跌
    return f'<span style="color:{color}">{v:+.2f}%</span>'


def render_email(brief: dict) -> tuple[str, str]:
    s, m = brief.get("summary") or {}, brief["market"]
    t = m["taiex"]
    rows = "".join(
        f"<tr><td>{html.escape(q['name'])}</td><td align=right>{_pct(q.get('change_pct'))}</td></tr>"
        for q in [t, *m["global"], *m["ai_stocks"]] if "error" not in q
    )
    points = "".join(
        f"<li><b>[{html.escape(p['tag'])}] {html.escape(p['title'])}</b><br>{html.escape(p['summary'])}</li>"
        for p in s.get("points", [])
    )
    site = os.environ.get("SITE_URL", "")
    link = f'<p><a href="{html.escape(site)}">打開完整早報</a></p>' if site else ""
    body = f"""<div style="font-family:sans-serif;max-width:560px">
<h2 style="margin:0 0 8px">{html.escape(s.get('headline', '今日早報'))}</h2>
<p>{html.escape(s.get('market_comment', ''))}</p>
<h3>財經重點</h3><ul>{points}</ul>
<h3>主要市場</h3><table cellpadding=4>{rows}</table>{link}
<p style="color:#888;font-size:12px">AI 整理，僅供參考，不構成投資建議。</p></div>"""
    subject = f"投資早報 {brief['generated_at'][:10]}｜{s.get('headline', '')}"[:120]
    return subject, body


def send_email(brief: dict) -> bool:
    sender, password = os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_PASSWORD")
    if not sender or not password:
        log.info("沒有設定 Email，略過寄送")
        return False
    to = os.environ.get("EMAIL_RECEIVERS") or sender
    subject, body = render_email(brief)
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())
    log.info("已寄出早報給 %s", to)
    return True
