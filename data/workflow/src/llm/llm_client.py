# src/llm/llm_client.py
#
# 统一LLM客户端，支持多个提供商：
#   - DeepSeek (deepseek-chat, deepseek-coder)
#   - Qwen     (qwen-max, qwen-plus, qwen-turbo)
#   - GLM      (glm-4, glm-4-flash)
#
# API Key配置（任选其一）：
#   config/deepseek_api_key.txt
#   config/qwen_api_key.txt
#   config/glm_api_key.txt
#
# 使用方式（在config_registry.py或实验脚本里设置）：
#   LLM_PROVIDER = "deepseek"   # 默认
#   LLM_PROVIDER = "qwen"
#   LLM_PROVIDER = "glm"

import logging
import os
import time
import requests

from src.llm import call_logger

logger = logging.getLogger(__name__)

class LLMAPIError(RuntimeError):
    """Provider or gateway returned an API-level failure."""

class LLMEmptyResponseError(LLMAPIError):
    """Provider returned HTTP 200 but no model content."""


# ── 提供商配置 ────────────────────────────────────────────────────────────────

PROVIDER_CONFIGS = {
    "deepseek": {
        "url":         "https://api.agicto.cn/v1/chat/completions",
        "model":       "deepseek-v4-pro",
        "key_file":    "deepseek_api_key.txt",
        "temperature": 0.2,
    },
    "deepseek-flash": {
        "url":         "https://api.agicto.cn/v1/chat/completions",
        "model":       "deepseek-v4-flash",
        "key_file":    "deepseek_api_key.txt",
        "temperature": 0.2,
    },
    "qwen": {
        "url":         "https://api.agicto.cn/v1/chat/completions",
        "model":       "qwen3-max",
        "key_file":    "qwen_api_key.txt",
        "temperature": 0.2,
    },
    "glm": {
        "url":         "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "model":       "glm-4",
        "key_file":    "glm_api_key.txt",
        "temperature": 0.2,
    },
    "openai": {
        "url":         "https://api.agicto.cn/v1/chat/completions",
        "model":       "gpt-5.1",
        "key_file":    "openai_api_key.txt",
        "temperature": 0.2,
    },
}

# 默认提供商（可被环境变量或参数覆盖）
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek")


# ── API Key读取 ───────────────────────────────────────────────────────────────

def read_api_key(path: str) -> str:
    """读取API key文件。保持与原deepseek_client.py兼容。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_api_key(provider: str = None, config_dir: str = None) -> str:
    """
    自动读取对应提供商的API key。

    Parameters
    ----------
    provider   : 提供商名称，默认使用DEFAULT_PROVIDER
    config_dir : config目录路径，默认自动推断
    """
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(f"Unknown provider: '{provider}'. "
                         f"Available: {list(PROVIDER_CONFIGS.keys())}")

    # Environment keys work for both the fresh-run launcher and workflow.
    env_name = {"openai": "OPENAI_API_KEY", "qwen": "QWEN_API_KEY",
                "deepseek-flash": "DEEPSEEK_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
                "glm": "GLM_API_KEY"}.get(provider)
    if env_name and os.environ.get(env_name, "").strip():
        return os.environ[env_name].strip()

    if config_dir is None:
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "config"
        )

    key_file = PROVIDER_CONFIGS[provider]["key_file"]
    key_path = os.path.join(config_dir, key_file)

    if not os.path.isfile(key_path):
        raise FileNotFoundError(
            f"API key file not found: {key_path}\n"
            f"Please create it with your {provider} API key."
        )

    return read_api_key(key_path)


# ── 统一调用接口 ──────────────────────────────────────────────────────────────

class LLMResponse(str):
    """str 兼容的返回值，额外携带 .meta（usage / 实际模型版本 / 时延 / 重试）。

    既有调用方把它当普通字符串用不受影响；需要审计信息的调用方读 .meta。
    """

    def __new__(cls, content: str, meta: dict = None):
        obj = super().__new__(cls, content)
        obj.meta = meta or {}
        return obj


def _normalize_usage(u):
    """把 OpenAI 兼容的 usage 字典拍平成稳定 schema；无 usage 返回 None。"""
    if not isinstance(u, dict) or not u:
        return None
    out = {k: u[k] for k in
           ("prompt_tokens", "completion_tokens", "total_tokens")
           if u.get(k) is not None}
    ptd = u.get("prompt_tokens_details") or {}
    ctd = u.get("completion_tokens_details") or {}
    if ptd.get("cached_tokens") is not None:
        out["cached_tokens"] = ptd["cached_tokens"]
    if ctd.get("reasoning_tokens") is not None:
        out["reasoning_tokens"] = ctd["reasoning_tokens"]
    # 部分网关把细节字段直接平铺在 usage 上
    for k in ("cached_tokens", "cache_hit_tokens", "reasoning_tokens"):
        if u.get(k) is not None and k not in out:
            out[k] = u[k]
    return out or dict(u)


def _thinking_config(provider: str, payload: dict):
    """记录每次调用实际生效的 thinking/reasoning 配置（复现性关键）。"""
    if provider in ("deepseek", "deepseek-flash"):
        return {"enable_thinking": False, "thinking": "disabled"}
    if provider == "qwen":
        return {"enable_thinking": False}
    if provider == "openai":
        return {"reasoning_effort": payload.get("reasoning_effort", "gateway-default")}
    return None


def call_llm(
    prompt: str,
    api_key: str,
    provider: str = None,
    max_retries: int = 3,
    retry_delay: float = 10.0,
    timeout: int = 120,
    max_tokens: int = None,
    reasoning_effort: str = None,
    call_meta: dict = None,
) -> str:
    """
    统一LLM调用接口，支持DeepSeek、Qwen、GLM。

    Parameters
    ----------
    prompt           : 输入prompt
    api_key          : 对应提供商的API key
    provider         : 提供商名称（默认使用DEFAULT_PROVIDER）
    max_retries      : 最大重试次数
    retry_delay      : 重试间隔秒数
    timeout          : 读取超时秒数（连接超时固定30秒）
    max_tokens       : 显式输出上限。None=沿用网关默认（历史行为）。
                       正式重跑建议显式钉死为 8192 并保持一致。
    reasoning_effort : 仅 openai 分支生效（gpt-5.1 的推理预算）。
                       None=网关默认；建议显式设置以统一三家的推理条件。
    call_meta        : 附加到审计记录的任意元数据（如 {"cell": "..."}）。

    Returns
    -------
    模型响应文本（LLMResponse，str 子类；审计信息见 .meta）。
    每次调用（含最终失败）都会写一条 JSONL 到 call_logger。
    """
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(f"Unknown provider: '{provider}'")

    cfg     = PROVIDER_CONFIGS[provider]
    url     = cfg["url"]
    model   = cfg["model"]
    temp    = cfg["temperature"]

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model":       model,
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": temp,
    }
    # 禁用 thinking 模式，避免超时和额外 token 消耗
    if provider == "qwen":
        payload["enable_thinking"] = False
    if provider in ("deepseek", "deepseek-flash"):
        payload["enable_thinking"] = False
        payload["thinking"] = {"type": "disabled"}
    if max_tokens is not None:
        # gpt-5.x 官方协议要求 max_completion_tokens，其余走 max_tokens
        if provider == "openai":
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
    if reasoning_effort is not None and provider == "openai":
        payload["reasoning_effort"] = reasoning_effort

    payload["stream"] = True  # 流式返回，避免长prompt时连接挂起
    # 让网关在流的末尾回传 usage；个别网关不认识时会在下方 400 分支自动摘除
    payload["stream_options"] = {"include_usage": True}

    request_view = {
        "temperature":     temp,
        "max_tokens":      max_tokens,
        "reasoning_effort": reasoning_effort,
        "thinking":        _thinking_config(provider, payload),
        "prompt_chars":    len(prompt),
    }

    def _audit(**fields):
        call_logger.log_call({
            "event": "llm_call", "provider": provider, "endpoint": url,
            "model_requested": model, "attempts": attempt, "max_retries": max_retries,
            "request": request_view, "call_meta": call_meta or None,
            **fields,
        })

    last_exc = None
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        # 每次调用附带的上下文（cell/attempt/repair 等）由实验脚本注入
        stream_usage = None
        stream_model = None
        stream_id    = None
        finish_reason = None
        ttfb = None
        try:
            # 禁用连接复用，避免僵死连接导致永久挂起
            headers["Connection"] = "close"
            t0 = time.monotonic()
            response = requests.post(
                url, headers=headers, json=payload,
                timeout=(60, timeout), stream=True)
            response.raise_for_status()
            # Gateway may return HTTP 200 with an error JSON or empty stream.
            full_content = []
            parsed_chunks = 0
            raw_lines = []
            for line in response.iter_lines():
                if ttfb is None:
                    ttfb = (time.monotonic() - t0) * 1000
                if not line:
                    continue
                line = line.decode("utf-8") if isinstance(line, bytes) else line
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                raw_lines.append(line[:500])
                try:
                    import json as _json
                    chunk = _json.loads(line)
                except Exception:
                    continue

                parsed_chunks += 1
                # usage 通常在最后一个 choices 为空的 chunk 里（include_usage）
                if isinstance(chunk.get("usage"), dict):
                    stream_usage = chunk["usage"]
                if chunk.get("model"):
                    stream_model = chunk["model"]
                if chunk.get("id"):
                    stream_id = chunk["id"]
                error = chunk.get("error")
                if error:
                    detail = (
                        error.get("message") or error.get("detail") or repr(error)
                        if isinstance(error, dict) else str(error)
                    )
                    raise LLMAPIError(f"[{provider}] stream error: {detail}")

                choices = chunk.get("choices") or []
                if not choices:
                    detail = chunk.get("message") or chunk.get("detail")
                    if detail:
                        raise LLMAPIError(f"[{provider}] gateway error: {detail}")
                    continue

                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
                token = choices[0].get("delta", {}).get("content", "")
                if token:
                    full_content.append(token)

            total_ms = (time.monotonic() - t0) * 1000
            content = "".join(full_content)
            if not content.strip():
                raise LLMEmptyResponseError(
                    f"[{provider}] empty response content "
                    f"(parsed_chunks={parsed_chunks}, raw={raw_lines[:3]!r})"
                )

            lower = content.lower()
            infra_markers = (
                "insufficient balance", "insufficient quota",
                "quota exceeded", "credit balance",
                "余额不足", "额度不足", "余额已用完",
            )
            if any(marker in lower for marker in infra_markers):
                raise LLMAPIError(
                    f"[{provider}] provider error content: {content[:300]!r}"
                )

            meta = {
                "provider":        provider,
                "endpoint":        url,
                "http_status":     response.status_code,
                "model_requested": model,
                "model_resolved":  stream_model or model,
                "response_id":     stream_id,
                "finish_reason":   finish_reason,
                "usage":           _normalize_usage(stream_usage),
                "usage_raw":       stream_usage,
                "latency_ttfb_ms": round(ttfb, 1) if ttfb is not None else None,
                "latency_total_ms": round(total_ms, 1),
                "attempts":        attempt,
                "request":         request_view,
            }
            _audit(
                http_status=response.status_code,
                model_resolved=meta["model_resolved"],
                response_id=stream_id,
                finish_reason=finish_reason,
                usage=meta["usage"], usage_raw=stream_usage,
                latency_ttfb_ms=meta["latency_ttfb_ms"],
                latency_total_ms=meta["latency_total_ms"],
                content_chars=len(content),
                error=None,
            )
            return LLMResponse(content, meta)

        except requests.exceptions.Timeout as e:
            last_exc = e
            logger.warning(
                f"[{provider}] Timeout on attempt {attempt}/{max_retries}. "
                f"Retrying in {retry_delay}s…"
            )
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400 and \
                    "stream_options" in (e.response.text or "")[:2000]:
                # 网关不认识 stream_options：摘掉后立刻重试，不消耗重试次数
                # （payload 中该键已移除，此分支至多触发一次，无死循环风险）
                payload.pop("stream_options", None)
                request_view["stream_options_dropped"] = True
                logger.warning(
                    f"[{provider}] gateway rejected stream_options; "
                    f"retrying without it (usage capture disabled for this gateway)"
                )
                last_exc = e
                attempt -= 1
                continue
            if e.response is not None and e.response.status_code < 500:
                _audit(http_status=e.response.status_code,
                       error=f"HTTPError: {e.response.status_code} "
                             f"{(e.response.text or '')[:300]}")
                raise
            last_exc = e
            logger.warning(
                f"[{provider}] HTTP {e.response.status_code if e.response is not None else '?'} "
                f"on attempt {attempt}/{max_retries}. Retrying in {retry_delay}s…"
            )
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            logger.warning(
                f"[{provider}] Connection error on attempt {attempt}/{max_retries}. "
                f"Retrying in {retry_delay}s…"
            )
        except LLMAPIError as e:
            # 网关 200-带错误 / 空响应 / 余额类错误：不重试（与原行为一致），但留审计记录
            _audit(error=f"{type(e).__name__}: {e}")
            raise

        if attempt < max_retries:
            time.sleep(retry_delay)

    _audit(error=f"{type(last_exc).__name__}: {last_exc}")
    raise last_exc


# ── 向后兼容：保留call_deepseek接口 ──────────────────────────────────────────

def call_deepseek(
    prompt: str,
    api_key: str,
    max_retries: int = 3,
    retry_delay: float = 10.0,
    timeout: int = 120,
) -> str:
    """向后兼容接口，等价于call_llm(..., provider='deepseek')。"""
    return call_llm(
        prompt      = prompt,
        api_key     = api_key,
        provider    = "deepseek",
        max_retries = max_retries,
        retry_delay = retry_delay,
        timeout     = timeout,
    )


# ── 测试入口 ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider", default=DEFAULT_PROVIDER,
        choices=list(PROVIDER_CONFIGS.keys()),
        help="LLM provider to test"
    )
    args = parser.parse_args()

    provider = args.provider
    print(f"[INFO] Testing provider: {provider}")
    print(f"[INFO] Model: {PROVIDER_CONFIGS[provider]['model']}")

    try:
        api_key = get_api_key(provider)
        print(f"[INFO] API key loaded: {api_key[:6]}...")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return

    test_prompt = (
        f"Reply with exactly one sentence: "
        f"confirm you are {provider} and you are ready."
    )
    print(f"[INFO] Sending test prompt…\n")

    result = call_llm(test_prompt, api_key, provider=provider)
    print("[RESPONSE]")
    print(result)


if __name__ == "__main__":
    main()
