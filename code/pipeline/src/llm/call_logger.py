# -*- coding: utf-8 -*-
"""
call_logger.py — 托管 LLM API 调用的逐次审计日志（JSONL）。

目的：让每次 API 调用事后可核算、可复现：
  - 实际 token 用量（usage 由网关在流式末尾返回，llm_client 负责捕获）
  - 实际解析到的模型版本（响应 model 字段，而非请求别名）
  - thinking/reasoning 配置、temperature、max_tokens 等采样参数
  - 时延、重试、失败原因
  - cell 上下文（subject/condition/attempt），由实验脚本通过 set_context 注入

零配置可用：llm_client 首次调用时自动启用，默认写到
<repo>/logs/api_calls/api_calls_YYYYMMDD_HHMMSS_<pid>.jsonl。
环境变量 LLM_CALL_LOG_DISABLE=1 可整体关闭。

价格快照（write_pricing_snapshot）内嵌 2026-09-01 查到的价格表；
计费规则随时会变（DeepSeek 已改分时定价），跑正式实验前应在
中转站/官方控制台核对一遍再覆盖 extra 字段。
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_lock = threading.Lock()
_state = {
    "configured": False,
    "disabled":   False,
    "log_path":   None,
    "run_meta":   {},
    "context":    {},
}

# ── 价格快照（2026-09-01 查询，单位：每百万 token）─────────────────────────
# 来源见 sources；agicto 为其模型页公开标价（不分时段），DeepSeek 官方为
# 峰谷分时（高峰=工作日 9-12 / 14-18，其余半价）。重跑前务必控制台复核。

CURRENT_PRICES = {
    "as_of": "2026-09-01",
    "currency": "CNY",
    "unit": "per_1M_tokens",
    "channels": {
        "agicto": {
            "deepseek-v4-flash": {"input": 3.0,  "output": 9.0},
            "deepseek-v4-pro":   {"input": 9.0,  "output": 27.0},
            "qwen3-max":         {"input": 2.38, "output": 9.5,
                                  "note": "折扣价，原价 2.5/10；>32K 请求是否按官方阶梯加价需在控制台核实"},
            "gpt-5.1":           {"input": 7.88, "output": 63.0,
                                  "note": "折扣价，原价 8.75/70"},
            "time_based": False,
        },
        "deepseek_official": {
            "deepseek-v4-flash": {
                "input_cache_miss": {"peak": 3.0, "idle": 1.5},
                "input_cache_hit":  {"peak": 0.10, "idle": 0.05},
                "output":           {"peak": 9.0, "idle": 4.5},
            },
            "peak_hours_beijing": "weekdays 09:00-12:00, 14:00-18:00; 其余为 idle（半价）",
            "time_based": True,
        },
    },
    "sources": [
        "https://agicto.com/model",
        "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
    ],
}


# ── 配置与上下文 ────────────────────────────────────────────────────────────

def configure(log_path=None, run_meta=None, disable=False):
    """初始化日志。可重复调用；run_meta 每次覆盖。"""
    with _lock:
        if os.environ.get("LLM_CALL_LOG_DISABLE") == "1":
            disable = True
        _state["disabled"] = bool(disable)
        if disable:
            _state["configured"] = True
            return
        if log_path is None and os.environ.get('LLM_CALL_LOG'):
            log_path = os.environ['LLM_CALL_LOG']
        if log_path is None and _state["log_path"] is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = ROOT / "logs" / "api_calls" / f"api_calls_{ts}_pid{os.getpid()}.jsonl"
        if log_path is not None:
            _state["log_path"] = Path(log_path)
            _state["log_path"].parent.mkdir(parents=True, exist_ok=True)
        if run_meta is not None:
            _state["run_meta"] = dict(run_meta)
        _state["configured"] = True
        # 打印一次落点，方便实验日志里留痕
        print(f"[call_logger] API call audit log → {_state['log_path']}")


def ensure_configured():
    if not _state["configured"]:
        configure()


def is_disabled():
    return _state.get("disabled", False)


def log_path():
    return _state.get("log_path")


def set_context(**fields):
    """合并更新调用上下文（cell 级字段由实验脚本设置）。"""
    with _lock:
        _state["context"].update(fields)


def clear_context():
    with _lock:
        _state["context"] = {}


def get_context():
    with _lock:
        return dict(_state["context"])


# ── 记录写入 ────────────────────────────────────────────────────────────────

def log_call(record: dict):
    """写一条调用记录。禁用或未配置路径时静默跳过，绝不影响主流程。"""
    try:
        ensure_configured()
        if is_disabled() or not _state["log_path"]:
            return
        entry = {
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_meta":  _state.get("run_meta") or None,
            "context":   get_context() or None,
        }
        entry.update(record)
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with _lock:
            with open(_state["log_path"], "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as exc:  # 审计日志绝不能打断实验
        print(f"[call_logger] WARN: failed to write call record: {exc}")




# ── 价格快照 ────────────────────────────────────────────────────────────────

def write_pricing_snapshot(path=None, extra=None):
    """在 run 开始时固化价格表；extra 可覆盖/追加渠道价格。"""
    if path is None:
        ensure_configured()
        base = _state["log_path"].parent if _state["log_path"] else (ROOT / "logs" / "api_calls")
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"pricing_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    snapshot = {
        "snapshot_written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prices": CURRENT_PRICES,
        "extra":  extra or None,
        "note":   "跑正式实验前请在 agicto 控制台/各官方定价页复核并更新；"
                  "DeepSeek 官方为分时定价，费用核算需结合调用时刻。",
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[call_logger] pricing snapshot → {path}")
    return path


# ── 余额探针（尽力而为）────────────────────────────────────────────────────

def probe_balance(api_key=None, base_url=None, account_uuid=None, timeout=15):
    """
    查询中转站账户余额，用于每 cell 前后对账。失败返回 None，绝不抛异常。

    agicto 文档口径: POST /v1/enterprise/account {"uuid": ...} → data.account
    （需要账户 uuid，来源环境变量 AGICTO_ACCOUNT_UUID，单位未注明）。
    同时尝试 one-api 系标准路由 /v1/dashboard/billing/subscription 作为兜底。
    """
    import requests

    base = (base_url or "https://api.agicto.cn").rstrip("/")
    uuid = account_uuid or os.environ.get("AGICTO_ACCOUNT_UUID")
    results = {}
    try:
        if uuid:
            r = requests.post(f"{base}/v1/enterprise/account",
                              json={"uuid": uuid}, timeout=timeout)
            results["enterprise_account"] = {
                "http_status": r.status_code,
                "body": r.text[:500],
            }
    except Exception:
        pass
    if api_key:
        try:
            r = requests.get(f"{base}/v1/dashboard/billing/subscription",
                             headers={"Authorization": f"Bearer {api_key}"},
                             timeout=timeout)
            results["billing_subscription"] = {
                "http_status": r.status_code,
                "body": r.text[:500],
            }
        except Exception:
            pass
    if not results:
        return None
    out = {"probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "base_url": base, "results": results,
           "note": "单位以控制台为准；agicto 文档未注明 account 字段单位"}
    log_call({"event": "balance_probe", "balance": out})
    return out
