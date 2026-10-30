"""Interactive OAuth authorization-code login for Saxo SIM."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from hedge_fund.brokers.saxo import (
    _refresh_lock,
    AUTH_URL,
    RequestsTransport,
    SaxoAuthError,
)
from hedge_fund.secrets.provider import SecretProvider


def interactive_login(
    app_key: str,
    app_secret: str,
    redirect_uri: str,
    refresh_token_ref: str,
    secrets_provider: SecretProvider,
    *,
    browser_open=webbrowser.open,
    prompt=input,
    transport=None,
    verifier: str | None = None,
    state: str | None = None,
    lock_dir: str | Path | None = None,
) -> None:
    if not isinstance(app_key, str) or not app_key or not isinstance(app_secret, str) or not app_secret or not isinstance(refresh_token_ref, str) or not refresh_token_ref.startswith("op://"):
        raise ValueError("Saxo SIM app credentials and an op:// refresh-token reference are required")
    if not isinstance(redirect_uri, str):
        raise ValueError("SAXO_REDIRECT_URI must be an absolute registered URI")
    parsed_uri = urlparse(redirect_uri)
    if parsed_uri.scheme not in ("http", "https") or not parsed_uri.netloc:
        raise ValueError("SAXO_REDIRECT_URI must be an absolute registered URI")
    verifier = verifier or secrets.token_urlsafe(64)
    state = state or secrets.token_urlsafe(24)
    if not isinstance(verifier, str) or not 43 <= len(verifier) <= 128 or not isinstance(state, str) or not state:
        raise ValueError("Saxo PKCE verifier or state is invalid")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    query_string = urlencode(
        {
            "client_id": app_key,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    authorization_url = f"{AUTH_URL}/authorize?{query_string}"
    browser_open(authorization_url)
    callback = prompt("Paste the redirected callback URL: ")
    if not isinstance(callback, str):
        raise ValueError("Saxo authorization callback is invalid")
    callback = callback.strip()
    callback_uri = urlparse(callback)
    query = parse_qs(callback_uri.query)
    if not callback or (callback_uri.scheme, callback_uri.netloc, callback_uri.path) != (parsed_uri.scheme, parsed_uri.netloc, parsed_uri.path) or query.get("state", [None])[0] != state:
        raise ValueError("Saxo authorization callback state did not match")
    code = query.get("code", [None])[0]
    if not code or query.get("error"):
        raise ValueError("Saxo authorization was not completed")
    client = transport or RequestsTransport()
    try:
        with _refresh_lock(refresh_token_ref, lock_dir):
            response = client.request(
                "POST",
                f"{AUTH_URL}/token",
                auth=(app_key, app_secret),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            status = int(getattr(response, "status_code", response[0] if isinstance(response, tuple) else 0))
            body = response[1] if isinstance(response, tuple) else response.json()
            token = body.get("refresh_token") if isinstance(body, dict) else None
            if status < 200 or status >= 300 or not isinstance(token, str) or not token:
                raise ValueError("Saxo authorization exchange failed")
            secrets_provider.write_back("SAXO_REFRESH_TOKEN_REF", refresh_token_ref, token)
    except SaxoAuthError:
        raise
    except Exception:
        raise ValueError("Saxo authorization failed; retry interactive login") from None


def main() -> None:
    env = os.environ
    names = ("SAXO_APP_KEY_REF", "SAXO_APP_SECRET_REF", "SAXO_REFRESH_TOKEN_REF")
    refs = {name: env.get(name, "") for name in names}
    for name in names:
        if not refs[name]:
            raise ValueError(f"{name}: required for Saxo interactive login")
    redirect_uri = env.get("SAXO_REDIRECT_URI", "")
    if not redirect_uri:
        raise ValueError("SAXO_REDIRECT_URI: required for Saxo interactive login")
    provider = SecretProvider()
    credentials = {name: provider.resolve(name, refs[name]) for name in names[:2]}
    interactive_login(
        credentials["SAXO_APP_KEY_REF"],
        credentials["SAXO_APP_SECRET_REF"],
        redirect_uri,
        refs["SAXO_REFRESH_TOKEN_REF"],
        provider,
    )


if __name__ == "__main__":
    main()
