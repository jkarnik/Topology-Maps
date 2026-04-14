import asyncio
import time
import pytest
from server.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_allows_burst_up_to_capacity():
    limiter = RateLimiter(rate=5, capacity=5)
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_throttles_beyond_capacity():
    limiter = RateLimiter(rate=5, capacity=5)
    for _ in range(5):
        await limiter.acquire()
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15

@pytest.mark.asyncio
async def test_rate_limiter_concurrent_requests():
    limiter = RateLimiter(rate=5, capacity=5)
    start = time.monotonic()
    await asyncio.gather(*[limiter.acquire() for _ in range(10)])
    elapsed = time.monotonic() - start
    assert elapsed >= 0.8
    assert elapsed < 2.0
