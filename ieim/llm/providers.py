from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    usage: Optional[dict[str, Any]]


class LLMProvider:
    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        raise NotImplementedError


class OpenAIChatCompletionsProvider(LLMProvider):
    def __init__(self, *, api_base: Optional[str] = None) -> None:
        default_base = "https://api.openai.com/v1"
        api_base = api_base or os.getenv("OPENAI_API_BASE") or default_base
        self._api_base = api_base.rstrip("/")
        self._default_base = default_base

    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            if self._api_base != self._default_base:
                api_key = "local"
            else:
                raise LLMProviderError("OPENAI_API_KEY is not set")

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }

        req = urllib.request.Request(
            url=f"{self._api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except Exception as e:
            raise LLMProviderError(f"openai request failed: {e}") from e

        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise LLMProviderError(f"openai response is not JSON: {e}") from e

        choices = obj.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderError("openai response missing choices")
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("openai response missing message content")

        usage = obj.get("usage") if isinstance(obj, dict) else None
        return ProviderResponse(content=content, usage=usage if isinstance(usage, dict) else None)


class DisabledLLMProvider(LLMProvider):
    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        raise LLMProviderError("LLM provider is disabled")


class OllamaChatProvider(LLMProvider):
    def __init__(self, *, host: Optional[str] = None) -> None:
        host = host or os.getenv("OLLAMA_HOST") or "http://localhost:11434"
        self._host = host.rstrip("/")

    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": float(temperature),
                "num_predict": int(max_tokens),
            },
        }

        req = urllib.request.Request(
            url=f"{self._host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except Exception as e:
            raise LLMProviderError(f"ollama request failed: {e}") from e

        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise LLMProviderError(f"ollama response is not JSON: {e}") from e

        message = obj.get("message") if isinstance(obj, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            content = obj.get("response") if isinstance(obj, dict) else None
        if not isinstance(content, str) or not content.strip():
            # Fallback to /api/generate for models that don't return chat content.
            fallback_payload: dict[str, Any] = {
                "model": model,
                "prompt": system_prompt + "\n\n" + user_prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": float(temperature),
                    "num_predict": int(max_tokens),
                },
            }
            fallback_req = urllib.request.Request(
                url=f"{self._host}/api/generate",
                data=json.dumps(fallback_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(fallback_req, timeout=60) as resp:
                    raw = resp.read()
            except Exception as e:
                raise LLMProviderError(f"ollama generate request failed: {e}") from e
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception as e:
                raise LLMProviderError(f"ollama generate response is not JSON: {e}") from e
            content = obj.get("response") if isinstance(obj, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("ollama response missing content")

        usage: dict[str, Any] = {}
        for k in ["prompt_eval_count", "eval_count", "total_duration", "load_duration"]:
            v = obj.get(k) if isinstance(obj, dict) else None
            if isinstance(v, (int, float)):
                usage[k] = v

        return ProviderResponse(content=content, usage=usage or None)
