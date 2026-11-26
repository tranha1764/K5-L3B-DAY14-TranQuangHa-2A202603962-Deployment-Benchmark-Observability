"""
Rate limiting (tiêu chí 7) — Sliding window lưu trên Redis Sorted Set.
"""
import time
import uuid
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Giới hạn tối đa RATE_LIMIT_PER_MINUTE request / 60 giây cho mỗi API key."""
    if r is None:
        return

    now = time.time()
    redis_key = f"rate_limit:{key}"

    try:
        # 1. Xóa các request đã quá cửa sổ 60 giây
        r.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        # 2. Đếm số request hiện tại trong cửa sổ
        current = r.zcard(redis_key)
        if current >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        # 3. Ghi nhận request mới (thêm uuid tránh trùng member nếu 2 request cùng timestamp)
        member = f"{now}:{uuid.uuid4().hex}"
        r.zadd(redis_key, {member: now})
        r.expire(redis_key, WINDOW_SECONDS)
    except HTTPException:
        raise
    except Exception:
        # Không làm sập endpoint nếu Redis tạm thời mất kết nối
        return
