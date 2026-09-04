"""针对临时 HTTP 状态码的异步重试工具。"""

import asyncio
import math
import os
import random
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

DEFAULT_STATUS_RETRY_COUNT = 2
DEFAULT_STATUS_RETRY_BASE_SECONDS = 20.0
DEFAULT_STATUS_RETRY_MAX_SECONDS = 60.0
DEFAULT_RETRYABLE_STATUS_CODES = (403, 429, 500, 502, 503, 504)


def _get_non_negative_float(name: str, default: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value):
        value = default
    return min(max(0.0, value), maximum)


def get_status_retry_count() -> int:
    """获取状态码重试次数（不含首次请求）。"""
    try:
        value = int(os.getenv("STATUS_RETRY_COUNT", str(DEFAULT_STATUS_RETRY_COUNT)))
    except (TypeError, ValueError):
        value = DEFAULT_STATUS_RETRY_COUNT
    return max(0, min(value, 5))


def get_status_retry_base_seconds() -> float:
    """获取状态码重试基础等待时间。"""
    return _get_non_negative_float(
        "STATUS_RETRY_BASE_SECONDS",
        DEFAULT_STATUS_RETRY_BASE_SECONDS,
        DEFAULT_STATUS_RETRY_MAX_SECONDS,
    )


def get_status_retry_max_seconds() -> float:
    """获取单次重试最大等待时间，始终不超过 60 秒。"""
    return _get_non_negative_float(
        "STATUS_RETRY_MAX_SECONDS",
        DEFAULT_STATUS_RETRY_MAX_SECONDS,
        60.0,
    )


async def retry_on_status(
    operation: Callable[[], Awaitable[Dict[str, Any]]],
    *,
    logger: Any,
    operation_name: str,
    retry_statuses: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    """执行异步操作，并对临时 HTTP 状态码进行指数退避重试。

    重试只针对明确的状态码，不会重试 401 等通常代表凭据失效的响应。
    每次等待包含少量随机抖动，避免多个账号在同一时刻再次请求。
    """
    statuses = set(
        DEFAULT_RETRYABLE_STATUS_CODES if retry_statuses is None else retry_statuses
    )
    max_retries = get_status_retry_count()
    base_delay = get_status_retry_base_seconds()
    max_delay = get_status_retry_max_seconds()

    for attempt in range(max_retries + 1):
        result = await operation()
        if not isinstance(result, dict):
            return {"status": 0, "ok": False, "error": "Invalid operation response"}

        try:
            status = int(result.get("status"))
        except (TypeError, ValueError):
            status = 0

        if status not in statuses or attempt >= max_retries:
            return result

        backoff = min(max_delay, base_delay * (2 ** attempt))
        retry_after = result.get("retry_after") or result.get("retryAfter")
        try:
            if retry_after is not None:
                backoff = min(max_delay, max(0.0, float(retry_after)))
        except (TypeError, ValueError):
            pass
        jitter = random.uniform(0.0, min(5.0, backoff * 0.25))
        wait_seconds = min(60.0, backoff + jitter)
        logger.warning(
            f"⚠️ {operation_name} 返回 HTTP {status}，"
            f"{wait_seconds:.1f} 秒后重试（{attempt + 1}/{max_retries}）"
        )
        await asyncio.sleep(wait_seconds)

    return result
