"""J3: Prometheus metrics + rate limiting."""

from __future__ import annotations

from traffic_os.api.observability import Metrics, RateLimiter


def test_metrics_render_prometheus_format():
    m = Metrics()
    m.inc("http_requests_total", {"path": "/network"})
    m.inc("http_requests_total", {"path": "/network"})
    m.set_gauge("sim_tick", 42)
    text = m.render()
    assert "# TYPE http_requests_total counter" in text
    assert 'http_requests_total{path="/network"} 2.0' in text
    assert "sim_tick 42" in text


def test_rate_limiter_blocks_over_limit():
    rl = RateLimiter(per_min=3)
    assert all(rl.allow("1.2.3.4") for _ in range(3))
    assert rl.allow("1.2.3.4") is False  # 4th within the minute -> blocked
    # a different client is unaffected
    assert rl.allow("5.6.7.8") is True


def test_rate_limiter_disabled_allows_all():
    rl = RateLimiter(per_min=0)
    assert all(rl.allow("x") for _ in range(1000))
