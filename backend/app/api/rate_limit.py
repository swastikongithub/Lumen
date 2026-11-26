"""Rate limits for POST /chat (SPEC §9 step 1, §13), with slowapi.

Two limits, both counted in memory (per instance; at most 2 instances, a trade-off the
SPEC accepts to avoid running Redis):
- per session (`X-Session-Id`), 10/minute and 100/day by default;
- per IP address, higher, because students on campus Wi-Fi share a few public addresses.
  It stops one script from dodging the session limit by inventing new session IDs.

IP addresses are never stored. The key is an HMAC-SHA256 of the address with a random
salt that exists only in this process's memory and changes at every restart, so even
trying all 4 billion IPv4 addresses cannot reverse a key. IPv6 addresses count per /64
network, since one device can pick any address in its /64.

A request over a limit gets 429 with `Retry-After` (seconds) and a JSON body:
    {"detail": "...", "code": "too_many_requests", "retry_after": 42}
The routes check the session header before the limit, so a bad request never counts.
"""

import hashlib
import hmac
import ipaddress
import math
import secrets
import time
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.config import Settings

# Random per process and never written anywhere (see the module docstring).
_SALT = secrets.token_bytes(32)


class _Limits:
    """The limit strings of the running app. slowapi reads them on every request."""

    session = "10/minute;100/day"
    ip = "60/minute;1000/day"


def client_address(request: Request, trusted_proxy_hops: int) -> str:
    """The caller's IP. Behind `n` trusted proxies that each append the address they saw
    to X-Forwarded-For, it is the n-th entry from the right; entries further left were
    written by the client and could be anything."""
    if trusted_proxy_hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(hops) >= trusted_proxy_hops:
            return hops[-trusted_proxy_hops]
    return request.client.host if request.client else "unknown"


def network_of(address: str) -> str:
    """The address itself for IPv4; the /64 network for IPv6."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:  # ::ffff:203.0.113.7 is the IPv4 address 203.0.113.7
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def hash_address(address: str, salt: bytes = _SALT) -> str:
    return hmac.new(salt, network_of(address).encode(), hashlib.sha256).hexdigest()[:32]


def ip_key(request: Request) -> str:
    settings: Settings = request.app.state.settings
    return "ip:" + hash_address(client_address(request, settings.trusted_proxy_hops))


def session_key(request: Request) -> str:
    """The session ID, already validated by the route's session dependency."""
    raw = request.headers.get("x-session-id", "")
    try:
        return "session:" + str(uuid.UUID(raw.strip()))
    except ValueError:
        return "session:invalid"


limiter = Limiter(key_func=ip_key, storage_uri="memory://", strategy="moving-window")

# Decorators for the chat route. The strings are read per request, from configure().
# slowapi files limits under the route function's name, so decorate each route only once.
# It checks them in the order they were applied, innermost first. Put `limit_per_session`
# innermost: a request its session limit refuses then doesn't use up the IP's shared quota.
limit_per_session = limiter.limit(lambda: _Limits.session, key_func=session_key)
limit_per_ip = limiter.limit(lambda: _Limits.ip, key_func=ip_key)


def configure(settings: Settings) -> None:
    """Use this app's limits and start with empty counters."""
    _Limits.session = settings.rate_limit_session
    _Limits.ip = settings.rate_limit_ip
    limiter.reset()


def retry_after_seconds(request: Request) -> int:
    """Seconds until the limit that was hit lets one more request through."""
    hit = getattr(request.state, "view_rate_limit", None)
    if not hit:
        return 60
    limit, keys = hit
    reset_at = limiter.limiter.get_window_stats(limit, *keys).reset_time
    return max(1, math.ceil(reset_at - time.time()))


def rate_limited(request: Request, exc: Exception) -> JSONResponse:
    """The 429 response for RateLimitExceeded."""
    assert isinstance(exc, RateLimitExceeded)
    seconds = retry_after_seconds(request)
    return JSONResponse(
        {
            "detail": "Too many questions from this device or network. Try again later.",
            "code": "too_many_requests",
            "retry_after": seconds,
        },
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(seconds)},
    )
