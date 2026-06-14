"""Regression tests for extract_json robustness."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from brief import extract_json

def test_strict():
    assert extract_json('{"a": 1}') == {"a": 1}

def test_trailing_comma():
    assert extract_json('{"a": 1,}') == {"a": 1}

def test_array_trailing_comma():
    assert extract_json('{"items": [1, 2,]}') == {"items": [1, 2]}

def test_fenced():
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}

def test_prefix_text():
    assert extract_json('Here is the result:\n{"a": 3}') == {"a": 3}

# === 2026-06-11 / 06-13 真实故障样本: 模型在字符串值里塞了未转义的 ASCII 双引号 ===

def test_bare_quote_in_string():
    """6-13: '永续合约"ETF化"议题升温' — json.loads 报 Expecting ',' delimiter"""
    raw = '{"overview_zh":"SpaceX完成IPO，永续合约"ETF化"议题升温。","actionable":[]}'
    out = extract_json(raw)
    assert out["actionable"] == []
    assert "ETF" in out["overview_zh"]

def test_multiple_bare_quotes():
    raw = '{"x":"foo"bar"baz"qux"}'
    assert extract_json(raw) == {"x": 'foo"bar"baz"qux'}

def test_bare_quote_with_trailing_comma():
    """裸引号 + 尾逗号双重 — 第 3 级和第 4 级容错必须协同工作"""
    raw = '{"x":"foo"bar","y":2,}'
    assert extract_json(raw) == {"x": 'foo"bar', "y": 2}

def test_unicode_bare_quotes():
    """中文上下文里的多个裸引号"""
    raw = '{"overview_zh":"亚马逊CEO推动"出口管制"落地，BTC突破"64000美元"。"}'
    out = extract_json(raw)
    assert "出口管制" in out["overview_zh"]
    assert "64000" in out["overview_zh"]

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")
    print("all tests passed")
