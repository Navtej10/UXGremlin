import os
import ipaddress
import socket
import urllib.parse
import time
import re
import asyncio
import inspect
from typing import Any

# ==============================================================================
# 1. URL & IP Validation Constants and Functions
# ==============================================================================

# Allow localhost / loopback testing by default (can be disabled via ALLOW_LOCALHOST=false)
ALLOW_LOCALHOST = os.getenv("ALLOW_LOCALHOST", "true").lower() in ("true", "1", "yes")
ALLOW_PRIVATE_IPS = os.getenv("ALLOW_PRIVATE_IPS", "false").lower() in ("true", "1", "yes")

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),         # Private class A (10.x)
    ipaddress.ip_network("100.64.0.0/10"),      # Shared address space / CGNAT
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback (127.x)
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local & cloud metadata (169.254.x)
    ipaddress.ip_network("172.16.0.0/12"),      # Private class B (172.16.x - 172.31.x)
    ipaddress.ip_network("192.168.0.0/16"),     # Private class C (192.168.x)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved for future use
    # IPv6 ranges
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),            # Loopback (::1)
    ipaddress.ip_network("fc00::/7"),           # Unique Local Addresses (fc00::/7)
    ipaddress.ip_network("fe80::/10"),          # Link-local (fe80::/10)
    ipaddress.ip_network("ff00::/8"),           # Multicast
]

# Sensitive cloud metadata endpoints that must NEVER be accessed
FORBIDDEN_HOSTNAMES = {
    "metadata.google.internal",
    "metadata",
    "instance-data",
}

LOOPBACK_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}

CLOUD_METADATA_IPS = {
    "169.254.169.254",   # AWS, GCP, Azure metadata
    "100.100.100.200",   # Alibaba cloud metadata
}


def is_loopback_host(hostname: str) -> bool:
    """Checks whether the hostname is a loopback / localhost address."""
    clean = hostname.strip().strip("[]").lower()
    if clean in LOOPBACK_HOSTNAMES or clean.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(clean)
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        return False


def normalize_target_url(url: str) -> str:
    """
    Ensures user-entered URL has a valid scheme.
    If scheme is missing, defaults to http:// for localhost/loopback, or https:// otherwise.
    """
    if not url or not isinstance(url, str):
        return ""
    cleaned = url.strip()
    if not cleaned:
        return ""

    lower = cleaned.lower()
    if lower.startswith(("http://", "https://")):
        return cleaned

    # Preserve known non-http schemes so they get rejected by scheme validation
    if re.match(r"^(ftp|file|javascript|data|ws|wss|mailto|ssh|tel|about):", lower):
        return cleaned

    # Loopback / localhost patterns
    if lower.startswith(("localhost", "127.0.0.1", "0.0.0.0", "[::1]")) or ".localhost" in lower:
        return f"http://{cleaned}"

    # Standard domain names (e.g. example.com, demo.mycorp.org/page)
    if re.match(r"^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+", cleaned):
        return f"https://{cleaned}"

    return cleaned


def is_valid_scheme(url: str) -> bool:
    """Checks if the URL scheme is strictly http or https."""
    try:
        normalized = normalize_target_url(url)
        parsed = urllib.parse.urlsplit(normalized)
        return parsed.scheme.lower() in ("http", "https")
    except Exception:
        return False


def is_blocked_ip(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    allow_localhost: bool | None = None,
    allow_private_ips: bool | None = None,
) -> tuple[bool, str]:
    """
    Checks if an IP address belongs to private, loopback, link-local,
    cloud-metadata, or reserved ranges.
    Returns (is_blocked: bool, reason: str).
    """
    if allow_localhost is None:
        allow_localhost = ALLOW_LOCALHOST
    if allow_private_ips is None:
        allow_private_ips = ALLOW_PRIVATE_IPS

    ip_str = str(ip_obj)

    # Cloud metadata is forbidden in all environments
    if ip_str in CLOUD_METADATA_IPS:
        return True, f"Cloud metadata IP address '{ip_str}' is forbidden."

    # Loopback / local host check
    if ip_obj.is_loopback or ip_str == "0.0.0.0":
        if allow_localhost:
            return False, ""
        return True, f"Loopback IP address '{ip_str}' is forbidden."

    # Private IP check
    if ip_obj.is_private:
        if allow_private_ips:
            return False, ""
        return True, f"Private IP address '{ip_str}' is forbidden."

    if ip_obj.is_link_local:
        return True, f"Link-local IP address '{ip_str}' is forbidden."

    if ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified:
        return True, f"Reserved, multicast, or unspecified IP address '{ip_str}' is forbidden."

    for net in BLOCKED_IP_NETWORKS:
        if allow_localhost and net in (
            ipaddress.ip_network("127.0.0.0/8"),
            ipaddress.ip_network("::1/128"),
            ipaddress.ip_network("0.0.0.0/8"),
        ):
            continue
        if allow_private_ips and net in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("fc00::/7"),
        ):
            continue
        if ip_obj in net:
            return True, f"IP address '{ip_str}' falls into blocked range {net}."

    return False, ""


def resolve_hostname_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """
    Resolves hostname to a list of IP address objects (both IPv4 and IPv6).
    If hostname is already an IP, returns it directly.
    """
    clean_host = hostname.strip().strip("[]").lower()

    # Direct IP string
    try:
        return [ipaddress.ip_address(clean_host)]
    except ValueError:
        pass

    # RFC 6761 special localhost resolution fallback
    if clean_host == "localhost" or clean_host.endswith(".localhost"):
        try:
            addrinfo = socket.getaddrinfo(clean_host, None)
            ips = []
            for entry in addrinfo:
                ip_str = entry[4][0]
                try:
                    ips.append(ipaddress.ip_address(ip_str))
                except ValueError:
                    continue
            if ips:
                return ips
        except Exception:
            pass
        return [ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")]

    try:
        addrinfo = socket.getaddrinfo(clean_host, None)
        ips = []
        for entry in addrinfo:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            try:
                ips.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue
        return ips
    except Exception as e:
        raise ValueError(f"DNS resolution failed for '{clean_host}': {e}") from e


def validate_target_url(
    url: str,
    allow_localhost: bool | None = None,
    allow_private_ips: bool | None = None,
) -> tuple[bool, str]:
    """
    Validates target URL:
    1. Scheme must be http or https
    2. Hostname must be present and not in forbidden hostnames (e.g. cloud metadata)
    3. Resolves DNS and rejects private, loopback (unless allow_localhost=True),
       link-local, and cloud-metadata IP ranges.
    Returns (is_valid: bool, error_reason: str).
    """
    if allow_localhost is None:
        allow_localhost = ALLOW_LOCALHOST
    if allow_private_ips is None:
        allow_private_ips = ALLOW_PRIVATE_IPS

    if not url or not isinstance(url, str) or not url.strip():
        return False, "Target URL cannot be empty."

    raw_url = normalize_target_url(url)
    try:
        parsed = urllib.parse.urlsplit(raw_url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, f"Invalid scheme '{scheme}'. Only http and https protocols are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL does not contain a valid hostname."

    clean_host = hostname.strip().strip("[]").lower()

    if clean_host in FORBIDDEN_HOSTNAMES:
        return False, f"Forbidden hostname '{clean_host}'."

    is_local = is_loopback_host(clean_host)
    if is_local:
        if not allow_localhost:
            return False, f"Forbidden hostname '{clean_host}' (loopback addresses are disabled)."
        # Prevent self-recursion against UXGremlin's internal API endpoints
        backend_port = int(os.getenv("PORT", "8000"))
        if (parsed.port or 80) == backend_port and parsed.path.startswith(("/api", "/docs", "/openapi.json")):
            return False, f"Target URL cannot target UXGremlin's internal API endpoints (port {backend_port})."

    try:
        resolved_ips = resolve_hostname_ips(clean_host)
    except ValueError as e:
        return False, str(e)

    if not resolved_ips:
        return False, f"Could not resolve any IP addresses for hostname '{clean_host}'."

    for ip_obj in resolved_ips:
        blocked, reason = is_blocked_ip(
            ip_obj,
            allow_localhost=allow_localhost,
            allow_private_ips=allow_private_ips,
        )
        if blocked:
            return False, reason

    return True, ""


# ==============================================================================
# 2. Playwright Route Interception (Redirects & Navigations)
# ==============================================================================

async def setup_route_interception(page_or_context: Any, allow_localhost: bool | None = None) -> None:
    """
    Sets up route interception on the page or context to re-validate URLs
    on every navigation and redirect. Blocks forbidden requests with 'blockedbyclient'.
    """
    if allow_localhost is None:
        allow_localhost = ALLOW_LOCALHOST

    route_fn = getattr(page_or_context, "route", None)
    if not callable(route_fn):
        return

    async def _handle_route(route):
        try:
            req = route.request
            req_url = req.url

            # Validate requested URL
            is_safe, reason = validate_target_url(req_url, allow_localhost=allow_localhost)
            if not is_safe:
                print(f"[Security Guard] Blocked request/redirect to forbidden URL: {req_url} ({reason})")
                await route.abort("blockedbyclient")
                return

            # Check if this request is a redirect from another request
            redir_from = getattr(req, "redirected_from", None)
            if redir_from:
                redir_url = getattr(redir_from, "url", "")
                origin_host = (urllib.parse.urlsplit(redir_url).hostname or "").lower()
                dest_host = (urllib.parse.urlsplit(req_url).hostname or "").lower()
                # SSRF guard: if redirected from an external public site, forbid redirecting to internal/loopback
                if not is_loopback_host(origin_host) and is_loopback_host(dest_host):
                    print(f"[Security Guard] Blocked SSRF redirect from external site {redir_url} to internal URL {req_url}")
                    await route.abort("blockedbyclient")
                    return

                redir_safe, redir_reason = validate_target_url(req_url, allow_localhost=allow_localhost)
                if not redir_safe:
                    print(f"[Security Guard] Blocked redirect from {redir_url} to {req_url} ({redir_reason})")
                    await route.abort("blockedbyclient")
                    return

            await route.continue_()
        except Exception as e:
            # Defensive fallback: if route handling fails, attempt continue or ignore
            try:
                await route.continue_()
            except Exception:
                pass

    res = route_fn("**/*", _handle_route)
    if inspect.iscoroutine(res):
        await res


# ==============================================================================
# 3. Rate Limiter, Max Session Duration & Steps Cap
# ==============================================================================

MAX_STEPS_CAP = 25
MAX_SESSION_DURATION_SECONDS = 180.0
DEFAULT_RATE_LIMIT_MAX_REQUESTS = 10
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0


class RateLimiter:
    """In-memory sliding window rate limiter per client IP."""
    def __init__(self, max_requests: int = DEFAULT_RATE_LIMIT_MAX_REQUESTS, window_seconds: float = DEFAULT_RATE_LIMIT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._ip_history: dict[str, list[float]] = {}

    def check_rate_limit(self, client_ip: str) -> tuple[bool, int, float]:
        """
        Checks whether client_ip is within the rate limit.
        Returns (allowed: bool, remaining_requests: int, reset_in_seconds: float).
        """
        now = time.time()
        ip = (client_ip or "127.0.0.1").strip()

        history = self._ip_history.get(ip, [])
        cutoff = now - self.window_seconds
        # Retain only timestamps inside sliding window
        valid_history = [t for t in history if t > cutoff]

        if len(valid_history) >= self.max_requests:
            oldest = valid_history[0]
            reset_in = max(0.1, (oldest + self.window_seconds) - now)
            self._ip_history[ip] = valid_history
            return False, 0, reset_in

        valid_history.append(now)
        self._ip_history[ip] = valid_history
        remaining = max(0, self.max_requests - len(valid_history))
        return True, remaining, self.window_seconds

    def reset(self):
        """Clears all stored rate limit history."""
        self._ip_history.clear()


session_rate_limiter = RateLimiter(
    max_requests=DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    window_seconds=DEFAULT_RATE_LIMIT_WINDOW_SECONDS
)


def apply_session_security_caps(
    max_steps: int | None = None,
    max_duration: float | None = None
) -> tuple[int, float]:
    """
    Applies security ceilings on session steps and session duration.
    Returns (capped_steps: int, capped_duration: float).
    """
    req_steps = max_steps if (max_steps is not None and max_steps > 0) else 15
    capped_steps = min(req_steps, MAX_STEPS_CAP)

    req_duration = max_duration if (max_duration is not None and max_duration > 0) else MAX_SESSION_DURATION_SECONDS
    capped_duration = min(req_duration, MAX_SESSION_DURATION_SECONDS)

    return capped_steps, capped_duration


# ==============================================================================
# 4. Downloads, File Choosers & Payment Field Guards
# ==============================================================================

async def setup_download_and_file_guards(page: Any) -> None:
    """
    Registers page listeners to block downloads and cancel/ignore file chooser dialogs.
    """
    try:
        on_fn = getattr(page, "on", None)
        if callable(on_fn):
            def _on_download(download):
                try:
                    cancel_fn = getattr(download, "cancel", None)
                    if callable(cancel_fn):
                        res = cancel_fn()
                        if inspect.iscoroutine(res):
                            asyncio.create_task(res)
                except Exception as e:
                    print(f"[Security Guard] Error canceling download: {e}")

            r1 = on_fn("download", _on_download)
            if inspect.iscoroutine(r1):
                await r1

            def _on_file_chooser(file_chooser):
                # Ignore file chooser to prevent uploading local files
                pass

            r2 = on_fn("filechooser", _on_file_chooser)
            if inspect.iscoroutine(r2):
                await r2
    except Exception as e:
        print(f"[Security Guard] Error attaching download/file chooser guards: {e}")


def is_payment_field(
    label: str = "",
    name: str = "",
    field_type: str = "",
    autocomplete: str = "",
    placeholder: str = "",
    target_id: str = "",
) -> bool:
    """
    Detects whether an input field represents a credit card number or payment detail.
    """
    combined = f"{label} {name} {placeholder} {autocomplete} {target_id}".lower()

    if autocomplete and "cc-number" in autocomplete.lower():
        return True

    patterns = [
        r"\bcredit[\s_\-]*card\b",
        r"\bcard[\s_\-]*number\b",
        r"\bcc[\s_\-]*num\b",
        r"\bcc[\s_\-]*number\b",
        r"\bcc_num\b",
        r"\bpan\b",
        r"\bcard[\s_\-]*no\b",
        r"\bcardnumber\b",
        r"\bcreditcard\b",
    ]
    return any(re.search(p, combined) for p in patterns)


def detect_payment_fields(elements: list[dict] | None = None) -> tuple[bool, str]:
    """
    Inspects visible interactive elements for credit card number fields.
    Returns (has_payment_fields: bool, description: str).
    """
    if not elements:
        return False, ""

    for el in elements:
        name = str(el.get("name", ""))
        text = str(el.get("text", ""))
        placeholder = str(el.get("placeholder", ""))
        f_type = str(el.get("type", ""))
        auto = str(el.get("autocomplete", ""))
        tag = str(el.get("tag", ""))
        el_id = str(el.get("id", ""))

        if tag in ("input", "textarea") or f_type in ("text", "tel", "number", "password"):
            if is_payment_field(
                label=text,
                name=name,
                field_type=f_type,
                autocomplete=auto,
                placeholder=placeholder,
                target_id=el_id,
            ):
                return True, f"Card number input field detected: '{text or name or placeholder or el_id}'"

    return False, ""


def is_payment_submission_action(
    action: str,
    target_label: str = "",
    target_el: dict | None = None
) -> bool:
    """
    Checks if an action attempts to submit a payment or checkout form.
    """
    if action not in ("click", "submit"):
        return False

    combined = f"{target_label} {target_el.get('text', '') if target_el else ''} {target_el.get('name', '') if target_el else ''}".lower()
    submission_keywords = [
        "pay",
        "checkout",
        "place order",
        "complete order",
        "purchase",
        "buy now",
        "submit payment",
        "confirm payment",
    ]
    return any(re.search(rf"\b{re.escape(k)}\b", combined) for k in submission_keywords)


# ==============================================================================
# 5. Fake Form Data Enforcement
# ==============================================================================

def sanitize_fake_form_data(value: str, label: str = "", field_type: str = "") -> tuple[str, bool]:
    """
    Ensures typed values use only clearly fake form data (e.g. test@example.com)
    to protect real user privacy.
    Returns (sanitized_value: str, was_modified: bool).
    """
    combined = f"{label} {field_type}".lower()

    # Email
    if "email" in combined or re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", value):
        return "test@example.com", (value != "test@example.com")

    # Phone
    if any(k in combined for k in ["phone", "tel", "mobile"]) or re.search(r"^\+?[\d\s\-()]{7,}$", value.strip()):
        return "555-0100", (value != "555-0100")

    # Full name / User name
    if any(k in combined for k in ["full name", "fullname", "first name", "firstname", "last name", "lastname", "name"]):
        return "Test User", (value != "Test User")

    # Street address
    if "address" in combined or "street" in combined:
        return "123 Test Street", (value != "123 Test Street")

    # Zip / Postal
    if any(k in combined for k in ["zip", "postal"]):
        return "00000", (value != "00000")

    # Default fallback for passwords or personal fields
    if "password" in combined:
        return "TestPassword123!", (value != "TestPassword123!")

    return value, False
