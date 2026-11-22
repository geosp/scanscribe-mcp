"""Static bearer-token check for the MCP endpoint (D8), as in pandoc-mcp."""

from __future__ import annotations

import hmac

from fastmcp.server.auth import AccessToken, TokenVerifier
from pydantic import SecretStr


def token_matches(expected: SecretStr, given: str) -> bool:
    """Compare in constant time, so the answer's timing doesn't reveal the token."""
    return hmac.compare_digest(given.encode(), expected.get_secret_value().encode())


class BearerTokenVerifier(TokenVerifier):
    """Accepts exactly one static bearer token."""

    def __init__(self, token: SecretStr) -> None:
        super().__init__()
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if token_matches(self._token, token):
            return AccessToken(token=token, client_id="scanscribe-mcp-client", scopes=[])
        return None
