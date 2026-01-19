from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ieim.config import IEIMConfig
from ieim.llm.canonical_labels import build_canonical_labels_payload
from ieim.llm.contracts import load_prompt_json, sha256_prompt_pair, validate_contract_output
from ieim.llm.file_cache import DailyCallCounter, FileLLMCache, LLMCacheKey
from ieim.llm.providers import (
    DisabledLLMProvider,
    LLMProvider,
    LLMProviderError,
    OllamaChatProvider,
    OpenAIChatCompletionsProvider,
)
from ieim.llm.redaction import redact_preserve_length


class LLMAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMStageResponse:
    output: dict[str, Any]
    model_info: dict[str, Any]
    cache_hit: bool


def _truncate_text(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if not lines:
        return cleaned
    # Drop the opening fence line (``` or ```json)
    cleaned = "\n".join(lines[1:])
    if "```" in cleaned:
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def _parse_json_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except Exception:
        cleaned = _strip_code_fences(content)
        try:
            parsed = json.loads(cleaned)
        except Exception:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def _minimized_normalized_message(*, normalized_message: dict, shorten: bool) -> dict[str, Any]:
    subject = str(normalized_message.get("subject_c14n") or "")
    body = str(normalized_message.get("body_text_c14n") or "")
    if shorten:
        body = _truncate_text(body, max_chars=1500)

    return {
        "message_id": str(normalized_message.get("message_id") or ""),
        "language": str(normalized_message.get("language") or ""),
        "subject_c14n": redact_preserve_length(subject),
        "body_text_c14n": redact_preserve_length(body),
    }


def _provider_from_config(cfg: IEIMConfig) -> LLMProvider:
    if cfg.classification.llm.provider == "openai":
        return OpenAIChatCompletionsProvider()
    if cfg.classification.llm.provider == "ollama":
        return OllamaChatProvider()
    if cfg.classification.llm.provider == "disabled":
        return DisabledLLMProvider()
    raise ValueError(f"unsupported LLM provider: {cfg.classification.llm.provider}")


class LLMAdapter:
    def __init__(
        self,
        *,
        repo_root: Path,
        config: IEIMConfig,
        provider: Optional[LLMProvider] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._repo_root = repo_root
        self._config = config
        self._provider = provider or _provider_from_config(config)
        self._cache = FileLLMCache(base_dir=cache_dir)
        self._counter = DailyCallCounter(base_dir=cache_dir)

    def _call(
        self,
        *,
        stage: str,
        task_prompt_path: str,
        contract_name: str,
        contract_version: str,
        prompt_version: str,
        token_budget: int,
        user_input: dict[str, Any],
    ) -> LLMStageResponse:
        system_prompt_bytes = (self._repo_root / "prompts" / "system_prompt.md").read_bytes()
        task_prompt_bytes = (self._repo_root / task_prompt_path).read_bytes()
        prompt_sha256 = sha256_prompt_pair(system_prompt=system_prompt_bytes, task_prompt=task_prompt_bytes)

        cache_key = LLMCacheKey(
            stage=stage,
            provider=self._config.classification.llm.provider,
            model_name=self._config.classification.llm.model_name,
            model_version=self._config.classification.llm.model_version,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            message_fingerprint=str(user_input.get("message_fingerprint") or ""),
        )

        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                validate_contract_output(name=contract_name, version=contract_version, output=cached.response)
            except Exception as e:
                raise LLMAdapterError(f"cached LLM output failed contract validation: {e}") from e
            return LLMStageResponse(
                output=cached.response,
                model_info={
                    "provider": self._config.classification.llm.provider,
                    "model_name": self._config.classification.llm.model_name,
                    "model_version": self._config.classification.llm.model_version,
                    "prompt_version": prompt_version,
                    "prompt_sha256": prompt_sha256,
                    "temperature": 0.0,
                    "max_tokens": int(token_budget),
                },
                cache_hit=True,
            )

        if not self._counter.can_consume(max_calls_per_day=self._config.classification.llm.max_calls_per_day):
            raise LLMAdapterError("LLM daily call cap reached")

        self._counter.consume()

        system_prompt = system_prompt_bytes.decode("utf-8")
        prompt_template = load_prompt_json(repo_root=self._repo_root, relative_path=task_prompt_path)
        prompt_template["input"] = user_input
        user_prompt = json.dumps(prompt_template, ensure_ascii=False, sort_keys=True)

        try:
            resp = self._provider.chat_json(
                model=self._config.classification.llm.model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=int(token_budget),
            )
        except LLMProviderError as e:
            raise LLMAdapterError(str(e)) from e

        try:
            parsed = _parse_json_response(resp.content)
        except Exception as e:
            raise LLMAdapterError(f"LLM response is not JSON: {e}") from e

        try:
            validate_contract_output(name=contract_name, version=contract_version, output=parsed)
        except Exception as e:
            raise LLMAdapterError(f"LLM output failed contract validation: {e}") from e

        self._cache.put(key=cache_key, response=parsed)

        return LLMStageResponse(
            output=parsed,
            model_info={
                "provider": self._config.classification.llm.provider,
                "model_name": self._config.classification.llm.model_name,
                "model_version": self._config.classification.llm.model_version,
                "prompt_version": prompt_version,
                "prompt_sha256": prompt_sha256,
                "temperature": 0.0,
                "max_tokens": int(token_budget),
            },
            cache_hit=False,
        )

    def classify(self, *, normalized_message: dict, message_fingerprint: str) -> LLMStageResponse:
        prompt_version = str(self._config.classification.llm.prompt_versions.get("classify") or "")
        if not prompt_version:
            raise ValueError("missing prompt version for classify")
        token_budget = int(self._config.classification.llm.token_budgets.get("classify") or 0)
        if token_budget <= 0:
            raise ValueError("invalid token budget for classify")

        canonical_labels = build_canonical_labels_payload()
        base_input = {
            "message_fingerprint": message_fingerprint,
            "normalized_message": _minimized_normalized_message(normalized_message=normalized_message, shorten=False),
            "attachment_texts": [],
            "canonical_labels": canonical_labels,
        }

        try:
            return self._call(
                stage="classify",
                task_prompt_path="prompts/classify_prompt.md",
                contract_name="ClassifyLLMOutput",
                contract_version="1.0.0",
                prompt_version=prompt_version,
                token_budget=token_budget,
                user_input=base_input,
            )
        except LLMAdapterError:
            retry_input = dict(base_input)
            retry_input["normalized_message"] = _minimized_normalized_message(
                normalized_message=normalized_message, shorten=True
            )
            return self._call(
                stage="classify",
                task_prompt_path="prompts/classify_prompt.md",
                contract_name="ClassifyLLMOutput",
                contract_version="1.0.0",
                prompt_version=prompt_version,
                token_budget=token_budget,
                user_input=retry_input,
            )

    def extract(self, *, normalized_message: dict, message_fingerprint: str, policies: dict) -> LLMStageResponse:
        prompt_version = str(self._config.classification.llm.prompt_versions.get("extract") or "")
        if not prompt_version:
            raise ValueError("missing prompt version for extract")
        token_budget = int(self._config.classification.llm.token_budgets.get("extract") or 0)
        if token_budget <= 0:
            raise ValueError("invalid token budget for extract")

        canonical_labels = build_canonical_labels_payload()
        base_input = {
            "message_fingerprint": message_fingerprint,
            "normalized_message": _minimized_normalized_message(normalized_message=normalized_message, shorten=False),
            "attachment_texts": [],
            "canonical_labels": canonical_labels,
            "policies": policies,
        }

        try:
            return self._call(
                stage="extract",
                task_prompt_path="prompts/extract_prompt.md",
                contract_name="ExtractLLMOutput",
                contract_version="1.0.0",
                prompt_version=prompt_version,
                token_budget=token_budget,
                user_input=base_input,
            )
        except LLMAdapterError:
            retry_input = dict(base_input)
            retry_input["normalized_message"] = _minimized_normalized_message(
                normalized_message=normalized_message, shorten=True
            )
            return self._call(
                stage="extract",
                task_prompt_path="prompts/extract_prompt.md",
                contract_name="ExtractLLMOutput",
                contract_version="1.0.0",
                prompt_version=prompt_version,
                token_budget=token_budget,
                user_input=retry_input,
            )
