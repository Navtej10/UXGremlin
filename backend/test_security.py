import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from main import app
from security import (
    validate_target_url,
    is_valid_scheme,
    is_blocked_ip,
    setup_route_interception,
    setup_download_and_file_guards,
    RateLimiter,
    session_rate_limiter,
    apply_session_security_caps,
    detect_payment_fields,
    is_payment_field,
    is_payment_submission_action,
    sanitize_fake_form_data,
    MAX_STEPS_CAP,
    MAX_SESSION_DURATION_SECONDS,
)
from agent import perform_action
import ipaddress


@pytest.fixture
def client():
    # Reset global rate limiter before tests
    session_rate_limiter.reset()
    return TestClient(app)


# ==============================================================================
# 1. URL Validator & IP Range Tests
# ==============================================================================

def test_validate_url_valid_schemes():
    valid_urls = [
        "https://example.com",
        "http://example.com/catalog",
        "https://example.com:8443/login",
        "https://example.org/search?q=test",
    ]
    for url in valid_urls:
        ok, reason = validate_target_url(url)
        assert ok is True, f"Expected {url} to be valid, but got: {reason}"


def test_validate_url_invalid_schemes():
    invalid_urls = [
        "ftp://example.com/file.txt",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>Hello</h1>",
        "ws://example.com/socket",
        "",
        "not_a_url",
    ]
    for url in invalid_urls:
        ok, reason = validate_target_url(url)
        assert ok is False
        assert "scheme" in reason.lower() or "malformed" in reason.lower() or "cannot be empty" in reason.lower() or "hostname" in reason.lower()


def test_validate_url_private_ip_ranges():
    # 10.x, 172.16-31.x, 192.168.x
    private_urls = [
        "http://10.0.0.1/",
        "http://10.255.255.254/admin",
        "http://172.16.0.1:8080/",
        "http://172.24.1.1/",
        "http://172.31.255.255/",
        "http://192.168.0.1/",
        "http://192.168.1.100/router",
    ]
    for url in private_urls:
        ok, reason = validate_target_url(url)
        assert ok is False, f"Expected private IP {url} to be blocked"
        assert "forbidden" in reason.lower() or "blocked" in reason.lower() or "private" in reason.lower()


def test_validate_url_loopback_ranges_blocked_when_disabled():
    # When allow_localhost is False, loopback URLs are blocked
    loopback_urls = [
        "http://127.0.0.1/",
        "http://127.0.0.1:8000/api",
        "http://127.0.0.2:3000/",
        "http://localhost/",
        "http://localhost:8000/",
        "http://sub.localhost/",
    ]
    for url in loopback_urls:
        ok, reason = validate_target_url(url, allow_localhost=False)
        assert ok is False, f"Expected loopback {url} to be blocked when disabled"
        assert "forbidden" in reason.lower() or "loopback" in reason.lower()


def test_validate_url_allows_localhost_when_enabled():
    # When allow_localhost is True (default for local UX testing), local dev URLs are accepted
    allowed_local_urls = [
        "http://localhost:8080/index.html",
        "http://127.0.0.1:8080/fixed/index.html",
        "http://localhost:3000/products",
        "http://127.0.0.1:5173/",
        "http://[::1]:8080/",
        "localhost:8080/demo",
    ]
    for url in allowed_local_urls:
        ok, reason = validate_target_url(url, allow_localhost=True)
        assert ok is True, f"Expected local dev URL {url} to be allowed, but got: {reason}"


def test_validate_url_rejects_self_api_recursion():
    # UXGremlin must not test its own backend API endpoints
    ok, reason = validate_target_url("http://localhost:8000/api/launch", allow_localhost=True)
    assert ok is False
    assert "internal api" in reason.lower()


def test_validate_url_link_local_and_cloud_metadata():
    # 169.254.x, 169.254.169.254, metadata.google.internal
    cloud_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.1.1/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://100.100.100.200/latest/meta-data/",
    ]
    for url in cloud_urls:
        ok, reason = validate_target_url(url)
        assert ok is False, f"Expected cloud metadata {url} to be blocked"
        assert "forbidden" in reason.lower() or "cloud metadata" in reason.lower() or "link-local" in reason.lower()


def test_validate_url_ipv6_forbidden_ranges():
    # ::1 loopback IPv6 is blocked when allow_localhost is disabled
    for loopback in ["http://[::1]/", "http://[::1]:8080/admin"]:
        ok, reason = validate_target_url(loopback, allow_localhost=False)
        assert ok is False
        assert "forbidden" in reason.lower() or "loopback" in reason.lower()

    # fc00::/7 (ULA) and fe80::/10 (link-local) are blocked in all modes
    ipv6_urls = [
        "http://[fc00::1]/",
        "http://[fd12:3456:789a:1::1]/",
        "http://[fe80::1]/",
    ]
    for url in ipv6_urls:
        ok, reason = validate_target_url(url)
        assert ok is False, f"Expected IPv6 {url} to be blocked"
        assert "forbidden" in reason.lower() or "loopback" in reason.lower() or "private" in reason.lower() or "link-local" in reason.lower()


# ==============================================================================
# 2. Route Interception & Redirect to 127.0.0.1
# ==============================================================================

@pytest.mark.anyio
async def test_route_interception_blocks_redirect_to_127_0_0_1():
    """
    Simulates Playwright route interception on a request redirected to 127.0.0.1.
    Verifies that the route is intercepted and aborted with 'blockedbyclient'.
    """
    # Create mock page with route registration
    mock_page = MagicMock()
    captured_handler = None

    def capture_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    mock_page.route = capture_route
    await setup_route_interception(mock_page)
    assert captured_handler is not None, "setup_route_interception should register a route handler"

    # 1. Simulate redirect to 127.0.0.1
    mock_route = AsyncMock()
    mock_request = MagicMock()
    mock_request.url = "http://127.0.0.1:8000/admin"

    # Simulate redirect chain from public site
    mock_origin_request = MagicMock()
    mock_origin_request.url = "https://example.com/oauth/callback"
    mock_request.redirected_from = mock_origin_request
    mock_route.request = mock_request

    # Execute intercepted handler
    await captured_handler(mock_route)

    # Assert request to 127.0.0.1 was aborted with 'blockedbyclient'
    assert mock_route.abort.await_count == 1
    mock_route.abort.assert_awaited_with("blockedbyclient")
    assert mock_route.continue_.await_count == 0


@pytest.mark.anyio
async def test_route_interception_allows_safe_navigation():
    """Verifies that route interception allows requests to valid public URLs."""
    mock_page = MagicMock()
    captured_handler = None

    def capture_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    mock_page.route = capture_route
    await setup_route_interception(mock_page)

    mock_route = AsyncMock()
    mock_request = MagicMock()
    mock_request.url = "https://example.com/products"
    mock_request.redirected_from = None
    mock_route.request = mock_request

    await captured_handler(mock_route)

    assert mock_route.continue_.await_count == 1
    assert mock_route.abort.await_count == 0


# ==============================================================================
# 3. Rate Limiter, Max Session Duration & Steps Cap
# ==============================================================================

def test_rate_limiter_per_ip():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)
    client_ip = "203.0.113.195"

    # First 3 requests allowed
    ok1, rem1, _ = limiter.check_rate_limit(client_ip)
    assert ok1 is True and rem1 == 2

    ok2, rem2, _ = limiter.check_rate_limit(client_ip)
    assert ok2 is True and rem2 == 1

    ok3, rem3, _ = limiter.check_rate_limit(client_ip)
    assert ok3 is True and rem3 == 0

    # 4th request exceeds limit
    ok4, rem4, reset_in = limiter.check_rate_limit(client_ip)
    assert ok4 is False
    assert rem4 == 0
    assert reset_in > 0

    # Different IP is not blocked
    other_ip = "198.51.100.42"
    ok_other, _, _ = limiter.check_rate_limit(other_ip)
    assert ok_other is True

    # Reset clears limit
    limiter.reset()
    ok_after_reset, _, _ = limiter.check_rate_limit(client_ip)
    assert ok_after_reset is True


def test_session_security_caps():
    # Steps cap enforced (MAX_STEPS_CAP = 25)
    steps, dur = apply_session_security_caps(max_steps=100, max_duration=1000.0)
    assert steps == MAX_STEPS_CAP
    assert dur == MAX_SESSION_DURATION_SECONDS

    # Normal values under cap preserved
    steps_normal, dur_normal = apply_session_security_caps(max_steps=10, max_duration=60.0)
    assert steps_normal == 10
    assert dur_normal == 60.0


# ==============================================================================
# 4. Downloads, File Choosers & Payment Field Guards
# ==============================================================================

@pytest.mark.anyio
async def test_block_download_and_file_chooser_actions():
    page = AsyncMock()

    # Blocked action names
    success, msg = await perform_action(page, "download", "button#download")
    assert success is False
    assert "blocked" in msg.lower()

    success, msg = await perform_action(page, "file_chooser", "input#file")
    assert success is False
    assert "blocked" in msg.lower()

    # File input selector blocked
    success, msg = await perform_action(page, "click", "input[type='file']")
    assert success is False
    assert "blocked" in msg.lower()


def test_payment_field_detection():
    # Card number field detected
    elements = [
        {"id": "uxg-1", "tag": "input", "name": "card_number", "text": "Card Number", "type": "text"},
        {"id": "uxg-2", "tag": "input", "name": "cvv", "text": "CVV", "type": "text"},
        {"id": "uxg-3", "tag": "button", "name": "submit", "text": "Pay Now", "role": "button"},
    ]
    has_payment, desc = detect_payment_fields(elements)
    assert has_payment is True
    assert "card number" in desc.lower()

    # Autocomplete cc-number detected
    elements_auto = [
        {"id": "uxg-1", "tag": "input", "name": "pan", "autocomplete": "cc-number", "type": "text"},
    ]
    has_auto, _ = detect_payment_fields(elements_auto)
    assert has_auto is True

    # Standard non-payment fields not detected
    elements_clean = [
        {"id": "uxg-1", "tag": "input", "name": "username", "text": "Username", "type": "text"},
        {"id": "uxg-2", "tag": "input", "name": "email", "text": "Email Address", "type": "email"},
        {"id": "uxg-3", "tag": "button", "name": "submit", "text": "Sign In", "role": "button"},
    ]
    has_clean, _ = detect_payment_fields(elements_clean)
    assert has_clean is False


def test_payment_submission_action_detection():
    assert is_payment_submission_action("click", "Pay Now") is True
    assert is_payment_submission_action("click", "Place Order") is True
    assert is_payment_submission_action("click", "Complete Purchase") is True
    assert is_payment_submission_action("click", "Checkout") is True
    assert is_payment_submission_action("click", "View Product Details") is False
    assert is_payment_submission_action("scroll", "Pay Now") is False


# ==============================================================================
# 5. Fake Form Data Enforcement
# ==============================================================================

def test_fake_form_data_sanitization():
    # Real email replaced with test@example.com
    email_val, mod = sanitize_fake_form_data("real_ceo@company.com", label="Email", field_type="email")
    assert email_val == "test@example.com"
    assert mod is True

    # Real phone replaced with 555-0100
    phone_val, mod = sanitize_fake_form_data("+1-202-555-0199", label="Phone Number", field_type="tel")
    assert phone_val == "555-0100"
    assert mod is True

    # Real name replaced with Test User
    name_val, mod = sanitize_fake_form_data("Alice Wonderland", label="Full Name", field_type="text")
    assert name_val == "Test User"
    assert mod is True

    # Real address replaced with 123 Test Street
    addr_val, mod = sanitize_fake_form_data("742 Evergreen Terrace", label="Street Address", field_type="text")
    assert addr_val == "123 Test Street"
    assert mod is True


# ==============================================================================
# 6. API Endpoint Security Rejections
# ==============================================================================

def test_api_launch_rejects_forbidden_urls(client):
    from unittest.mock import patch
    with patch("main.threading.Thread"):
        # Loopback URL rejected when allow_localhost=False
        res_loopback = client.post("/api/launch", json={
            "url": "http://127.0.0.1:8080/admin",
            "task": "attack internal server",
            "persona": "pro_tester",
            "allow_localhost": False,
        })
        assert res_loopback.status_code == 400
        assert "forbidden" in res_loopback.json()["detail"].lower()

        # Cloud metadata URL rejected with HTTP 400
        res_metadata = client.post("/api/launch", json={
            "url": "http://169.254.169.254/latest/meta-data/",
            "task": "steal cloud keys",
            "persona": "skeptic",
        })
        assert res_metadata.status_code == 400
        assert "forbidden" in res_metadata.json()["detail"].lower()

        # Private IP URL rejected with HTTP 400
        res_private = client.post("/api/start-session", json={
            "url": "http://192.168.1.1/setup",
            "task": "hack router",
            "persona": "impatient",
        })
        assert res_private.status_code == 400
        assert "forbidden" in res_private.json()["detail"].lower()


def test_api_launch_accepts_localhost_by_default(client):
    from unittest.mock import patch
    with patch("main.threading.Thread"):
        res = client.post("/api/launch", json={
            "url": "http://localhost:8080/index.html",
            "task": "test coffee demo site",
            "persona": "pro_tester",
        })
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert data["url"] == "http://localhost:8080/index.html"


def test_api_launch_rate_limiting(client):
    from unittest.mock import patch
    with patch("main.threading.Thread"):
        # Temporarily restrict rate limiter to 2 requests
        orig_max = session_rate_limiter.max_requests
        session_rate_limiter.max_requests = 2
        try:
            res1 = client.post("/api/launch", json={"url": "https://example.com/page1", "task": "task 1", "persona": "pro_tester"})
            assert res1.status_code == 200

            res2 = client.post("/api/launch", json={"url": "https://example.com/page2", "task": "task 2", "persona": "pro_tester"})
            assert res2.status_code == 200

            # 3rd request from same client exceeds rate limit
            res3 = client.post("/api/launch", json={"url": "https://example.com/page3", "task": "task 3", "persona": "pro_tester"})
            assert res3.status_code == 429
            assert "rate limit exceeded" in res3.json()["detail"].lower()
        finally:
            session_rate_limiter.max_requests = orig_max
            session_rate_limiter.reset()
