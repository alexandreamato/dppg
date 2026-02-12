"""Matplotlib chart rendering for PDF reports (Agg backend -> PNG in memory)."""

import io
from typing import List, Tuple, Dict, Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from ..config import ESTIMATED_SAMPLING_RATE, ADC_TO_PPG_FACTOR, LABEL_DESCRIPTIONS
from ..models import PPGBlock, PPGParameters
from ..analysis import calculate_parameters


def render_ppg_chart(block: PPGBlock, width_inches=3.0, height_inches=1.8, dpi=150,
                     point_number: int = None, point_color: str = None) -> bytes:
    """Render a single PPG channel chart as PNG bytes.

    Shows the PPG curve in %PPG with peak and endpoint markers,
    matching the VASOSCREEN report style.

    Args:
        point_number: Optional number (1-4) matching diagnostic scatter chart dot.
        point_color: Optional color matching diagnostic scatter chart dot.
    """
    params = calculate_parameters(block)
    samples = np.array(block.samples, dtype=float)

    if len(samples) < 10:
        return _empty_chart(width_inches, height_inches, dpi)

    # Convert to %PPG
    baseline = params.baseline_value if params else float(np.median(samples[:10]))
    ppg = (samples - baseline) / ADC_TO_PPG_FACTOR

    sr = ESTIMATED_SAMPLING_RATE
    peak_idx = params.peak_index if params else int(np.argmax(samples))

    # Time axis relative to peak (peak = 0)
    time_axis = (np.arange(len(samples)) - peak_idx) / sr

    fig, ax = plt.subplots(figsize=(width_inches, height_inches), dpi=dpi)

    # Plot PPG curve
    ax.plot(time_axis, ppg, color='red', linewidth=1.0)

    # Y axis range like VASOSCREEN: -2 to 8 %PPG (or wider if needed)
    y_min = min(-2, np.min(ppg) - 0.5)
    y_max = max(8, np.max(ppg) + 0.5)
    ax.set_ylim(y_min, y_max)

    # Markers
    if params:
        # Peak marker (X)
        peak_t = 0
        peak_ppg = ppg[params.peak_index]
        ax.plot(peak_t, peak_ppg, 'rx', markersize=8, markeredgewidth=2)

        # Endpoint marker (X)
        end_idx = min(params.To_end_index, len(samples) - 1)
        end_t = (end_idx - peak_idx) / sr
        end_ppg = ppg[end_idx]
        ax.plot(end_t, end_ppg, 'rx', markersize=8, markeredgewidth=2)

    # Label
    label_desc = block.label_desc
    exam_str = f" #{block.exam_number}" if block.exam_number else ""
    ax.text(0.02, 0.95, f"{label_desc}{exam_str}",
            transform=ax.transAxes, fontsize=8, color='darkcyan',
            verticalalignment='top', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='lightyellow', alpha=0.8))

    # Point indicator matching diagnostic scatter chart
    if point_number is not None and point_color:
        ax.plot(0.96, 0.95, 'o', color=point_color, markersize=12,
                markeredgecolor='black', markeredgewidth=0.8,
                transform=ax.transAxes, zorder=10, clip_on=False)
        ax.text(0.96, 0.95, str(point_number),
                transform=ax.transAxes, fontsize=8, fontweight='bold',
                color='white', ha='center', va='center', zorder=11)

    # Axis labels
    ax.set_xlabel("s", fontsize=7)
    ax.set_ylabel("%PPG", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linewidth=0.5, linestyle='--')

    fig.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_diagnostic_chart(points: List[Tuple[float, float, str]],
                            width_inches=3.5, height_inches=2.5, dpi=150) -> bytes:
    """Render the Vo% x To diagnostic scatter chart as PNG bytes.

    Args:
        points: list of (To, Vo, label) tuples
    """
    fig, ax = plt.subplots(figsize=(width_inches, height_inches), dpi=dpi)

    max_to = 50
    max_vo = 15

    # Zone backgrounds
    # Green (normal) - full background
    ax.axvspan(24, max_to, ymin=0, ymax=1, color='#ccffcc', zorder=0)

    # Yellow (borderline) - To 20-24
    ax.axvspan(20, 24, ymin=2/max_vo, ymax=1, color='#ffffcc', zorder=1)

    # Yellow triangle: (24,4)-(50,2)-(24,2)
    triangle = MplPolygon(
        [[24, 4], [50, 2], [24, 2]],
        closed=True, facecolor='#ffffcc', edgecolor='none', zorder=1
    )
    ax.add_patch(triangle)

    # Red (abnormal) - To <= 20
    ax.axvspan(0, 20, color='#ffcccc', zorder=2)

    # Red - Vo <= 2 (bottom strip, right of To=20)
    ax.fill_between([20, max_to], [0, 0], [2, 2], color='#ffcccc', zorder=2)

    # Border lines
    ax.axvline(x=20, color='#cc0000', linewidth=0.8, zorder=3)
    ax.axvline(x=24, color='#cccc00', linewidth=0.8, ymin=2/max_vo, zorder=3)
    ax.axhline(y=2, color='#cc0000', linewidth=0.8, xmin=20/max_to, zorder=3)
    ax.plot([24, 50], [4, 2], color='#cccc00', linewidth=0.8, zorder=3)

    # Zone labels
    ax.text(10, 12, "abnormal", ha='center', fontsize=7, color='red', zorder=4)
    ax.text(38, 12, "normal", ha='center', fontsize=7, color='green', zorder=4)
    ax.text(30, 3, "Border line", ha='center', fontsize=6, color='#999900', zorder=4)

    # Data points
    colors = ['blue', 'red', 'green', 'orange']
    for i, (to_val, vo_val, label) in enumerate(points):
        color = colors[i % len(colors)]
        ax.plot(to_val, vo_val, 'o', color=color, markersize=7,
                markeredgecolor='black', markeredgewidth=0.5, zorder=5)
        ax.annotate(str(i + 1), (to_val, vo_val), textcoords="offset points",
                    xytext=(6, 6), fontsize=7, fontweight='bold', color=color, zorder=5)

    ax.set_xlim(0, max_to)
    ax.set_ylim(0, max_vo)
    ax.set_xlabel("To s", fontsize=8)
    ax.set_ylabel("Vo%", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_xticks([0, 25, 50])
    ax.set_yticks([0, 5, 10, 15])

    fig.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _empty_chart(w, h, dpi):
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    ax.text(0.5, 0.5, "Sem dados", ha='center', va='center', fontsize=10, color='gray')
    ax.set_xticks([])
    ax.set_yticks([])
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
