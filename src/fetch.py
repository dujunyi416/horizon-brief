"""Stage 1: pull RSS sources, window + dedupe + cap, write out/candidates.json."""

import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
SEEN_PATH = ROOT / "state" / "seen.json"
OUT_PATH = ROOT / "out" / "candidates.json"
SEEN_TTL_DAYS = 14


def item_key(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    cutoff = time.time() - SEEN_TTL_DAYS * 86400
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(pruned, indent=0), encoding="utf-8")


def parse_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def clean_summary(entry) -> str:
    import re

    raw = getattr(entry, "summary", "") or ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def main() -> int:
    config = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    window = timedelta(hours=config.get("window_hours", 36))
    max_candidates = config.get("max_candidates", 120)
    now = datetime.now(timezone.utc)
    seen = load_seen()

    candidates = []
    for src in config["sources"]:
        try:
            feed = feedparser.parse(src["url"], agent="horizon-brief/1.0 (+https://github.com)")
        except Exception as exc:  # noqa: BLE001 - a dead feed must not kill the run
            print(f"[warn] {src['name']}: {exc}", file=sys.stderr)
            continue
        if feed.bozo and not feed.entries:
            print(f"[warn] {src['name']}: unreadable feed ({feed.get('bozo_exception')})", file=sys.stderr)
            continue

        taken = 0
        for entry in feed.entries:
            if taken >= src.get("cap", 10):
                break
            url = getattr(entry, "link", "") or ""
            title = (getattr(entry, "title", "") or "").strip()
            if not url or not title:
                continue
            published = parse_published(entry)
            if published and now - published > window:
                continue
            key = item_key(url, title)
            if key in seen:
                continue
            seen[key] = time.time()
            candidates.append(
                {
                    "id": len(candidates),
                    "key": key,
                    "source": src["name"],
                    "topic": src["topic"],
                    "title": title,
                    "summary": clean_summary(entry),
                    "url": url,
                    "published_ts": published.isoformat() if published else None,
                    "fetched_ts": now.isoformat(),
                }
            )
            taken += 1
        print(f"[ok] {src['name']}: +{taken}")

    # newest first, then cap for the prompt
    candidates.sort(key=lambda c: c["published_ts"] or "", reverse=True)
    candidates = candidates[:max_candidates]
    for i, c in enumerate(candidates):
        c["id"] = i

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    save_seen(seen)
    print(f"[done] {len(candidates)} candidates -> {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
