#!/usr/bin/env python3
"""Realtime viewer for prtouch_v2 UDP wave packets.

Usage:
    python prtouch_wave_viewer.py
    python prtouch_wave_viewer.py --port 21021 --history-seconds 60

The viewer listens for UDP packets emitted by `prtouch_v2` when
`tri_wave_ip` is configured in `printer.cfg`.
"""

from __future__ import annotations

import argparse
import queue
import socket
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from tkinter import ttk


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 21021
DEFAULT_CHANNELS = 4
DEFAULT_HISTORY_SECONDS = 60.0
DEFAULT_SAMPLE_INTERVAL = 0.011
MAX_ABS_SAMPLE_VALUE = 100000
AXIS_MARGIN_LEFT = 72
AXIS_MARGIN_RIGHT = 20
AXIS_MARGIN_TOP = 20
AXIS_MARGIN_BOTTOM = 42
REFRESH_MS = 50
COLORS = ("#4FC3F7", "#81C784", "#FFB74D", "#E57373")
SUM_COLOR = "#F062D0"
BG_COLOR = "#101318"
FG_COLOR = "#D8DEE9"
GRID_COLOR = "#2A3038"


@dataclass
class WavePacket:
    channel: int
    samples: list[int]
    trigger: int
    received_at: float
    source: tuple[str, int]
    raw: str = ""


@dataclass
class DataPoint:
    timestamp: float
    value: int


@dataclass
class ChannelState:
    samples: deque[DataPoint] = field(default_factory=deque)
    trigger: int = -1
    last_update: float = 0.0
    packet_count: int = 0

    def append_samples(self, values: list[int], received_at: float, sample_interval: float, history_seconds: float) -> None:
        filtered_values = [value for value in values if abs(value) <= MAX_ABS_SAMPLE_VALUE]
        if not filtered_values:
            return
        sample_count = len(filtered_values)
        start_time = received_at - max(sample_count - 1, 0) * sample_interval
        for idx, value in enumerate(filtered_values):
            self.samples.append(DataPoint(timestamp=start_time + idx * sample_interval, value=value))
        cutoff = received_at - history_seconds
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()
        self.last_update = received_at
        self.packet_count += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="接收 prtouch_v2 的 UDP 波形数据并实时显示所有通道。"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 21021")
    parser.add_argument(
        "--channels",
        type=int,
        default=DEFAULT_CHANNELS,
        help="通道数量，默认 4",
    )
    parser.add_argument(
        "--history-seconds",
        type=float,
        default=DEFAULT_HISTORY_SECONDS,
        help="图上保留的历史秒数，默认 60",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=DEFAULT_SAMPLE_INTERVAL,
        help="估算的采样间隔秒数，默认 0.011",
    )
    return parser.parse_args()


def parse_wave_packet(message: str, received_at: float, source: tuple[str, int]) -> WavePacket | None:
    parts = message.strip().split("$", 3)
    if len(parts) < 4:
        return None
    _, title, _, payload = parts
    if title != "SHOW_WAVE":
        return None

    items = [item.strip() for item in payload.split(",") if item.strip()]
    if len(items) < 3:
        return None

    try:
        channel = int(items[0])
        trigger = int(items[-1])
        samples = [int(item) for item in items[1:-1]]
    except ValueError:
        return None

    return WavePacket(
        channel=channel,
        samples=samples,
        trigger=trigger,
        received_at=received_at,
        source=source,
        raw=message.strip(),
    )


class UdpReceiver(threading.Thread):
    def __init__(self, host: str, port: int, out_queue: queue.SimpleQueue[WavePacket], stop_event: threading.Event):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.sock: socket.socket | None = None

    def run(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.5)

        while not self.stop_event.is_set():
            try:
                payload, source = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            received_at = time.time()
            message = payload.decode("utf-8", errors="ignore")
            packet = parse_wave_packet(message, received_at, source)
            if packet is not None:
                self.out_queue.put(packet)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass


class CombinedWaveFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, channels: int):
        super().__init__(master, padding=(8, 6))
        self.channels = channels
        self.summary_var = tk.StringVar(value="等待数据...")

        title = ttk.Label(self, text="PRTouch 四通道实时波形", font=("Segoe UI", 11, "bold"))
        title.pack(anchor="w")

        summary = ttk.Label(self, textvariable=self.summary_var)
        summary.pack(anchor="w", pady=(0, 6))

        self.canvas = tk.Canvas(
            self,
            height=620,
            background=BG_COLOR,
            highlightthickness=1,
            highlightbackground=GRID_COLOR,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw([], DEFAULT_HISTORY_SECONDS))

    def _build_sum_points(self, visible_by_channel: list[list[DataPoint]]) -> list[DataPoint]:
        events: list[tuple[float, int, int]] = []
        for channel, points in enumerate(visible_by_channel):
            for point in points:
                events.append((point.timestamp, channel, point.value))
        if not events:
            return []

        events.sort(key=lambda item: item[0])
        current_values = [0] * len(visible_by_channel)
        sum_points: list[DataPoint] = []
        for timestamp, channel, value in events:
            current_values[channel] = value
            sum_points.append(DataPoint(timestamp=timestamp, value=sum(current_values)))
        return sum_points

    def draw(self, states: list[ChannelState], history_seconds: float) -> None:
        width = max(self.canvas.winfo_width(), 10)
        height = max(self.canvas.winfo_height(), 10)
        self.canvas.delete("all")

        plot_left = AXIS_MARGIN_LEFT
        plot_top = AXIS_MARGIN_TOP
        plot_right = width - AXIS_MARGIN_RIGHT
        plot_bottom = height - AXIS_MARGIN_BOTTOM
        plot_width = max(plot_right - plot_left, 10)
        plot_height = max(plot_bottom - plot_top, 10)

        all_points = [point for state in states for point in state.samples]
        if not all_points:
            self.canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom, outline=GRID_COLOR)
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="暂无波形数据\n请执行 READ_PRES / SELF_CHECK_PRTOUCH / G29",
                fill=FG_COLOR,
                font=("Segoe UI", 11),
                justify="center",
            )
            self.summary_var.set("等待数据...")
            return

        now = time.time()
        start_time = now - history_seconds
        visible_by_channel = [
            [point for point in state.samples if point.timestamp >= start_time]
            for state in states
        ]
        sum_points = self._build_sum_points(visible_by_channel)
        visible_values = [point.value for points in visible_by_channel for point in points]
        visible_values.extend(point.value for point in sum_points)
        if not visible_values:
            self.canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom, outline=GRID_COLOR)
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="最近 60 秒内暂无波形数据",
                fill=FG_COLOR,
                font=("Segoe UI", 11),
                justify="center",
            )
            self.summary_var.set("最近 60 秒内暂无数据")
            return
        lo = min(visible_values)
        hi = max(visible_values)
        if lo == hi:
            lo -= 1
            hi += 1
        padding = max((hi - lo) * 0.1, 10.0)
        lo -= padding
        hi += padding
        span = hi - lo

        def value_to_y(value: float) -> float:
            return plot_bottom - ((value - lo) / span) * plot_height

        def time_to_x(timestamp: float) -> float:
            clamped = min(max(timestamp, start_time), now)
            if history_seconds <= 0:
                return plot_right
            return plot_left + ((clamped - start_time) / history_seconds) * plot_width

        self.canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom, outline=GRID_COLOR)

        for index in range(7):
            frac = index / 6
            y = plot_top + frac * plot_height
            value = hi - frac * span
            self.canvas.create_line(plot_left, y, plot_right, y, fill=GRID_COLOR, dash=(2, 4))
            self.canvas.create_text(
                plot_left - 8,
                y,
                text=f"{value:.0f}",
                fill=FG_COLOR,
                anchor="e",
                font=("Segoe UI", 9),
            )

        for index in range(7):
            frac = index / 6
            x = plot_left + frac * plot_width
            seconds_ago = history_seconds * (1.0 - frac)
            self.canvas.create_line(x, plot_top, x, plot_bottom, fill=GRID_COLOR, dash=(2, 4))
            self.canvas.create_text(
                x,
                plot_bottom + 16,
                text=f"-{seconds_ago:.0f}s" if seconds_ago > 0.5 else "现在",
                fill=FG_COLOR,
                anchor="n",
                font=("Segoe UI", 9),
            )

        zero_y = value_to_y(0)
        if plot_top <= zero_y <= plot_bottom:
            self.canvas.create_line(plot_left, zero_y, plot_right, zero_y, fill="#55616E", width=1)
            self.canvas.create_text(
                plot_left - 8,
                zero_y - 10,
                text="0",
                fill="#AAB4C0",
                anchor="e",
                font=("Segoe UI", 9),
            )

        legend_y = 8
        for channel, state in enumerate(states):
            color = COLORS[channel % len(COLORS)]
            x0 = plot_left + channel * 170
            self.canvas.create_rectangle(x0, legend_y, x0 + 14, legend_y + 10, fill=color, outline=color)
            latest_text = "-"
            if state.samples:
                latest_text = str(state.samples[-1].value)
            self.canvas.create_text(
                x0 + 20,
                legend_y + 5,
                text=f"CH{channel} 最新 {latest_text}",
                fill=FG_COLOR,
                anchor="w",
                font=("Segoe UI", 9),
            )

        sum_legend_x = plot_left + len(states) * 170
        self.canvas.create_rectangle(
            sum_legend_x, legend_y, sum_legend_x + 14, legend_y + 10, fill=SUM_COLOR, outline=SUM_COLOR
        )
        sum_latest_text = "-"
        if sum_points:
            sum_latest_text = str(sum_points[-1].value)
        self.canvas.create_text(
            sum_legend_x + 20,
            legend_y + 5,
            text=f"SUM 最新 {sum_latest_text}",
            fill=FG_COLOR,
            anchor="w",
            font=("Segoe UI", 9),
        )

        summary_parts: list[str] = []
        for channel, state in enumerate(states):
            color = COLORS[channel % len(COLORS)]
            visible_points = visible_by_channel[channel]
            if not visible_points:
                summary_parts.append(f"CH{channel}: 无数据")
                continue

            coords: list[float] = []
            for point in visible_points:
                coords.extend((time_to_x(point.timestamp), value_to_y(point.value)))
            if len(coords) >= 4:
                self.canvas.create_line(coords, fill=color, width=2, smooth=False)

            last_point = visible_points[-1]
            last_x = time_to_x(last_point.timestamp)
            last_y = value_to_y(last_point.value)
            self.canvas.create_oval(last_x - 3, last_y - 3, last_x + 3, last_y + 3, fill=color, outline=color)
            self.canvas.create_text(
                min(last_x + 28, plot_right - 10),
                last_y - 10,
                text=f"CH{channel}:{last_point.value}",
                fill=color,
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            )

            if 0 <= state.trigger < len(visible_points):
                trigger_point = visible_points[state.trigger]
                trig_x = time_to_x(trigger_point.timestamp)
                self.canvas.create_line(trig_x, plot_top, trig_x, plot_bottom, fill=color, dash=(4, 3))

            values = [point.value for point in visible_points]
            summary_parts.append(
                f"CH{channel}: 最新 {values[-1]}, 最小 {min(values)}, 最大 {max(values)}, 点数 {len(values)}"
            )

        if sum_points:
            sum_coords: list[float] = []
            for point in sum_points:
                sum_coords.extend((time_to_x(point.timestamp), value_to_y(point.value)))
            if len(sum_coords) >= 4:
                self.canvas.create_line(sum_coords, fill=SUM_COLOR, width=3, smooth=False)

            sum_last = sum_points[-1]
            sum_last_x = time_to_x(sum_last.timestamp)
            sum_last_y = value_to_y(sum_last.value)
            self.canvas.create_oval(
                sum_last_x - 4,
                sum_last_y - 4,
                sum_last_x + 4,
                sum_last_y + 4,
                fill=SUM_COLOR,
                outline=SUM_COLOR,
            )
            self.canvas.create_text(
                min(sum_last_x + 32, plot_right - 10),
                sum_last_y + 12,
                text=f"SUM:{sum_last.value}",
                fill=SUM_COLOR,
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            )
            sum_values = [point.value for point in sum_points]
            summary_parts.append(
                f"SUM: 最新 {sum_values[-1]}, 最小 {min(sum_values)}, 最大 {max(sum_values)}, 点数 {len(sum_values)}"
            )
        else:
            summary_parts.append("SUM: 无数据")

        self.canvas.create_text(
            (plot_left + plot_right) / 2,
            plot_bottom + 34,
            text="X 轴: 时间（最近 60 秒）",
            fill=FG_COLOR,
            font=("Segoe UI", 9),
        )
        self.canvas.create_text(
            18,
            (plot_top + plot_bottom) / 2,
            text="Y 轴\n计数值",
            fill=FG_COLOR,
            font=("Segoe UI", 9),
            justify="center",
        )
        self.summary_var.set(" | ".join(summary_parts))


class ViewerApp:
    def __init__(self, root: tk.Tk, host: str, port: int, channels: int, history_seconds: float, sample_interval: float):
        self.root = root
        self.host = host
        self.port = port
        self.history_seconds = history_seconds
        self.sample_interval = sample_interval
        self.packet_queue: queue.SimpleQueue[WavePacket] = queue.SimpleQueue()
        self.stop_event = threading.Event()
        self.receiver = UdpReceiver(host, port, self.packet_queue, self.stop_event)
        self.channel_states = [ChannelState() for _ in range(channels)]
        self.wave_view: CombinedWaveFrame | None = None

        self.total_packets = 0
        self.last_packet_time = 0.0
        self.last_source = ""

        self.root.title("PRTouch v2 Wave Viewer")
        self.root.geometry("1200x820")
        self.root.configure(background=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui(channels)
        self.receiver.start()
        self.root.after(REFRESH_MS, self.refresh)

    def _build_ui(self, channels: int) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Root.TFrame", background=BG_COLOR)
        style.configure("Main.TLabel", background=BG_COLOR, foreground=FG_COLOR)
        style.configure("Main.TFrame", background=BG_COLOR)

        container = ttk.Frame(self.root, style="Root.TFrame", padding=10)
        container.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(
            value=f"监听 {self.host}:{self.port} | 已收 0 包 | 来源 - | 最后更新 -"
        )
        status = ttk.Label(
            container,
            textvariable=self.status_var,
            style="Main.TLabel",
            font=("Segoe UI", 10),
        )
        status.pack(anchor="w", pady=(0, 8))

        self.wave_view = CombinedWaveFrame(container, channels=channels)
        self.wave_view.pack(fill="both", expand=True)

        hint = ttk.Label(
            container,
            style="Main.TLabel",
            text="提示：图中叠加显示 4 个通道，X 轴为最近 60 秒，Y 轴为传感器计数值。",
            font=("Segoe UI", 9),
        )
        hint.pack(anchor="w", pady=(8, 0))

    def refresh(self) -> None:
        while True:
            try:
                packet = self.packet_queue.get_nowait()
            except queue.Empty:
                break

            if not 0 <= packet.channel < len(self.channel_states):
                continue

            state = self.channel_states[packet.channel]
            state.append_samples(
                packet.samples,
                received_at=packet.received_at,
                sample_interval=self.sample_interval,
                history_seconds=self.history_seconds,
            )
            state.trigger = packet.trigger

            self.total_packets += 1
            self.last_packet_time = packet.received_at
            self.last_source = f"{packet.source[0]}:{packet.source[1]}"

        now = time.time()
        cutoff = now - self.history_seconds
        for state in self.channel_states:
            while state.samples and state.samples[0].timestamp < cutoff:
                state.samples.popleft()

        if self.wave_view is not None:
            self.wave_view.draw(self.channel_states, self.history_seconds)

        if self.last_packet_time > 0:
            age = time.time() - self.last_packet_time
            status = (
                f"监听 {self.host}:{self.port} | 已收 {self.total_packets} 包 | "
                f"来源 {self.last_source} | 最后更新 {age:.1f}s 前"
            )
        else:
            status = f"监听 {self.host}:{self.port} | 等待数据..."
        self.status_var.set(status)

        self.root.after(REFRESH_MS, self.refresh)

    def on_close(self) -> None:
        self.stop_event.set()
        self.receiver.close()
        self.root.destroy()


def main() -> None:
    args = parse_args()
    root = tk.Tk()
    ViewerApp(
        root,
        args.host,
        args.port,
        args.channels,
        args.history_seconds,
        args.sample_interval,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
