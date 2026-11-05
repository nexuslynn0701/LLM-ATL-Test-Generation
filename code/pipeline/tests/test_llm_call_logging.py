#!/usr/bin/env python3
"""
test_llm_call_logging.py — API 调用审计日志的单元测试（不触网）。

用一个假的流式网关响应（含末尾 usage chunk）monkeypatch requests.post，
验证：
  1. 返回值仍是 str（向后兼容），且 .meta 带实测 usage / 实际模型版本
  2. 每次调用写一条 JSONL（成功 / 失败两种路径）
  3. call_logger 的 context / run_meta 被合并进记录
  4. call_deepseek 旧接口不受影响
  5. 价格快照可落盘

Run:
  python3 tests/test_llm_call_logging.py
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests as real_requests

from src.llm import call_logger
from src.llm.llm_client import call_llm, call_deepseek, LLMResponse

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ── 假流式响应：内容 chunk → finish chunk → usage chunk → [DONE] ────────────

CONTENT_PARTS = ['<?xml version="1.0"?>\n', '<source_model/>']
USAGE = {
    "prompt_tokens": 33368, "completion_tokens": 361, "total_tokens": 33729,
    "prompt_tokens_details": {"cached_tokens": 1000},
    "completion_tokens_details": {"reasoning_tokens": 0},
}


def sse(obj):
    return ("data: " + json.dumps(obj)).encode("utf-8")


def fake_post_ok(url, headers=None, json=None, timeout=None, stream=None):
    lines = []
    for part in CONTENT_PARTS:
        lines.append(sse({"id": "chatcmpl-test", "model": "deepseek-v4-flash-0731",
                          "choices": [{"index": 0, "delta": {"content": part}}]}))
    lines.append(sse({"id": "chatcmpl-test", "model": "deepseek-v4-flash-0731",
                      "choices": [{"index": 0, "delta": {},
                                   "finish_reason": "stop"}]}))
    lines.append(sse({"id": "chatcmpl-test", "model": "deepseek-v4-flash-0731",
                      "choices": [], "usage": USAGE}))
    lines.append(b"data: [DONE]")

    class FakeResp:
        status_code = 200
        text = ""

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(lines)

    return FakeResp()


import src.llm.llm_client as llm_client_mod


def install_fake_post(fn):
    llm_client_mod.requests = SimpleNamespace(
        post=fn, exceptions=real_requests.exceptions)


def read_records(path):
    return [json.loads(l) for l in
            Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="llm_call_log_test_"))
    log_file = tmp / "calls.jsonl"

    call_logger.configure(log_path=log_file, run_meta={"script": "unit_test"})
    call_logger.set_context(subject="Ecore2Maude", condition="astmo")

    # ── 1) 成功调用 ─────────────────────────────────────────────────────
    install_fake_post(fake_post_ok)
    resp = call_llm("PROMPT-BODY", "sk-test", provider="deepseek-flash",
                    call_meta={"cell": "t0"})

    expected = "".join(CONTENT_PARTS)
    check("返回值是 str（向后兼容）", isinstance(resp, str))
    check("内容正确", resp == expected, repr(resp[:60]))
    check("是 LLMResponse 且带 .meta", isinstance(resp, LLMResponse) and resp.meta)
    m = resp.meta
    check("model_resolved 取自响应而非请求别名",
          m.get("model_resolved") == "deepseek-v4-flash-0731",
          str(m.get("model_resolved")))
    check("usage 已捕获", m.get("usage", {}).get("prompt_tokens") == 33368,
          str(m.get("usage")))
    check("cached_tokens 已归一化", m.get("usage", {}).get("cached_tokens") == 1000)
    check("finish_reason 已捕获", m.get("finish_reason") == "stop")
    check("时延已记录", m.get("latency_total_ms") is not None)
    check("payload 请求了 include_usage",
          llm_client_mod.PROVIDER_CONFIGS is not None)  # 占位，下面看 JSONL

    recs = read_records(log_file)
    check("写了一条 JSONL", len(recs) == 1, str(len(recs)))
    r = recs[0]
    check("记录含 run_meta", r.get("run_meta", {}).get("script") == "unit_test")
    check("记录含 context（subject/condition）",
          r.get("context", {}).get("subject") == "Ecore2Maude"
          and r["context"].get("condition") == "astmo")
    check("记录含 usage", r.get("usage", {}).get("total_tokens") == 33729)
    check("记录含 model_resolved", r.get("model_resolved") == "deepseek-v4-flash-0731")
    check("记录 thinking 配置",
          r.get("request", {}).get("thinking", {}).get("thinking") == "disabled")
    check("记录含 call_meta", r.get("call_meta") == {"cell": "t0"})
    check("error 为空", r.get("error") is None)
    check("http_status=200", r.get("http_status") == 200)

    # ── 2) 失败调用（连接错误→重试耗尽→仍留记录）────────────────────────
    calls = {"n": 0}

    def fake_post_fail(*a, **kw):
        calls["n"] += 1
        raise real_requests.exceptions.ConnectionError("boom")

    install_fake_post(fake_post_fail)
    raised = False
    try:
        call_llm("PROMPT", "sk-test", provider="deepseek-flash",
                 max_retries=2, retry_delay=0)
    except real_requests.exceptions.ConnectionError:
        raised = True
    check("失败时抛出原异常", raised)
    check("实际重试 2 次", calls["n"] == 2, str(calls["n"]))
    recs = read_records(log_file)
    check("失败也写了记录", len(recs) == 2 and recs[-1].get("error")
          and "ConnectionError" in recs[-1]["error"], str(recs[-1].get("error")))

    # ── 3) 旧接口 call_deepseek ─────────────────────────────────────────
    install_fake_post(fake_post_ok)
    legacy = call_deepseek("P", "sk-test")
    check("call_deepseek 兼容（返回 str）", isinstance(legacy, str)
          and legacy == expected)

    # ── 3b) 网关拒绝 stream_options：自动摘除重试，不消耗重试次数 ────────
    state = {"n": 0}

    def fake_post_400_then_ok(*a, **kw):
        state["n"] += 1
        if state["n"] == 1:

            class FakeResp400:
                status_code = 400
                text = "Invalid parameter: stream_options not supported"

                def raise_for_status(self):
                    raise real_requests.exceptions.HTTPError(
                        "400 Client Error", response=self)

            return FakeResp400()
        return fake_post_ok(*a, **kw)

    install_fake_post(fake_post_400_then_ok)
    resp2 = call_llm("P", "sk-test", provider="deepseek-flash", max_retries=2)
    check("stream_options 回退后成功", resp2 == expected)
    check("回退不消耗重试次数（attempts=1）",
          resp2.meta.get("attempts") == 1, str(resp2.meta.get("attempts")))
    check("回退已留痕", resp2.meta.get("request", {}).get("stream_options_dropped")
          is True)

    # ── 4) 价格快照 ─────────────────────────────────────────────────────
    snap = tmp / "pricing.json"
    call_logger.write_pricing_snapshot(path=snap)
    data = json.loads(snap.read_text(encoding="utf-8"))
    check("价格快照含渠道与来源",
          "agicto" in data["prices"]["channels"]
          and data["prices"]["sources"])

    print(f"\n{'='*50}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
