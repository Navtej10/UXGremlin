import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from llm_client import (
    ResilientLLMClient,
    TokenBucketLimiter,
    LLMUnavailableError,
    extract_retry_after,
    ProviderCandidate,
)
from agent import run_agent_loop
from scoring import Step


def test_token_bucket_limiter():
    """Verify that token bucket paces and respects rate limit."""
    async def _run():
        limiter = TokenBucketLimiter(capacity=2.0, refill_rate=10.0)
        # First 2 requests should be acquired immediately without waiting
        await limiter.acquire()
        await limiter.acquire()
        assert limiter.tokens < 1.0

    asyncio.run(_run())


def test_extract_retry_after():
    """Verify parsing Retry-After from headers and error messages."""
    # From response header
    mock_err_header = Exception("Rate limit")
    mock_resp = MagicMock()
    mock_resp.headers = {"Retry-After": "3.5"}
    mock_err_header.response = mock_resp
    assert extract_retry_after(mock_err_header) == 3.5

    # From error string
    mock_err_msg = Exception("Rate limit reached. Please try again in 4.25s.")
    assert extract_retry_after(mock_err_msg) == 4.25


def test_llm_client_fallback_chain_and_retry():
    """Verify exponential backoff, status event callback, and switching to fallback model."""
    async def _run():
        client = ResilientLLMClient()
        # Configure mock candidates
        mock_c1_client = MagicMock()
        mock_c1_client.chat.completions.create.side_effect = Exception("429 Rate limit exceeded. Try again in 0.1s")

        mock_c2_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"thought": "test", "action": "click", "target": "uxg-1"}'))]
        mock_c2_client.chat.completions.create.return_value = mock_response

        c1 = ProviderCandidate(name="Primary", client=mock_c1_client, model="primary-model", is_fallback=False)
        c2 = ProviderCandidate(name="Fallback", client=mock_c2_client, model="fallback-model", is_fallback=True)

        client.get_candidates = MagicMock(return_value=[c1, c2])

        status_events = []
        async def on_status(msg: str):
            status_events.append(msg)

        # Call with max_retries_per_candidate=2
        res = await client.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model_type="vision",
            max_retries_per_candidate=2,
            status_callback=on_status,
            timeout=5.0,
        )
        assert res == mock_response
        # Verify status events streamed over callback
        assert any("Rate limit on primary-model" in ev for ev in status_events)
        assert any("Switched to fallback model: fallback-model" in ev for ev in status_events)

    asyncio.run(_run())


def test_llm_client_all_fallbacks_fail_raises_unavailable():
    """Verify that LLMUnavailableError is raised when all candidates exhaust retries."""
    async def _run():
        client = ResilientLLMClient()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 Rate limit exceeded")
        c1 = ProviderCandidate(name="Primary", client=mock_client, model="primary-model", is_fallback=False)
        client.get_candidates = MagicMock(return_value=[c1])

        with pytest.raises(LLMUnavailableError) as exc_info:
            await client.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_retries_per_candidate=1,
                timeout=2.0,
            )
        assert "All LLM retries and fallback providers failed" in str(exc_info.value)

    asyncio.run(_run())


def test_agent_aborted_llm_unavailable_saves_partial_report():
    """
    Verify that if all LLM retries fail in run_agent_loop, the session ends with
    status 'aborted_llm_unavailable' and still saves the partial report.
    """
    async def _run():
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/checkout"
        mock_page.screenshot.return_value = b"fake_screenshot_bytes"
        mock_page.evaluate.return_value = []

        queue = asyncio.Queue()
        session_data = {
            "session_id": "sess-rate-limit",
            "url": "https://example.com/checkout",
            "task": "checkout item",
            "persona": "pro_tester",
            "steps": [],
            "report": None,
            "status": "running",
        }

        with patch("agent.resilient_llm_client.chat_completion", side_effect=LLMUnavailableError("Quota exhausted")):
            await run_agent_loop(
                page=mock_page,
                task="checkout item",
                persona="pro_tester",
                queue=queue,
                max_steps=5,
                session_id="sess-rate-limit",
                session_data=session_data,
            )

        assert session_data["status"] == "aborted_llm_unavailable"
        report = session_data["report"]
        assert report is not None
        assert report["status"] == "aborted_llm_unavailable"
        assert report["score"] is not None
        assert report["task"] == "checkout item"
        assert "aborted" in report["verdict"].lower()

        # Verify done message signaled with status aborted_llm_unavailable
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        done_event = next(ev for ev in events if ev.get("done"))
        assert done_event.get("status") == "aborted_llm_unavailable"

    asyncio.run(_run())
