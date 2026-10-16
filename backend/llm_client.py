import os
import re
import time
import random
import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Callable, Coroutine
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class LLMUnavailableError(Exception):
    """Raised when all LLM retries and fallback providers have failed."""
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class TokenBucketLimiter:
    """
    Client-side token-bucket rate limiter to prevent concurrent requests
    from overflowing provider rate limits.
    """
    def __init__(self, capacity: float = 5.0, refill_rate: float = 0.5):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = float(refill_rate)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    async def acquire(self, wait_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None):
        wait_time = 0.0
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return

            needed = 1.0 - self.tokens
            wait_time = needed / self.refill_rate

        if wait_time > 0:
            if wait_callback:
                try:
                    await wait_callback(f"Pacing requests: rate limiter holding for {wait_time:.1f}s...")
                except Exception:
                    pass
            await asyncio.sleep(wait_time)
            async with self._lock:
                self.tokens = max(0.0, self.tokens - 1.0)

    def sync_acquire(self):
        with self._sync_lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            needed = 1.0 - self.tokens
            wait_time = needed / self.refill_rate

        if wait_time > 0:
            time.sleep(wait_time)
            with self._sync_lock:
                self.tokens = max(0.0, self.tokens - 1.0)


def extract_retry_after(err: Exception) -> float | None:
    """Extracts Retry-After header or seconds from exception or response."""
    resp = getattr(err, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", None) or {}
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra:
            try:
                return float(ra)
            except (ValueError, TypeError):
                pass

    body = getattr(err, "body", None)
    if isinstance(body, dict):
        msg = body.get("error", {}).get("message", "")
        m = re.search(r"try again in ([\d\.]+)s", msg, re.I)
        if m:
            return float(m.group(1))

    err_str = str(err)
    m = re.search(r"try again in ([\d\.]+)s", err_str, re.I)
    if m:
        return float(m.group(1))

    m2 = re.search(r"retry[- ]after:?\s*([\d\.]+)", err_str, re.I)
    if m2:
        return float(m2.group(1))

    return None


@dataclass
class ProviderCandidate:
    name: str
    client: Groq
    model: str
    is_fallback: bool = False


class ResilientLLMClient:
    """
    Resilient wrapper around Groq / OpenAI-compatible LLM endpoints:
    - Client-side token-bucket limiter
    - Exponential backoff with jitter and Retry-After support (max 4 retries)
    - Fallback chain: Primary Groq -> Smaller Groq -> Secondary API key -> Optional 2nd Provider
    - Per-request timeout and clear LLMUnavailableError
    - Status callbacks for real-time SSE streaming
    """
    def __init__(self):
        capacity = float(os.getenv("LLM_RATE_LIMIT_CAPACITY", "5.0"))
        refill_rate = float(os.getenv("LLM_RATE_LIMIT_REFILL_RATE", "0.5"))
        self.limiter = TokenBucketLimiter(capacity=capacity, refill_rate=refill_rate)
        self._clients: dict[tuple[str, str | None], Groq] = {}

    def _get_client(self, api_key: str | None, base_url: str | None = None) -> Groq:
        key = (api_key or "", base_url)
        if key not in self._clients:
            kwargs = {}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            self._clients[key] = Groq(**kwargs)
        return self._clients[key]

    def get_candidates(self, model_type: str = "vision") -> list[ProviderCandidate]:
        candidates: list[ProviderCandidate] = []

        primary_key = os.getenv("GROQ_API_KEY")
        secondary_key = os.getenv("GROQ_SECONDARY_API_KEY") or os.getenv("GROQ_API_KEY_SECONDARY")

        if model_type == "vision":
            primary_model = os.getenv("GROQ_PRIMARY_VISION_MODEL", "qwen/qwen3.8-27b")
            fallback_model = os.getenv("GROQ_FALLBACK_VISION_MODEL", "meta-llama/llama-4-scout-17b-16k")
        else:
            primary_model = os.getenv("GROQ_PRIMARY_TEXT_MODEL", "openai/gpt-oss-120b")
            fallback_model = os.getenv("GROQ_FALLBACK_TEXT_MODEL", "llama-3.1-8b-instant")

        # 1. Primary Groq model
        if primary_key:
            candidates.append(ProviderCandidate(
                name="Primary Groq Model",
                client=self._get_client(primary_key),
                model=primary_model,
                is_fallback=False
            ))

        # 2. Smaller Groq model (fallback)
        if primary_key and fallback_model != primary_model:
            candidates.append(ProviderCandidate(
                name=f"Smaller Groq Model ({fallback_model})",
                client=self._get_client(primary_key),
                model=fallback_model,
                is_fallback=True
            ))

        # 3. Secondary Groq API key
        if secondary_key:
            candidates.append(ProviderCandidate(
                name="Secondary Groq API Key",
                client=self._get_client(secondary_key),
                model=primary_model,
                is_fallback=True
            ))

        # 4. Optional second provider (OpenAI-compatible)
        sec_base_url = os.getenv("SECONDARY_PROVIDER_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        sec_api_key = os.getenv("SECONDARY_PROVIDER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if sec_base_url or sec_api_key:
            sec_model = (
                (os.getenv("SECONDARY_PROVIDER_VISION_MODEL") or os.getenv("OPENAI_VISION_MODEL") or "gpt-4o-mini")
                if model_type == "vision"
                else (os.getenv("SECONDARY_PROVIDER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini")
            )
            candidates.append(ProviderCandidate(
                name="Secondary Provider (OpenAI-compatible)",
                client=self._get_client(sec_api_key, base_url=sec_base_url),
                model=sec_model,
                is_fallback=True
            ))

        # Fallback safety if no candidate was registered
        if not candidates:
            candidates.append(ProviderCandidate(
                name="Default Groq",
                client=self._get_client(primary_key),
                model=primary_model,
                is_fallback=False
            ))

        return candidates

    async def chat_completion(
        self,
        messages: list[dict],
        model_type: str = "vision",
        response_format: dict | None = None,
        max_tokens: int = 1200,
        temperature: float | None = None,
        timeout: float = 40.0,
        max_retries_per_candidate: int = 4,
        status_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> Any:
        candidates = self.get_candidates(model_type=model_type)
        all_errors: list[str] = []

        async def emit(msg: str):
            if status_callback:
                try:
                    res = status_callback(msg)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

        for c_idx, candidate in enumerate(candidates):
            if c_idx > 0:
                await emit(f"Switched to fallback model: {candidate.model} ({candidate.name})")

            for attempt in range(max_retries_per_candidate):
                await self.limiter.acquire(wait_callback=emit)

                req_kwargs: dict[str, Any] = {
                    "model": candidate.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if response_format is not None:
                    req_kwargs["response_format"] = response_format
                if temperature is not None:
                    req_kwargs["temperature"] = temperature

                try:
                    # Enforce per-request timeout
                    response = await asyncio.wait_for(
                        asyncio.to_thread(candidate.client.chat.completions.create, **req_kwargs),
                        timeout=timeout,
                    )
                    return response

                except asyncio.TimeoutError:
                    err_desc = f"Request timed out after {timeout}s on {candidate.model}"
                    all_errors.append(err_desc)
                    if attempt < max_retries_per_candidate - 1:
                        delay = min(15.0, (1.5 * (2 ** attempt)) + random.uniform(0.1, 0.5))
                        await emit(f"{err_desc}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries_per_candidate})...")
                        await asyncio.sleep(delay)
                    else:
                        break

                except Exception as api_err:
                    err_str = str(api_err)
                    err_lower = err_str.lower()
                    all_errors.append(f"{candidate.name} ({candidate.model}): {err_str[:140]}")

                    is_rate_limit = ("429" in err_lower or "rate limit" in err_lower or "tokens per minute" in err_lower)
                    is_server_error = ("500" in err_lower or "502" in err_lower or "503" in err_lower or "504" in err_lower)

                    # Check for Retry-After header or seconds in error
                    ra = extract_retry_after(api_err) if is_rate_limit else None
                    if ra is not None:
                        delay = min(45.0, max(1.0, ra) + random.uniform(0.1, 0.5))
                    else:
                        delay = min(30.0, (1.0 * (2 ** attempt)) + random.uniform(0.1, 0.8))

                    if (is_rate_limit or is_server_error) and attempt < max_retries_per_candidate - 1:
                        await emit(
                            f"Rate limit on {candidate.model}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries_per_candidate})..."
                            if is_rate_limit
                            else f"Server error on {candidate.model}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue

                    # If not a rate limit / server error, or retries exhausted, move to next candidate in chain
                    break

        error_summary = "; ".join(all_errors[-4:])
        raise LLMUnavailableError(
            f"All LLM retries and fallback providers failed. Errors: {error_summary}",
            errors=all_errors,
        )

    def sync_chat_completion(
        self,
        messages: list[dict],
        model_type: str = "text",
        response_format: dict | None = None,
        max_tokens: int = 2000,
        temperature: float | None = 0.2,
        timeout: float = 35.0,
        max_retries_per_candidate: int = 4,
    ) -> Any:
        candidates = self.get_candidates(model_type=model_type)
        all_errors: list[str] = []

        for candidate in candidates:
            for attempt in range(max_retries_per_candidate):
                self.limiter.sync_acquire()
                req_kwargs: dict[str, Any] = {
                    "model": candidate.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if response_format is not None:
                    req_kwargs["response_format"] = response_format
                if temperature is not None:
                    req_kwargs["temperature"] = temperature

                try:
                    return candidate.client.chat.completions.create(**req_kwargs)
                except Exception as api_err:
                    err_str = str(api_err)
                    all_errors.append(f"{candidate.name} ({candidate.model}): {err_str[:120]}")
                    is_rate_limit = ("429" in err_str.lower() or "rate limit" in err_str.lower())
                    ra = extract_retry_after(api_err) if is_rate_limit else None
                    delay = ra + random.uniform(0.1, 0.5) if ra else min(20.0, (1.0 * (2 ** attempt)) + random.uniform(0.1, 0.5))
                    if is_rate_limit and attempt < max_retries_per_candidate - 1:
                        time.sleep(delay)
                        continue
                    break

        raise LLMUnavailableError(
            f"All LLM providers failed: {'; '.join(all_errors[-3:])}",
            errors=all_errors,
        )


# Global singleton resilient LLM client
resilient_llm_client = ResilientLLMClient()
