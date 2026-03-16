"""HealthProber is the liveness-probe analogue: periodically sends a canary prompt to each registered model and updates LLMPool health signals."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry


class HealthProber:
    """
    Background thread that probes each registered model with a canary LLM call.

    Analogous to Kubernetes liveness probes: sends a minimal prompt to each
    model on a fixed interval and updates the LLMPool health and load signals
    based on actual response time and success.

    The prober runs as a daemon thread — it is silently cancelled on shutdown.
    """

    _CANARY_PROMPT = "Reply with: ok"
    _CANARY_MAX_TOKENS = 4

    def __init__(
        self,
        pool: "LLMPool",
        interval_s: float = 60.0,
        timeout_s: float = 10.0,
    ) -> None:
        self._pool = pool
        self._interval_s = interval_s
        self._timeout_s = timeout_s
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background probing thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        t = threading.Thread(target=self._loop, daemon=True, name="kubeai-health-prober")
        t.start()
        self._thread = t

    def _loop(self) -> None:
        while True:
            time.sleep(self._interval_s)
            models = self._pool.list_models()
            for entry in models:
                self._probe_model(entry)

    def _probe_model(self, entry: "ModelEntry") -> None:
        """Probe a single model entry and update pool health signals."""
        try:
            import litellm  # type: ignore[import]
        except ImportError:
            return

        try:
            t0 = time.monotonic()
            response = litellm.completion(
                model=entry.model_id,
                messages=[{"role": "user", "content": self._CANARY_PROMPT}],
                max_tokens=self._CANARY_MAX_TOKENS,
                timeout=self._timeout_s,
            )
            latency = time.monotonic() - t0
            content = (response.choices[0].message.content or "").lower()
            ok = "ok" in content
            # Normalise load: latency relative to timeout (0.0 = instant, 1.0 = timed out)
            load = min(1.0, latency / max(self._timeout_s, 0.001))
            self._pool.update_health(entry.model_id, healthy=ok, load=load)
        except Exception:
            try:
                self._pool.update_health(entry.model_id, healthy=False)
            except KeyError:
                pass  # model deregistered between probe and update

    def __repr__(self) -> str:
        alive = self._thread is not None and self._thread.is_alive()
        return f"HealthProber(interval_s={self._interval_s}, running={alive})"
