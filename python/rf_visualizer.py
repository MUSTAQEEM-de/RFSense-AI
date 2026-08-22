"""RFSense AI live visualizer with an ordered RSSI analysis-window queue."""

from __future__ import annotations

import argparse
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Iterable, Optional

import numpy as np

# These two optional runtime dependencies are imported only when their feature
# is used.  Queue/state logic can therefore be checked without a GUI or COM
# port installed.
plt = None


WINDOW_SIZE = 64
ROWS = 40
COLS = 60
STALE_STREAM_SECONDS = 2.5
AMBIGUITY_MARGIN = 0.035
STATUS_COLORS = {
    "COMPLETE": "#46d369",
    "PARTIAL": "#f0ad4e",
    "BLOCKED": "#e05252",
    "UNRESOLVED": "#bd7bea",
    "WAITING": "#6ca0dc",
    "PROCESSING": "#57c7d4",
}


class CompletionStatus(str, Enum):
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class AnalysisResult:
    energy: float
    movement: str
    spectrum: np.ndarray
    unresolved_reason: Optional[str] = None


@dataclass
class AnalysisWindow:
    sequence_id: int
    timestamp: float
    samples: list[int]
    expected_samples: int = WINDOW_SIZE
    status: CompletionStatus = CompletionStatus.WAITING
    movement: Optional[str] = None
    reason: Optional[str] = None
    energy: Optional[float] = None
    processed_at: Optional[float] = None

    @property
    def received_samples(self) -> int:
        return len(self.samples)


def classify_energy(energy: float) -> tuple[str, Optional[str]]:
    """Keep the original movement bands, withholding only boundary cases."""
    nearest_boundary = min((0.2, 0.5), key=lambda boundary: abs(energy - boundary))
    if abs(energy - nearest_boundary) <= AMBIGUITY_MARGIN:
        return (
            "Ambiguous",
            f"Spectrum energy {energy:.3f} is near the {nearest_boundary:.1f} classification boundary.",
        )
    if energy < 0.2:
        return "No Movement", None
    if energy < 0.5:
        return "Movement", None
    return "High Movement", None


def analyze_rssi_window(samples: Iterable[int]) -> AnalysisResult:
    """Run the MVP delta/FFT pipeline on one complete, non-overlapping window."""
    values = np.asarray(list(samples), dtype=float)
    if values.size != WINDOW_SIZE:
        raise ValueError(f"Expected {WINDOW_SIZE} RSSI samples, got {values.size}.")

    deltas = np.diff(values)
    fft = np.fft.fft(deltas)
    magnitude = np.abs(fft[: len(fft) // 2])
    normalized = magnitude / (np.max(magnitude) + 1e-6)
    energy = float(np.mean(normalized))
    movement, unresolved_reason = classify_energy(energy)
    return AnalysisResult(energy, movement, normalized, unresolved_reason)


class AnalysisWindowQueue:
    """FIFO queue plus bounded history of distinct RSSI analysis windows."""

    def __init__(self, history_limit: int = 12) -> None:
        self._next_sequence = 1
        self.pending: Deque[AnalysisWindow] = deque()
        self.history: Deque[AnalysisWindow] = deque(maxlen=history_limit)

    def _new_item(self, samples: Iterable[int], status: CompletionStatus) -> AnalysisWindow:
        item = AnalysisWindow(
            sequence_id=self._next_sequence,
            timestamp=time.time(),
            samples=list(samples),
            status=status,
        )
        self._next_sequence += 1
        self.history.append(item)
        return item

    def enqueue_complete_window(self, samples: Iterable[int]) -> AnalysisWindow:
        values = list(samples)
        if len(values) != WINDOW_SIZE:
            raise ValueError("Only a complete 64-sample window can enter the processing queue.")
        item = self._new_item(values, CompletionStatus.WAITING)
        self.pending.append(item)
        return item

    def record_partial(self, samples: Iterable[int], reason: str) -> AnalysisWindow:
        values = list(samples)
        if not 0 < len(values) < WINDOW_SIZE:
            raise ValueError("A partial window must contain between 1 and 63 samples.")
        item = self._new_item(values, CompletionStatus.PARTIAL)
        item.reason = reason
        item.processed_at = time.time()
        return item

    def record_blocked(self, reason: str, samples: Iterable[int] = ()) -> AnalysisWindow:
        item = self._new_item(samples, CompletionStatus.BLOCKED)
        item.reason = reason
        item.processed_at = time.time()
        return item

    def process_next(self) -> Optional[tuple[AnalysisWindow, AnalysisResult]]:
        if not self.pending:
            return None
        item = self.pending.popleft()
        item.status = CompletionStatus.PROCESSING
        try:
            result = analyze_rssi_window(item.samples)
        except Exception as exc:
            item.status = CompletionStatus.BLOCKED
            item.reason = f"Analysis pipeline unavailable: {exc}"
            item.processed_at = time.time()
            return None

        item.energy = result.energy
        item.movement = result.movement
        item.processed_at = time.time()
        if result.unresolved_reason:
            item.status = CompletionStatus.UNRESOLVED
            item.reason = result.unresolved_reason
        else:
            item.status = CompletionStatus.COMPLETE
        return item, result

    def counts(self) -> Counter:
        return Counter(item.status.value for item in self.history)


class RFSenseVisualizer:
    def __init__(self, queue: AnalysisWindowQueue) -> None:
        global plt
        import matplotlib.pyplot as pyplot

        plt = pyplot
        plt.style.use("dark_background")
        plt.ion()
        self.queue = queue
        self.figure = plt.figure(figsize=(13, 7))
        grid = self.figure.add_gridspec(2, 2, width_ratios=(1, 1.25), height_ratios=(1, 1))
        self.ax_radar = self.figure.add_subplot(grid[:, 0], polar=True)
        self.ax_spectrum = self.figure.add_subplot(grid[0, 1])
        self.ax_queue = self.figure.add_subplot(grid[1, 1])
        self.spectrum_buffer = np.zeros((ROWS, COLS))
        self.last_title = "Waiting for RSSI"
        self.last_color = "cyan"
        self.image = self.ax_spectrum.imshow(
            self.spectrum_buffer[8:22, :], aspect="auto", cmap="plasma", origin="lower", interpolation="bilinear"
        )
        self._draw_spectrum_labels()
        plt.show(block=False)

    def _draw_spectrum_labels(self) -> None:
        self.ax_spectrum.set_title("Real-Time Motion Spectrum", fontsize=10)
        self.ax_spectrum.set_xlabel("Analysis windows →", fontsize=8)
        self.ax_spectrum.set_ylabel("Freq band", fontsize=8)
        self.ax_spectrum.set_xticks([])
        self.ax_spectrum.set_yticks([])

    def add_result(self, result: AnalysisResult) -> None:
        resized = np.interp(
            np.linspace(0, len(result.spectrum) - 1, ROWS),
            np.arange(len(result.spectrum)),
            result.spectrum,
        )
        self.spectrum_buffer = np.roll(self.spectrum_buffer, -1, axis=1)
        self.spectrum_buffer[:, -1] = resized
        self.image.set_data(np.power(np.clip(self.spectrum_buffer[8:22, :], 0, 1), 0.5))
        if result.movement == "No Movement":
            self.last_color, self.last_title = "cyan", "No Movement"
        elif result.movement == "Movement":
            self.last_color, self.last_title = "orange", "Movement ⚠"
        elif result.movement == "High Movement":
            self.last_color, self.last_title = "red", "High Movement 🚨"
        else:
            self.last_color, self.last_title = "#bd7bea", "Signal Unresolved"

    def _draw_radar(self) -> None:
        ax = self.ax_radar
        ax.clear()
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 1)
        theta = np.linspace(0, 2 * np.pi, 400)
        ax.fill(theta, np.ones_like(theta), color="#020202")
        for alpha in (0.05, 0.1, 0.2):
            ax.fill(theta, np.ones_like(theta), color=self.last_color, alpha=alpha)
        for radius in (0.4, 0.7):
            ax.plot(theta, [radius] * len(theta), linewidth=1)
        for direction in (0, np.pi / 2, np.pi, 3 * np.pi / 2):
            ax.plot([direction, direction], [0, 1])
        sweep_start = (time.monotonic() * 1.2) % (2 * np.pi)
        sweep_theta = np.linspace(sweep_start, sweep_start + 0.3, 200)
        ax.fill_between(sweep_theta, 0, 1, color=self.last_color, alpha=0.4)
        ax.set_title(self.last_title)

    def _draw_queue(self) -> None:
        ax = self.ax_queue
        ax.clear()
        ax.set_axis_off()
        counts = self.queue.counts()
        summary = "  ".join(
            f"{label[0]}:{counts.get(label, 0)}"
            for label in ("COMPLETE", "PARTIAL", "BLOCKED", "UNRESOLVED", "PROCESSING")
        )
        ax.text(0.01, 0.96, "RF ANALYSIS QUEUE", fontsize=12, fontweight="bold", va="top", transform=ax.transAxes)
        ax.text(0.01, 0.86, f"Total: {len(self.queue.history)}  {summary}", fontsize=8, color="#d5d5d5", transform=ax.transAxes)
        ax.text(0.01, 0.75, "WINDOW       SAMPLES       STATUS          RESULT / REASON", fontsize=8, color="#9ca7b8", transform=ax.transAxes)
        for row, item in enumerate(list(self.queue.history)[-6:]):
            y = 0.64 - row * 0.105
            status = item.status.value
            result = item.movement or item.reason or "Waiting for processing"
            if item.reason and item.movement:
                result = f"{item.movement}: {item.reason}"
            if len(result) > 47:
                result = result[:44] + "..."
            ax.text(0.01, y, f"#{item.sequence_id:03d}", fontsize=9, transform=ax.transAxes)
            ax.text(0.18, y, f"{item.received_samples:02d}/{item.expected_samples}", fontsize=9, transform=ax.transAxes)
            ax.text(0.36, y, status, fontsize=9, color=STATUS_COLORS[status], fontweight="bold", transform=ax.transAxes)
            ax.text(0.60, y, result, fontsize=8, color="#d5d5d5", transform=ax.transAxes)

    def refresh(self) -> None:
        self._draw_radar()
        self._draw_queue()
        self.figure.tight_layout()
        plt.pause(0.03)


def open_serial_port(port: str) -> tuple[Optional["serial.Serial"], Optional[str]]:
    import serial

    try:
        connection = serial.Serial(port, 115200, timeout=0)
        print("Using:", port)
        return connection, None
    except serial.SerialException as exc:
        return None, f"ESP32 serial stream unavailable on {port}: {exc}"


def read_rssi_sample(connection: "serial.Serial") -> Optional[int]:
    if not connection.in_waiting:
        return None
    line = connection.readline().decode(errors="ignore").strip()
    if not line.startswith("RSSI:"):
        return None
    try:
        return int(line.split(":", 1)[1])
    except ValueError:
        return None


def make_demo_windows(queue: AnalysisWindowQueue) -> list[AnalysisResult]:
    """Clearly separated demo data for showing every required completion state."""
    results: list[AnalysisResult] = []
    queue.record_partial([-60] * 37, "RSSI stream paused before this 64-sample window was complete.")
    queue.record_blocked("ESP32 serial stream unavailable (demo condition).")

    complete = queue.enqueue_complete_window([-60] * WINDOW_SIZE)
    processed = queue.process_next()
    if processed:
        _, result = processed
        results.append(result)

    n = np.arange(WINDOW_SIZE - 1)
    # The scale prevents integer RSSI rounding from moving this controlled
    # demo waveform away from the same 0.2 classifier boundary used in real mode.
    deltas = 20 * sum(np.sin(2 * np.pi * harmonic * n / len(n)) for harmonic in range(1, 7))
    unresolved_samples = np.rint(-60 + np.r_[0, np.cumsum(deltas)]).astype(int).tolist()
    queue.enqueue_complete_window(unresolved_samples)
    processed = queue.process_next()
    if processed:
        _, result = processed
        results.append(result)
    return results


def run(args: argparse.Namespace) -> None:
    queue = AnalysisWindowQueue()
    visualizer = None if args.headless else RFSenseVisualizer(queue)

    if args.demo:
        for result in make_demo_windows(queue):
            if visualizer:
                visualizer.add_result(result)
        if args.headless:
            print("Demo queue:", [(item.sequence_id, item.status.value) for item in queue.history])
            return
        while plt.fignum_exists(visualizer.figure.number):
            visualizer.refresh()
        return

    try:
        connection, connection_reason = open_serial_port(args.port)
    except ModuleNotFoundError:
        connection, connection_reason = None, "ESP32 serial stream unavailable: PySerial is not installed."
    current_samples: list[int] = []
    last_sample_at = time.monotonic()
    stream_issue_recorded = False
    if connection_reason:
        queue.record_blocked(connection_reason)
        stream_issue_recorded = True

    try:
        while args.headless or plt.fignum_exists(visualizer.figure.number):
            sample = None
            if connection:
                try:
                    sample = read_rssi_sample(connection)
                except Exception as exc:
                    connection = None
                    connection_reason = f"ESP32 serial stream unavailable: {exc}"

            if sample is not None:
                current_samples.append(sample)
                last_sample_at = time.monotonic()
                stream_issue_recorded = False
                if len(current_samples) == WINDOW_SIZE:
                    queue.enqueue_complete_window(current_samples)
                    current_samples = []
                    processed = queue.process_next()
                    if processed and visualizer:
                        visualizer.add_result(processed[1])
            elif not stream_issue_recorded and time.monotonic() - last_sample_at >= STALE_STREAM_SECONDS:
                if current_samples:
                    queue.record_partial(current_samples, "RSSI stream paused before this 64-sample window was complete.")
                    current_samples = []
                queue.record_blocked(connection_reason or "ESP32 serial stream unavailable: no RSSI samples received.")
                stream_issue_recorded = True

            if visualizer:
                visualizer.refresh()
            else:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if connection:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="RFSense AI RSSI visualizer with ordered analysis-window queue")
    parser.add_argument("--port", default="COM5", help="ESP32 serial port (default: COM5).")
    parser.add_argument("--demo", action="store_true", help="Run isolated deterministic queue demo data, never real sensing.")
    parser.add_argument("--headless", action="store_true", help="Run without opening the Matplotlib window (useful for checks).")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
