import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from rf_visualizer import (  # noqa: E402
    CompletionStatus,
    AnalysisWindowQueue,
    WINDOW_SIZE,
    analyze_rssi_window,
    classify_energy,
    make_demo_windows,
    open_serial_port,
    read_rssi_sample,
)


class AnalysisQueueTests(unittest.TestCase):
    def test_fifo_order_and_complete_status(self):
        queue = AnalysisWindowQueue()
        first = queue.enqueue_complete_window([-60] * WINDOW_SIZE)
        second = queue.enqueue_complete_window([-59] * WINDOW_SIZE)
        processed_first = queue.process_next()
        processed_second = queue.process_next()

        self.assertEqual((first.sequence_id, second.sequence_id), (1, 2))
        self.assertEqual((processed_first[0].sequence_id, processed_second[0].sequence_id), (1, 2))
        self.assertEqual(first.status, CompletionStatus.COMPLETE)
        self.assertEqual(first.movement, "No Movement")

    def test_partial_and_blocked_items_have_reasons(self):
        queue = AnalysisWindowQueue()
        partial = queue.record_partial([-60] * 37, "stream paused")
        blocked = queue.record_blocked("serial stream unavailable")

        self.assertEqual(partial.status, CompletionStatus.PARTIAL)
        self.assertEqual(partial.received_samples, 37)
        self.assertEqual(blocked.status, CompletionStatus.BLOCKED)
        self.assertIn("unavailable", blocked.reason)

    def test_unresolved_is_only_a_threshold_boundary(self):
        movement, reason = classify_energy(0.2)
        self.assertEqual(movement, "Ambiguous")
        self.assertIsNotNone(reason)
        self.assertEqual(classify_energy(0.05)[0], "No Movement")

    def test_fft_pipeline_executes_for_complete_window(self):
        samples = np.rint(-60 + np.cumsum(np.r_[0, np.sin(np.arange(WINDOW_SIZE - 1))])).astype(int)
        result = analyze_rssi_window(samples)
        self.assertEqual(len(result.spectrum), (WINDOW_SIZE - 1) // 2)
        self.assertGreaterEqual(result.energy, 0)

    def test_demo_mode_exposes_all_required_completion_states(self):
        queue = AnalysisWindowQueue()
        make_demo_windows(queue)
        self.assertEqual(
            [item.status for item in queue.history],
            [
                CompletionStatus.PARTIAL,
                CompletionStatus.BLOCKED,
                CompletionStatus.COMPLETE,
                CompletionStatus.UNRESOLVED,
            ],
        )

    def test_serial_connection_uses_the_requested_port(self):
        opened = []

        class FakeSerial:
            def __init__(self, port, baudrate, timeout):
                opened.append((port, baudrate, timeout))

        fake_module = types.SimpleNamespace(Serial=FakeSerial, SerialException=OSError)
        with patch.dict(sys.modules, {"serial": fake_module}):
            connection, reason = open_serial_port("COM5")

        self.assertIsInstance(connection, FakeSerial)
        self.assertIsNone(reason)
        self.assertEqual(opened, [("COM5", 115200, 0)])

    def test_rssi_parser_accepts_esp32_output(self):
        class FakeConnection:
            in_waiting = 9

            @staticmethod
            def readline():
                return b"RSSI:-46\r\n"

        self.assertEqual(read_rssi_sample(FakeConnection()), -46)


if __name__ == "__main__":
    unittest.main()
