"""Security middleware and utilities.

Implements API key authentication and request validation.
In production, this integrates with AWS API Gateway's built-in
authentication and WAF for additional protection.
"""

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from backend.app.core.config import Settings, get_settings

# API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate the API key from request headers.

    In production, API Gateway handles primary authentication.
    This provides defense-in-depth at the application layer.

    Args:
        api_key: API key extracted from X-API-Key header.
        settings: Application settings.

    Returns:
        The validated API key.

    Raises:
        HTTPException: If API key is missing or invalid.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
        )
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return api_key
