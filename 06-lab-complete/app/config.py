"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field


def _get_budget_usd() -> float:
    """Ưu tiên DAILY_BUDGET_USD; fallback sang MONTHLY_BUDGET_USD nếu có."""
    raw = os.getenv("DAILY_BUDGET_USD") or os.getenv("MONTHLY_BUDGET_USD") or "1.0"
    return float(raw)


@dataclass
class Settings:
    # Cổng lắng nghe do platform (Railway/Render) cấp động qua biến PORT
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    # Secret API key — tuyệt đối không hardcode giá trị thật trong code
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    # URL kết nối Redis cho rate limiter và cost guard
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    # Ngưỡng rate limit mỗi phút cho từng API key
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    # Ngân sách tối đa (USD) trước khi trả HTTP 402
    daily_budget_usd: float = field(default_factory=_get_budget_usd)


settings = Settings()
