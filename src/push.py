"""Stage 3: push out/brief.json to whichever channels have credentials configured.

Channels (all optional, all free):
- Telegram: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
- Feishu:   FEISHU_WEBHOOK_URL (群自定义机器人 webhook)
"""

import html
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BRIEF_PATH = ROOT / "out" / "brief.json"
REPORT_PATH = ROOT / "out" / "fetch_report.json"

SECTION_TITLES = {"actionable": "🎯 与你直接相关", "horizon": "🔭 视野扫描"}
TELEGRAM_MAX_LEN = 4096


def health_footer() -> str:
    """Surface dead feeds where they'll actually be seen — in the briefing itself."""
    if not REPORT_PATH.exists():
        return ""
    failed = json.loads(REPORT_PATH.read_text(encoding="utf-8")).get("failed_sources", [])
    if not failed:
        return ""
    return f"⚠️ 源异常: {', '.join(failed)}"


def push_telegram(brief: dict, date_str: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    lines = [f"<b>☀️ Horizon Brief · {date_str}</b>", ""]
    if brief.get("overview_zh"):
        lines += [html.escape(brief["overview_zh"]), ""]
    for section in ("actionable", "horizon"):
        items = brief.get(section, [])
        if not items:
            continue
        lines.append(f"<b>{SECTION_TITLES[section]}</b>")
        for item in items:
            title = html.escape(item.get("headline_zh") or item["title"])
            why = html.escape(item.get("why_zh", ""))
            lines.append(f"• <a href=\"{html.escape(item['url'])}\">{title}</a>")
            if why:
                lines.append(f"  └ {why}")
        lines.append("")
    footer = health_footer()
    if footer:
        lines.append(html.escape(footer))

    text = "\n".join(lines).strip()
    if len(text) > TELEGRAM_MAX_LEN:
        # drop trailing whole lines rather than risk cutting an HTML tag in half
        kept = []
        total = 0
        for line in text.split("\n"):
            if total + len(line) + 1 > TELEGRAM_MAX_LEN - 2:
                break
            kept.append(line)
            total += len(line) + 1
        text = "\n".join(kept) + "\n…"

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"[error] telegram: {resp.status_code} {resp.text[:500]}", file=sys.stderr)
        return False
    print("[ok] pushed to Telegram")
    return True


def push_feishu(brief: dict, date_str: str) -> bool:
    webhook = os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook:
        return False
    content = []
    if brief.get("overview_zh"):
        content.append([{"tag": "text", "text": brief["overview_zh"]}])
        content.append([{"tag": "text", "text": ""}])
    for section in ("actionable", "horizon"):
        items = brief.get(section, [])
        if not items:
            continue
        content.append([{"tag": "text", "text": SECTION_TITLES[section]}])
        for item in items:
            title = item.get("headline_zh") or item["title"]
            line = [{"tag": "a", "text": f"• {title}", "href": item["url"]}]
            content.append(line)
            if item.get("why_zh"):
                content.append([{"tag": "text", "text": f"  └ {item['why_zh']}"}])
        content.append([{"tag": "text", "text": ""}])
    footer = health_footer()
    if footer:
        content.append([{"tag": "text", "text": footer}])
    # 「自定义关键词」安全策略只检查正文，不检查标题 (实测 19024 Key Words Not Found)
    keyword = os.environ.get("FEISHU_KEYWORD", "").strip()
    if keyword:
        content.append([{"tag": "text", "text": f"#{keyword}"}])

    resp = requests.post(
        webhook,
        json={
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {"title": f"☀️ Horizon Brief · {date_str}", "content": content}
                }
            },
        },
        timeout=30,
    )
    body = {}
    try:
        body = resp.json()
    except ValueError:
        pass
    if not resp.ok or body.get("code") not in (0, None):
        print(f"[error] feishu: {resp.status_code} {resp.text[:500]}", file=sys.stderr)
        return False
    print("[ok] pushed to Feishu")
    return True


def main() -> int:
    brief = json.loads(BRIEF_PATH.read_text(encoding="utf-8"))
    if not brief or not (brief.get("actionable") or brief.get("horizon")):
        print("[done] empty brief, nothing to push")
        return 0

    aest = timezone(timedelta(hours=10))
    date_str = datetime.now(aest).strftime("%Y-%m-%d %a")

    sent = [push_telegram(brief, date_str), push_feishu(brief, date_str)]
    if not any(sent):
        print("[warn] no channel configured or all pushes failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
