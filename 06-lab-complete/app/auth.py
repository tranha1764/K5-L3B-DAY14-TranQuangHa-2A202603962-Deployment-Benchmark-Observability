"""
API Key authentication (tiêu chí 6).
"""
import hmac
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from app.config import settings

# auto_error=False để tự kiểm soát và trả HTTP 401 (thay vì 403 mặc định của APIKeyHeader)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Dependency kiểm tra header X-API-Key khớp với AGENT_API_KEY."""
    expected = settings.agent_api_key
    if not expected or not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
