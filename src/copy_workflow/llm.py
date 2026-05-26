from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from loguru import logger
from pydantic import BaseModel, ValidationError

from .cache import JSONCache, cache_key
from .config import Config


@dataclass
class LLMResponse:
    content: str
    raw: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    cached: bool = False


class DeepSeekClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.cache = JSONCache(cfg.paths.cache)
        self._configure_logger()

    def _configure_logger(self) -> None:
        log_file = self.cfg.paths.logs / "llm.jsonl"
        # idempotent: only add the sink once per process
        if not getattr(self, "_logger_configured", False):
            logger.add(
                log_file,
                serialize=True,
                rotation="50 MB",
                enqueue=True,
                level="INFO",
            )
            self._logger_configured = True

    def chat(
        self,
        *,
        system: str,
        user: str,
        model: str,
        json_mode: bool = False,
        temperature: float = 0.7,
        no_cache: bool = False,
    ) -> LLMResponse:
        key = cache_key(system, user, model, str(json_mode), str(temperature))

        if not no_cache:
            hit = self.cache.get(key)
            if hit is not None:
                logger.info(
                    {
                        "event": "llm_cache_hit",
                        "model": model,
                        "key": key,
                    }
                )
                return LLMResponse(
                    content=hit["content"],
                    raw=hit.get("raw", {}),
                    prompt_tokens=hit.get("prompt_tokens", 0),
                    completion_tokens=hit.get("completion_tokens", 0),
                    cached=True,
                )

        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.secrets.deepseek_api_key}",
        }

        last_err: Exception | None = None
        for attempt in range(1, self.cfg.generation.retries + 1):
            t0 = time.time()
            try:
                resp = requests.post(
                    self.cfg.secrets.deepseek_api_url,
                    json=body,
                    headers=headers,
                    timeout=self.cfg.generation.request_timeout_sec,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {}) or {}
                out = LLMResponse(
                    content=content,
                    raw=data,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
                logger.info(
                    {
                        "event": "llm_call",
                        "model": model,
                        "attempt": attempt,
                        "latency_ms": int((time.time() - t0) * 1000),
                        "prompt_tokens": out.prompt_tokens,
                        "completion_tokens": out.completion_tokens,
                    }
                )
                self.cache.set(
                    key,
                    {
                        "content": out.content,
                        "raw": out.raw,
                        "prompt_tokens": out.prompt_tokens,
                        "completion_tokens": out.completion_tokens,
                    },
                )
                return out
            except (requests.RequestException, KeyError, ValueError) as e:
                last_err = e
                logger.warning(
                    {
                        "event": "llm_retry",
                        "attempt": attempt,
                        "error": repr(e),
                    }
                )
                time.sleep(self.cfg.generation.retry_backoff_sec * attempt)

        raise RuntimeError(f"LLM call failed after retries: {last_err}")


def parse_json_strict(text: str) -> dict[str, Any]:
    """Strip markdown fences if any, then json.loads."""
    s = text.strip()
    if s.startswith("```"):
        # remove leading ```json or ``` and trailing ```
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return json.loads(s)


def call_with_validation(
    client: DeepSeekClient,
    *,
    system: str,
    user: str,
    model: str,
    schema: type[BaseModel],
    temperature: float = 0.7,
    no_cache: bool = False,
) -> tuple[BaseModel, LLMResponse]:
    """Call the LLM in JSON mode, validate against `schema`. One auto-repair retry."""
    resp = client.chat(
        system=system,
        user=user,
        model=model,
        json_mode=True,
        temperature=temperature,
        no_cache=no_cache,
    )
    try:
        data = parse_json_strict(resp.content)
        return schema.model_validate(data), resp
    except (json.JSONDecodeError, ValidationError) as e:
        repair_user = (
            f"{user}\n\n---\nYour previous output was rejected with this error:\n"
            f"{e}\n\nReturn corrected JSON only, no commentary."
        )
        resp2 = client.chat(
            system=system,
            user=repair_user,
            model=model,
            json_mode=True,
            temperature=0.2,
            no_cache=True,
        )
        data = parse_json_strict(resp2.content)
        return schema.model_validate(data), resp2


def load_prompt(name: str) -> str:
    p = Path(__file__).resolve().parent / "prompts" / name
    return p.read_text(encoding="utf-8")
