"""Regression tests for two new defenses:
- brief._classify_failure: 把 rank 失败 reason 归类成可操作指引
- push.detect_outage_brief: 全部源挂时主动构造 outage 简报, 修 "推送静默死" 盲区
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from brief import _classify_failure
import push


# === brief._classify_failure ===

def test_classify_github_models():
    msg = _classify_failure("all LLM providers failed: github-models: HTTP 403")
    assert "models: read" in msg

def test_classify_all_providers_failed():
    msg = _classify_failure("all 2 rank attempts failed: all LLM providers failed: x")
    assert "GitHub Models" in msg and "Claude" in msg

def test_classify_token_expired():
    msg = _classify_failure("all 2 rank attempts failed: claude exited 1: ")
    assert "CLAUDE_CODE_OAUTH_TOKEN" in msg
    assert "claude setup-token" in msg

def test_classify_cli_missing():
    msg = _classify_failure("claude CLI not found on PATH")
    assert "CLAUDE_CODE_OAUTH_TOKEN" in msg  # 同一类问题

def test_classify_bare_quotes_unrecoverable():
    msg = _classify_failure("unparseable JSON after all attempts. error=Expecting ...")
    assert "brief.raw.txt" in msg

def test_classify_fixer_no_converge():
    msg = _classify_failure("bare-quote fixer did not converge")
    assert "brief.raw.txt" in msg

def test_classify_timeout():
    msg = _classify_failure("claude exited 1: subprocess timed out after 600s")
    # 包含 'claude exited' 优先匹配 token 分支 — 实际超时不会有 'claude exited' 而是 TimeoutExpired
    # 单独测纯 timeout 串
    msg2 = _classify_failure("subprocess.TimeoutExpired: claude timeout")
    assert "API 慢" in msg2 or "网络" in msg2

def test_classify_unknown():
    msg = _classify_failure("some weird thing: details")
    assert "details" in msg


# === push.detect_outage_brief ===

def _write_report(d: dict):
    push.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    push.REPORT_PATH.write_text(json.dumps(d), encoding="utf-8")

def _no_report():
    if push.REPORT_PATH.exists():
        push.REPORT_PATH.unlink()


def test_outage_no_report():
    _no_report()
    assert push.detect_outage_brief() is None

def test_outage_has_candidates_means_legit():
    _write_report({"n_candidates": 50, "failed_sources": [], "total_sources": 14})
    assert push.detect_outage_brief() is None

def test_outage_zero_candidates_all_succeeded():
    """0 候选 + 0 失败 = 全部去重, 不是 outage"""
    _write_report({"n_candidates": 0, "failed_sources": [], "total_sources": 14})
    assert push.detect_outage_brief() is None

def test_outage_zero_candidates_few_failures():
    """0 候选 + 2/14 失败 = 阈值之下, 算作 legit"""
    _write_report({"n_candidates": 0, "failed_sources": ["A", "B"], "total_sources": 14})
    assert push.detect_outage_brief() is None

def test_outage_zero_candidates_half_failed():
    """0 候选 + 7/14 失败 = 触发告警"""
    failed = [f"src{i}" for i in range(7)]
    _write_report({"n_candidates": 0, "failed_sources": failed, "total_sources": 14})
    brief = push.detect_outage_brief()
    assert brief is not None
    assert brief["degraded"] is True
    assert "7/14" in brief["overview_zh"]
    assert brief["us_stocks"] == []  # outage brief 永远空 section

def test_outage_zero_candidates_all_failed():
    """0 候选 + 全 14/14 失败 = 强 outage 信号"""
    failed = [f"src{i}" for i in range(14)]
    _write_report({"n_candidates": 0, "failed_sources": failed, "total_sources": 14})
    brief = push.detect_outage_brief()
    assert brief is not None
    assert "14/14" in brief["overview_zh"]

def test_outage_missing_total_sources_is_safe():
    """老格式 report (没有 total_sources 字段) 不能误报 outage"""
    _write_report({"n_candidates": 0, "failed_sources": ["A", "B", "C"]})
    assert push.detect_outage_brief() is None


if __name__ == "__main__":
    # 备份用户真实 report, 跑完恢复
    original = push.REPORT_PATH.read_text(encoding="utf-8") if push.REPORT_PATH.exists() else None
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                fn()
                print(f"  ok  {name}")
        print("all tests passed")
    finally:
        if original is not None:
            push.REPORT_PATH.write_text(original, encoding="utf-8")
        elif push.REPORT_PATH.exists():
            push.REPORT_PATH.unlink()
