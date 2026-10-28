"""Prometheus 메트릭 (외부 의존성 없이 직접 구현).

노출 형식: https://prometheus.io/docs/instrumenting/exposition_formats/
라벨 카디널리티를 낮추기 위해 경로는 route 로 정규화한다(예: /api/book?id=.. -> /api/book).
"""
from __future__ import annotations

import threading
import time

BUCKETS: tuple[float, ...] = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


def _esc(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(**kw) -> str:
    if not kw:
        return ""
    return "{" + ",".join(f'{k}="{_esc(v)}"' for k, v in kw.items() if v is not None) + "}"


class Metrics:
    """스레드 안전한 최소 메트릭 레지스트리."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: dict[tuple[str, str, str], int] = {}
        self.hist: dict[str, list[int]] = {}
        self.hist_sum: dict[str, float] = {}
        self.hist_count: dict[str, int] = {}
        self.in_flight = 0
        self.search_queries: dict[tuple[str, str], int] = {}
        self.stage_sum: dict[str, float] = {}
        self.stage_count: dict[str, int] = {}
        self.gauges: dict[str, float] = {}
        self.build_info: dict[str, str] = {}

    # ---------------- observe ----------------
    def inc_in_flight(self) -> None:
        with self._lock:
            self.in_flight += 1

    def dec_in_flight(self) -> None:
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        key = (method, route, str(status))
        with self._lock:
            self.requests[key] = self.requests.get(key, 0) + 1
            buckets = self.hist.get(route)
            if buckets is None:
                buckets = [0] * len(BUCKETS)
                self.hist[route] = buckets
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    buckets[i] += 1
            self.hist_sum[route] = self.hist_sum.get(route, 0.0) + seconds
            self.hist_count[route] = self.hist_count.get(route, 0) + 1

    def observe_search(self, mode: str, strategy: str, stage_seconds: dict) -> None:
        with self._lock:
            k = (mode, strategy or "unknown")
            self.search_queries[k] = self.search_queries.get(k, 0) + 1
            for stage, sec in stage_seconds.items():
                self.stage_sum[stage] = self.stage_sum.get(stage, 0.0) + float(sec)
                self.stage_count[stage] = self.stage_count.get(stage, 0) + 1

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self.gauges[name] = float(value)

    # ---------------- render ----------------
    def render(self) -> str:
        t0 = time.time()
        lines: list[str] = []

        # counter: 요청 수
        lines.append("# HELP seoga_http_requests_total HTTP 요청 수")
        lines.append("# TYPE seoga_http_requests_total counter")
        with self._lock:
            for (method, route, status), n in sorted(self.requests.items()):
                lines.append(f"seoga_http_requests_total{_labels(method=method, route=route, status=status)} {n}")

        # histogram: 요청 지연
        lines.append("# HELP seoga_http_request_duration_seconds HTTP 요청 처리 시간")
        lines.append("# TYPE seoga_http_request_duration_seconds histogram")
        with self._lock:
            for route, buckets in sorted(self.hist.items()):
                cum = 0
                for i, b in enumerate(BUCKETS):
                    cum += buckets[i]
                    lines.append(
                        f"seoga_http_request_duration_seconds_bucket{_labels(route=route, le=f'{b:g}')} {cum}"
                    )
                lines.append(
                    f"seoga_http_request_duration_seconds_bucket{_labels(route=route, le='+Inf')} {cum}"
                )
                lines.append(f"seoga_http_request_duration_seconds_sum{_labels(route=route)} {self.hist_sum.get(route, 0):.6f}")
                lines.append(f"seoga_http_request_duration_seconds_count{_labels(route=route)} {self.hist_count.get(route, 0)}")

            # gauges
            lines.append("# HELP seoga_http_in_flight 처리 중인 요청 수")
            lines.append("# TYPE seoga_http_in_flight gauge")
            lines.append(f"seoga_http_in_flight {self.in_flight}")

        lines.append("# HELP seoga_search_queries_total 검색 질의 수 (모드/전략)")
        lines.append("# TYPE seoga_search_queries_total counter")
        with self._lock:
            stats = dict(self.stage_sum)
            counts = dict(self.stage_count)
            sq = dict(self.search_queries)
        for (mode, strategy), n in sorted(sq.items()):
            lines.append(f"seoga_search_queries_total{_labels(mode=mode, strategy=strategy)} {n}")

        for stage in ("keyword", "vector", "fuse"):
            lines.append(f"# HELP seoga_search_stage_seconds 검색 단계 소요시간 ({stage})")
            lines.append("# TYPE seoga_search_stage_seconds summary")
            lines.append(f"seoga_search_stage_seconds_sum{_labels(stage=stage)} {stats.get(stage, 0):.6f}")
            lines.append(f"seoga_search_stage_seconds_count{_labels(stage=stage)} {counts.get(stage, 0)}")

        with self._lock:
            gauges = dict(self.gauges)
            build = dict(self.build_info)
        for name in sorted(gauges):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {gauges[name]:g}")

        lines.append("# HELP seoga_build_info 빌드/인덱스 정보")
        lines.append("# TYPE seoga_build_info gauge")
        lines.append(f"seoga_build_info{_labels(**build)} 1")

        lines.append("# HELP seoga_scrape_duration_seconds 메트릭 렌더 시간")
        lines.append("# TYPE seoga_scrape_duration_seconds gauge")
        lines.append(f"seoga_scrape_duration_seconds {time.time() - t0:.6f}")
        return "\n".join(lines) + "\n"


# 프로세스 전역 레지스트리
METRICS = Metrics()
