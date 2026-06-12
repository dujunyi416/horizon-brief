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

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")
    print("all tests passed")
