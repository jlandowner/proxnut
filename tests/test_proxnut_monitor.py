"""Behavioural tests for :class:`proxnut.proxnut.ProxnutMonitor`."""

from __future__ import annotations

import os
import unittest
from typing import cast
from unittest.mock import patch

from proxnut.proxnut import ProxnutMonitor

from tests.mocks import MockNotifier, MockProxmoxClient, MockTimer, MockUPSClient


class ProxnutMonitorTests(unittest.TestCase):
    ENV_PATCH = {
        "PROXNUT_SHUTDOWN_HOSTS": "node1,node2",
        "PROXNUT_SHUTDOWN_DELAY": "15",
        "PROXNUT_CHECK_INTERVAL": "5",
        "MAX_CHECK_ERROR_LIMITS": "3",
    }

    def setUp(self):
        MockTimer.reset()
        self.timer_patcher = patch("proxnut.proxnut.threading.Timer", MockTimer)
        self.timer_patcher.start()

        self.env_patcher = patch.dict(os.environ, self.ENV_PATCH, clear=False)
        self.env_patcher.start()

        self.init_clients_patcher = patch.object(
            ProxnutMonitor, "init_clients", autospec=True, return_value=None
        )
        self.init_clients_patcher.start()

    def tearDown(self):
        self.init_clients_patcher.stop()
        self.env_patcher.stop()
        self.timer_patcher.stop()

    def _build_monitor(
        self,
        proxmox_client: MockProxmoxClient | None = None,
        ups_client: MockUPSClient | None = None,
        notifier: MockNotifier | None = None,
    ) -> ProxnutMonitor:
        monitor = ProxnutMonitor()
        proxmox_client = proxmox_client or MockProxmoxClient()
        ups_client = ups_client or MockUPSClient()
        notifier = notifier or MockNotifier()
        monitor.proxmox_client = proxmox_client  # type: ignore[assignment]
        monitor.ups_client = ups_client  # type: ignore[assignment]
        monitor.notifier = notifier  # type: ignore[assignment]
        monitor.monitoring_timer = None
        monitor.shutdown_timer = None
        monitor.error_count = 0
        monitor.check_interval = monitor.default_check_interval
        return monitor

    def test_reschedules_when_status_normal(self):
        """When the UPS and Proxmox report healthy status, it should reschedule the next check at the default interval."""
        # Prepare a monitor wired with default mock dependencies for observation in this test.
        monitor = self._build_monitor()
        notifier = cast(MockNotifier, monitor.notifier)  # type: ignore[arg-type]

        # Run a single monitoring cycle to simulate a healthy check.
        monitor.start_shutdown_timer_timer()

        # Confirm timers and notifications reflect the healthy state with no errors recorded.
        self.assertEqual(len(MockTimer.instances), 1)
        timer = MockTimer.instances[-1]
        self.assertEqual(timer.interval, monitor.default_check_interval)
        self.assertEqual(monitor.check_interval, monitor.default_check_interval)
        self.assertFalse(notifier.power_loss_calls)
        self.assertFalse(notifier.error_calls)
        self.assertEqual(monitor.error_count, 0)

    def test_power_loss_triggers_immediate_shutdown(self):
        """When power loss occurs with zero delay, it should execute shutdown immediately and exit successfully."""
        # Configure mocks so that Proxmox shutdown partially succeeds and UPS reports on-battery status.
        proxmox_client = MockProxmoxClient(
            shutdown_behaviour={"node1": True, "node2": False}
        )
        ups_client = MockUPSClient(
            variables={"ups.status": "OB"},
            raise_status_error=True,
        )
        notifier = MockNotifier()
        # Build a monitor using the prepared mocks and force zero shutdown delay.
        monitor = self._build_monitor(
            proxmox_client=proxmox_client, ups_client=ups_client, notifier=notifier
        )
        monitor.shutdown_delay = 0

        # Patch sys.exit to capture exit behaviour while triggering the monitoring loop once.
        with patch("proxnut.proxnut.sys.exit") as exit_patch:
            monitor.start_shutdown_timer_timer()

        # Check notifications, shutdown results, and ensure the process would have exited successfully.
        self.assertEqual(len(notifier.power_loss_calls), 1)
        power_loss_call = notifier.power_loss_calls[0]
        self.assertEqual(power_loss_call["shutdown_delay"], 0)
        self.assertEqual(len(notifier.shutdown_executed_calls), 1)
        shutdown_call = notifier.shutdown_executed_calls[0]
        self.assertEqual(shutdown_call["target_hosts"], ["node1", "node2"])
        self.assertEqual(shutdown_call["successful_nodes"], ["node1"])
        self.assertEqual(shutdown_call["failed_nodes"], ["node2"])
        self.assertEqual(proxmox_client.shutdown_calls, [["node1", "node2"]])
        exit_patch.assert_called_once_with(0)
        self.assertFalse(monitor.is_shutdown_scheduled())

    def test_delayed_shutdown_executes_when_power_not_recovered(self):
        """When power loss persists during delay, it should execute the scheduled shutdown and exit successfully."""
        # Configure mocks to keep the UPS in battery mode and have all nodes shut down successfully.
        proxmox_client = MockProxmoxClient(
            shutdown_behaviour={"node1": True, "node2": True}
        )
        ups_client = MockUPSClient(
            variables={"ups.status": "OB"},
            raise_status_error=True,
        )
        notifier = MockNotifier()
        # Build the monitor with delayed shutdown enabled via the environment configuration.
        monitor = self._build_monitor(
            proxmox_client=proxmox_client, ups_client=ups_client, notifier=notifier
        )

        # Patch sys.exit, trigger the initial monitoring cycle, and capture the scheduled shutdown timer.
        with patch("proxnut.proxnut.sys.exit") as exit_patch:
            monitor.start_shutdown_timer_timer()
            shutdown_callback = getattr(monitor, "_ProxnutMonitor__execute_shutdown")
            shutdown_timer = next(
                timer
                for timer in MockTimer.instances
                if timer.function == shutdown_callback
            )

            # Ensure the timer was scheduled correctly before manually firing it to simulate elapsed time.
            self.assertTrue(shutdown_timer.started)
            self.assertEqual(shutdown_timer.interval, monitor.shutdown_delay)
            exit_patch.assert_not_called()

            shutdown_timer.fire()

        # After firing the timer, the shutdown should have completed and the process should exit cleanly.
        exit_patch.assert_called_once_with(0)
        self.assertEqual(len(notifier.shutdown_executed_calls), 1)
        self.assertTrue(shutdown_timer.cancelled)
        self.assertFalse(monitor.is_shutdown_scheduled())

    def test_delayed_shutdown_is_cancelled_when_power_recovers(self):
        """When power recovers before the delay elapses, it should cancel the scheduled shutdown and notify recovery."""
        # Configure mocks to start with power loss but allow for successful shutdowns if executed.
        proxmox_client = MockProxmoxClient(
            shutdown_behaviour={"node1": True, "node2": True}
        )
        ups_client = MockUPSClient(
            variables={"ups.status": "OB"},
            raise_status_error=True,
        )
        notifier = MockNotifier()
        # Build the monitor to use the mocked dependencies for this recovery scenario.
        monitor = self._build_monitor(
            proxmox_client=proxmox_client, ups_client=ups_client, notifier=notifier
        )

        # Trigger the monitoring cycle once, then adjust the UPS mock to report recovery before the next cycle.
        with patch("proxnut.proxnut.sys.exit") as exit_patch:
            monitor.start_shutdown_timer_timer()
            shutdown_callback = getattr(monitor, "_ProxnutMonitor__execute_shutdown")
            shutdown_timer = next(
                timer
                for timer in MockTimer.instances
                if timer.function == shutdown_callback
            )

            # Flip the UPS status back to normal and invoke the monitoring loop again to simulate recovery.
            ups_client.raise_status_error = False
            ups_client.variables["ups.status"] = "OL"

            monitor.start_shutdown_timer_timer()

        # Verify the shutdown was cancelled, recovery was notified, and no exit was attempted.
        exit_patch.assert_not_called()
        self.assertTrue(shutdown_timer.cancelled)
        self.assertIsNone(monitor.shutdown_timer)
        self.assertEqual(len(notifier.power_recovered_calls), 1)
        self.assertEqual(len(notifier.shutdown_executed_calls), 0)

    def test_unexpected_error_triggers_backoff_and_exit_on_limit(self):
        """If unexpected errors keep occurring, it should back off and exit once the retry limit is exceeded."""
        # Configure the Proxmox mock to raise an unexpected error on every API call.
        proxmox_client = MockProxmoxClient(nodes_get_side_effect=RuntimeError("boom"))
        notifier = MockNotifier()
        monitor = self._build_monitor(proxmox_client=proxmox_client, notifier=notifier)

        # Run the monitoring loop once to capture the first error and ensure backoff is applied.
        monitor.start_shutdown_timer_timer()
        self.assertEqual(monitor.error_count, 1)
        self.assertEqual(len(notifier.error_calls), 1)
        self.assertEqual(
            MockTimer.instances[-1].interval, monitor.default_check_interval * 2
        )
        self.assertEqual(monitor.check_interval, monitor.default_check_interval * 2)

        # Continue the loop until the error threshold is exceeded and confirm the process would exit.
        with patch("proxnut.proxnut.sys.exit") as exit_patch:
            for _ in range(monitor.max_check_error_limits):
                monitor.start_shutdown_timer_timer()

        exit_patch.assert_called_once_with(1)
        self.assertGreater(monitor.error_count, monitor.max_check_error_limits)

    def test_proxmox_api_failure_is_reported_and_backed_off(self):
        """When Proxmox API raises an error, it should notify the error and schedule a backoff retry."""
        # Configure the Proxmox mock to raise a deterministic API failure.
        proxmox_client = MockProxmoxClient(
            nodes_get_side_effect=RuntimeError("api down")
        )
        notifier = MockNotifier()
        monitor = self._build_monitor(proxmox_client=proxmox_client, notifier=notifier)

        # Execute the monitoring loop once to trigger the API failure and subsequent error handling.
        monitor.start_shutdown_timer_timer()

        # Ensure the error was reported with context and a backoff retry was scheduled.
        self.assertEqual(monitor.error_count, 1)
        self.assertEqual(len(notifier.error_calls), 1)
        error_call = notifier.error_calls[0]
        self.assertIn("api down", error_call["error_message"])
        self.assertTrue(error_call["context"])  # traceback captured
        self.assertEqual(len(MockTimer.instances), 1)
        next_timer = MockTimer.instances[-1]
        self.assertEqual(next_timer.interval, monitor.default_check_interval * 2)
        self.assertEqual(monitor.check_interval, monitor.default_check_interval * 2)


if __name__ == "__main__":
    unittest.main()
