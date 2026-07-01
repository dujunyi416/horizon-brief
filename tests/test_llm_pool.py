"""Tests for stratified LLM pool selection."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from brief import select_llm_pool, slim_for_llm


def _c(i: int, topic: str, ts: str) -> dict:
    return {
        "id": i,
        "key": f"k{i}",
        "topic": topic,
        "title": f"title-{i}",
        "summary": f"summary-{i}",
        "url": f"https://example.com/{i}",
        "published_ts": ts,
        "fetched_ts": ts,
        "source": "test",
    }


def test_pool_unchanged_when_small():
    items = [_c(0, "tech", "2026-06-01T12:00:00+00:00")]
    assert select_llm_pool(items, pool_size=60) == items


def test_stratified_quotas_respected():
    items = []
    for i in range(30):
        items.append(_c(i, "tech", f"2026-06-01T{12 + i % 10:02d}:00:00+00:00"))
    for i in range(30, 60):
        items.append(_c(i, "macro", f"2026-06-01T{8 + i % 10:02d}:00:00+00:00"))
    pool = select_llm_pool(items, quotas={"us_stocks": 10, "tech": 10, "crypto": 5}, pool_size=20)
    assert len(pool) == 20
    topics = {c["topic"] for c in pool}
    assert "tech" in topics
    assert "macro" in topics


def test_slim_for_llm_omits_summary():
    items = [_c(1, "crypto", "2026-06-01T12:00:00+00:00")]
    raw = slim_for_llm(items)
    assert "summary" not in raw
    assert "title-1" in raw


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")
    print("all tests passed")
