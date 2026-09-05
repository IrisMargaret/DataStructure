# -*- coding: utf-8 -*-
"""OpenAI 兼容大模型 API 的轻量客户端（仅用于论文拆解 Agent）。

- 只从 os.environ 读取配置（.env 由应用入口 load_dotenv 注入）；
- chat_json(): 请求 /chat/completions，解析并返回 JSON 对象；
- 失败（网络/超时/格式错误）一律返回 None，由上层回退规则拆解；
- 任何异常路径都不打印密钥与请求体。
"""

import json
import os
import re

import requests

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def is_configured():
    """是否已配置可用的模型接口（base 与 key 同时存在）。"""
    return bool(os.getenv("LLM_API_BASE")) and bool(os.getenv("LLM_API_KEY"))


def _settings():
    return {
        "base": os.getenv("LLM_API_BASE", "").rstrip("/"),
        "key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", ""),
        "timeout": float(os.getenv("LLM_TIMEOUT", "30")),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
    }


def chat_json(system_prompt, user_prompt):
    """请求模型返回一个 JSON 对象；任何失败均返回 None。"""
    cfg = _settings()
    if not (cfg["base"] and cfg["key"] and cfg["model"]):
        return None
    url = f"{cfg['base']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "temperature": cfg["temperature"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {cfg['key']}"}

    for attempt in range(2):  # 最多重试 1 次
        try:
            resp = requests.post(url, json=payload, headers=headers,
                                 timeout=cfg["timeout"])
            if resp.status_code != 200:
                return None
            content = resp.json()["choices"][0]["message"]["content"]
            return _parse_json(content)
        except (requests.RequestException, KeyError, IndexError,
                ValueError, TypeError):
            continue
    return None


def _parse_json(content):
    """容忍 ```json 围栏与前后杂讯的 JSON 解析。"""
    if not content:
        return None
    match = _FENCE_RE.search(content)
    candidate = match.group(1) if match else content
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def test_connection(cfg=None):
    """用给定配置（缺省取当前环境）发一次最小 chat 请求，用于「设置-测试连接」。

    返回 (ok, message)；message 为面向用户的中文提示，不含 Key 与请求体。
    """
    base = ((cfg or {}).get("api_base") or os.getenv("LLM_API_BASE", "")) \
        .strip().rstrip("/")
    key = ((cfg or {}).get("api_key") or os.getenv("LLM_API_KEY", "")).strip()
    model = ((cfg or {}).get("model") or os.getenv("LLM_MODEL", "")).strip()
    if not base or not key or not model:
        return False, "请先填写 API 地址、Key 与模型名"
    try:
        timeout = float((cfg or {}).get("timeout")
                        or os.getenv("LLM_TIMEOUT", "30"))
    except (TypeError, ValueError):
        timeout = 30.0
    url = base + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "ping"}],
    }
    headers = {"Authorization": "Bearer " + key}
    try:
        resp = requests.post(url, json=payload, headers=headers,
                             timeout=timeout)
    except requests.exceptions.Timeout:
        return False, "连接超时：请检查 API 地址与网络"
    except requests.exceptions.ConnectionError:
        return False, "无法连接服务器：请检查 API 地址（需含 /v1 等路径）与网络"
    except requests.exceptions.RequestException as exc:
        return False, "请求失败：" + exc.__class__.__name__

    if resp.status_code == 200:
        return True, "连接成功"
    if resp.status_code == 401:
        return False, "API Key 无效或未授权（401）"
    if resp.status_code in (400, 404):
        hint = ""
        try:
            body = resp.json()
            hint = (body.get("error", {}).get("message") or "")[:140]
        except Exception:
            pass
        tail = hint if hint else "：请检查模型名与地址路径"
        return False, "请求被拒绝（" + str(resp.status_code) + "）" + tail
    if resp.status_code >= 500:
        return False, "服务端错误（" + str(resp.status_code) + "），请稍后重试或核对模型名"
    return False, "未知响应（" + str(resp.status_code) + "）"

