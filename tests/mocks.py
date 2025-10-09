"""Test support mocks for proxnut wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional

from proxnut.ups_client import UPSStatusNotNormalError


class MockTimer:
    """Lightweight replacement for ``threading.Timer`` that never spawns threads.

    Using the real ``threading.Timer`` in unit tests introduces background threads,
    real sleep delays, and nondeterministic execution ordering. Those behaviours
    make it difficult to assert when callbacks run, and they can cause tests to
    miss assertions or exit the process unexpectedly when shutdown logic calls
    ``sys.exit``. This mock keeps everything synchronous so tests can trigger the
    timer via :meth:`fire` exactly when needed and fully control the shutdown
    flow.
    """

    instances: List["MockTimer"] = []

    def __init__(self, interval: float, function: Callable[..., Any], *args, **kwargs):
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.started = False
        self.cancelled = False
        self.fired = False
        MockTimer.instances.append(self)

    def start(self):  # pragma: no cover - trivial
        self.started = True

    def cancel(self):  # pragma: no cover - trivial
        self.cancelled = True

    def fire(self):
        """Execute the scheduled callback immediately for deterministic testing."""
        if self.cancelled or self.fired:
            return
        self.fired = True
        self.function(*self.args, **self.kwargs)

    @classmethod
    def reset(cls):
        cls.instances.clear()


@dataclass
class MockProxmoxClient:
    """Mocked version of :class:`ProxmoxClient` with configurable behaviour."""

    nodes_get_return: Iterable[Dict[str, Any]] = field(default_factory=list)
    nodes_get_side_effect: Optional[BaseException] = None
    shutdown_behaviour: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        self.api = SimpleNamespace(nodes=SimpleNamespace(get=self._nodes_get))
        self.shutdown_calls: List[List[str]] = []

    def _nodes_get(self):
        if self.nodes_get_side_effect is not None:
            raise self.nodes_get_side_effect
        return list(self.nodes_get_return)

    def get_nodes(self) -> List[str]:  # pragma: no cover - passthrough helper
        return [node["node"] for node in self._nodes_get()]

    def shutdown_nodes(self, node_names: List[str]) -> Dict[str, bool]:
        self.shutdown_calls.append(list(node_names))
        if self.shutdown_behaviour:
            return {
                name: self.shutdown_behaviour.get(name, False) for name in node_names
            }
        return {name: True for name in node_names}

    def validate_target_nodes(
        self, target_nodes: List[str]
    ) -> bool:  # pragma: no cover
        available = {node["node"] for node in self._nodes_get()}
        targets = {target.strip() for target in target_nodes if target.strip()}
        return targets.issubset(available)


@dataclass
class MockUPSClient:
    """Mocked UPS client with controllable status behaviour."""

    ups_name: str = "test-ups"
    available_names: Optional[List[str]] = None
    variables: Dict[str, Any] = field(default_factory=lambda: {"ups.status": "OL"})
    raise_status_error: bool = False

    def __post_init__(self):
        if self.available_names is None:
            self.available_names = [self.ups_name]

    def get_ups_names(self) -> List[str]:  # pragma: no cover - helper
        return list(self.available_names or [])

    def validate_ups_name(self) -> bool:  # pragma: no cover - helper
        return bool(self.ups_name) and self.ups_name in (self.available_names or [])

    def get_ups_variables(self) -> Dict[str, Any]:  # pragma: no cover - helper
        return dict(self.variables)

    def check_ups_status_normal(self):
        if self.raise_status_error:
            status = self.variables.get("ups.status", "")
            raise UPSStatusNotNormalError(status)


class MockNotifier:
    """Recorder mock for :class:`Notifier`. Keeps track of notifications."""

    def __init__(self):
        self.power_loss_calls: List[Dict[str, Any]] = []
        self.power_recovered_calls: List[Dict[str, Any]] = []
        self.shutdown_executed_calls: List[Dict[str, Any]] = []
        self.error_calls: List[Dict[str, Any]] = []

    def notify_power_loss(self, ups_status: str, shutdown_delay: int = 0):
        self.power_loss_calls.append(
            {
                "ups_status": ups_status,
                "shutdown_delay": shutdown_delay,
            }
        )

    def notify_power_recovered(self):
        self.power_recovered_calls.append({})

    def notify_shutdown_executed(
        self,
        target_hosts: List[str],
        successful_nodes: List[str],
        failed_nodes: List[str],
    ):
        self.shutdown_executed_calls.append(
            {
                "target_hosts": list(target_hosts),
                "successful_nodes": list(successful_nodes),
                "failed_nodes": list(failed_nodes),
            }
        )

    def notify_error(self, error_message: str, context: str = ""):
        self.error_calls.append(
            {
                "error_message": error_message,
                "context": context,
            }
        )
