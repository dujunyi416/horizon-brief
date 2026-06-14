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

SECTION_TITLES = {
    "actionable": "🎯 直接相关",
    "us_stocks":  "📈 美股 · 宏观",
    "tech":       "🤖 科技 · AI",
    "crypto":     "🪙 加密 · 链上",
}
TELEGRAM_MAX_LEN = 4096


def env(name: str) -> str:
    """Read an env var stripped of whitespace and BOM.

    Windows 上用 PowerShell 管道喂 `gh secret set` 会给值带上 U+FEFF，
    实测会让 requests 报 InvalidSchema —— 所有凭证都过这层清洗。
    """
    return os.environ.get(name, "").strip().lstrip("\ufeff").strip()


def _read_report() -> dict:
    if not REPORT_PATH.exists():
        return {}
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def health_footer() -> str:
    """Surface dead feeds where they'll actually be seen — in the briefing itself."""
    failed = _read_report().get("failed_sources", [])
    if not failed:
        return ""
    return f"⚠️ 源异常: {', '.join(failed)}"


def detect_outage_brief() -> dict | None:
    """brief 为空时区分: 是"全部新闻今天都被 seen.json 去重了"(legit silence),
    还是"全部 RSS 源同时挂了"(必须告警, 否则跟无新闻一样安静死)?

    判定: 0 候选 + ≥50% 源失败 → outage. 候选数门槛和源失败比例都要满足,
    避免误报 1-2 个长期腐烂源 + 真的去重无新闻的日子.
    """
    report = _read_report()
    n_candidates = report.get("n_candidates", -1)
    failed = report.get("failed_sources", [])
    total = report.get("total_sources", 0)
    if n_candidates != 0 or total == 0 or len(failed) < total * 0.5:
        return None
    sample = ", ".join(failed[:5]) + ("…" if len(failed) > 5 else "")
    return {
        "degraded": True,
        "overview_zh": (
            f"⚠️ 全部 RSS 源同时不可用：今日 0 候选，失败源 {len(failed)}/{total} 个 "
            f"（{sample}）。可能是 runner 网络异常、Cloudflare 拦截或多源同时腐烂，"
            f"去 Actions 看 fetch 日志。"
        ),
        "actionable": [],
        "us_stocks": [],
        "tech": [],
        "crypto": [],
    }


def push_telegram(brief: dict, date_str: str) -> bool:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    title_emoji = "⚠️" if brief.get("degraded") else "☀️"
    lines = [f"<b>{title_emoji} Horizon Brief · {date_str}</b>", ""]
    if brief.get("overview_zh"):
        lines += [html.escape(brief["overview_zh"]), ""]
    for section in ("actionable", "us_stocks", "tech", "crypto"):
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
    webhook = env("FEISHU_WEBHOOK_URL")
    if not webhook:
        return False
    content = []
    if brief.get("overview_zh"):
        content.append([{"tag": "text", "text": brief["overview_zh"]}])
        content.append([{"tag": "text", "text": ""}])
    for section in ("actionable", "us_stocks", "tech", "crypto"):
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
    keyword = env("FEISHU_KEYWORD")
    if keyword:
        content.append([{"tag": "text", "text": f"#{keyword}"}])

    resp = requests.post(
        webhook,
        json={
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {"title": f"{'⚠️' if brief.get('degraded') else '☀️'} Horizon Brief · {date_str}", "content": content}
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
    # 飞书成功响应必带 code:0; 缺 code 字段一律视为失败 (此前 (0, None) 兜底反而吃掉了真实错误)
    if not resp.ok or body.get("code", -1) != 0:
        print(f"[error] feishu: {resp.status_code} {resp.text[:500]}", file=sys.stderr)
        return False
    print("[ok] pushed to Feishu")
    return True


def main() -> int:
    brief = json.loads(BRIEF_PATH.read_text(encoding="utf-8"))
    is_empty = not brief or not any(brief.get(s) for s in ("actionable", "us_stocks", "tech", "crypto"))
    if is_empty:
        # brief 空了 — 区分"全部去重"(legit) vs "全部源挂"(必须告警). 后者覆盖 brief
        outage = detect_outage_brief()
        if outage:
            print("[warn] all sources down — pushing outage alert", file=sys.stderr)
            brief = outage
            is_empty = False
    if is_empty:
        print("[done] empty brief, nothing to push")
        return 0

    aest = timezone(timedelta(hours=10))
    date_str = datetime.now(aest).strftime("%Y-%m-%d %a")

    # 单通道异常不能拖死另一个通道
    sent = []
    for channel in (push_telegram, push_feishu):
        try:
            sent.append(channel(brief, date_str))
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {channel.__name__}: {exc}", file=sys.stderr)
            sent.append(False)
    if not any(sent):
        print("[warn] no channel configured or all pushes failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
