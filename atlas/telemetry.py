"""Runtime telemetry for AtlasIQ V1 pipeline stages.

Records real wall-clock milliseconds. No latency floors or fake scores.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, Optional


@dataclass
class StageTimings:
    """Elapsed milliseconds per pipeline stage (0 if stage skipped)."""

    retrieve_ms: float = 0.0
    rerank_ms: float = 0.0
    generate_ms: float = 0.0
    total_ms: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "retrieve_ms": self.retrieve_ms,
            "rerank_ms": self.rerank_ms,
            "generate_ms": self.generate_ms,
            "total_ms": self.total_ms,
        }


class TelemetryClock:
    """Accumulates stage timings with real ``perf_counter`` spans."""

    def __init__(self) -> None:
        self.timings = StageTimings()
        self._t0 = time.perf_counter()

    @contextmanager
    def span(self, stage: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if stage == "retrieve":
                self.timings.retrieve_ms = elapsed_ms
            elif stage == "rerank":
                self.timings.rerank_ms = elapsed_ms
            elif stage == "generate":
                self.timings.generate_ms = elapsed_ms
            else:
                raise ValueError(f"Unknown telemetry stage: {stage}")

    def finish(self) -> StageTimings:
        self.timings.total_ms = (time.perf_counter() - self._t0) * 1000.0
        return self.timings
