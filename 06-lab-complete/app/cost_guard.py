"""
Cost guard (tiêu chí 8) — Theo dõi và giới hạn chi phí LLM trên Redis.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:daily:{day}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        return
    try:
        spent = float(r.get(_budget_key()) or 0.0)
        if spent >= settings.daily_budget_usd:
            raise HTTPException(
                status_code=402,
                detail=f"Daily budget exceeded (${spent:.6f} / ${settings.daily_budget_usd:.6f})",
            )
    except HTTPException:
        raise
    except Exception:
        return


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào Redis và trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K

    if r is not None:
        try:
            key = _budget_key()
            r.incrbyfloat(key, cost)
            r.expire(key, 2 * 24 * 3600)  # giữ key tối đa 48 giờ
        except Exception:
            pass
    return cost
