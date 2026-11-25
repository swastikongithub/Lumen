"""Dependencies shared by the API routes.

Sessions (SPEC §10): the client creates a random UUID on first launch and sends it as
`X-Session-Id` on every request, plus `X-Client` (web | android) and `X-App-Version`.
No cookies: the web app, the API and the Android WebView are different sites.
The ID is only checked for UUID syntax. It identifies a device, it does not authenticate.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, NoReturn

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings
from app.enums import Client

MAX_APP_VERSION_LENGTH = 32


@dataclass(frozen=True)
class ClientSession:
    session_id: str  # canonical lowercase UUID string
    client: Client
    app_version: str | None


def parse_session_headers(
    session_id: str | None, client: str | None, app_version: str | None
) -> ClientSession:
    """Validate the session headers. Raises 400 with a clear message on bad input."""
    if not session_id:
        raise _bad_request("X-Session-Id header is required")
    try:
        canonical_id = str(uuid.UUID(session_id.strip()))
    except ValueError:
        raise _bad_request("X-Session-Id must be a UUID") from None

    if client is None or not client.strip():
        parsed_client = Client.WEB
    else:
        try:
            parsed_client = Client(client.strip().lower())
        except ValueError:
            allowed = ", ".join(c.value for c in Client)
            raise _bad_request(f"X-Client must be one of: {allowed}") from None

    version = app_version.strip() if app_version else None
    if version and len(version) > MAX_APP_VERSION_LENGTH:
        raise _bad_request(f"X-App-Version must be at most {MAX_APP_VERSION_LENGTH} characters")

    return ClientSession(session_id=canonical_id, client=parsed_client, app_version=version or None)


def require_session(
    x_session_id: Annotated[str | None, Header()] = None,
    x_client: Annotated[str | None, Header()] = None,
    x_app_version: Annotated[str | None, Header()] = None,
) -> ClientSession:
    """FastAPI dependency for routes that read or write a session's data."""
    return parse_session_headers(x_session_id, x_client, x_app_version)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


CurrentSession = Annotated[ClientSession, Depends(require_session)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def not_implemented(phase: int) -> NoReturn:
    """Placeholder body for routes whose contract exists but whose logic comes later."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Not implemented yet (SPEC §14, Phase {phase})",
    )


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
