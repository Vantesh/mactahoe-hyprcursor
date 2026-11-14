"""Complete upstream's spinner animations into a full loop.

Upstream's scalable/<name>/metadata.json lists only wait.svg + wait-01..12
(and the same for progress): half a turn of the 24-step, 15-degree
pinwheel, so the cursor jumps back to the start mid-rotation. Its X cursor
configs list wait-01..23 without the base frame, which leaves one 30-degree
step at the loop seam. The artwork contains the complete turn: numbered
frames 01..N plus the base frame <name>.svg, which fills the missing step.
"""

from __future__ import annotations

import re
from pathlib import Path


def complete_loop(name: str, metadata: list[dict], svg_dir: Path) -> list[dict]:
    """Return metadata with the full loop: numbered frames in order, then the
    base frame. Single-frame cursors are returned unchanged."""
    if len(metadata) < 2:
        return metadata

    pattern = re.compile(rf"^{re.escape(name)}-(\d+)\.svg$")
    numbered = sorted(
        (int(match.group(1)), path.name)
        for path in svg_dir.glob(f"{name}-*.svg")
        if (match := pattern.match(path.name))
    )
    numbers = [number for number, _ in numbered]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"{name}: numbered frames are not contiguous from 01: {numbers}")

    frames = [filename for _, filename in numbered] + [f"{name}.svg"]
    missing = {frame["filename"] for frame in metadata} - set(frames)
    if missing:
        raise ValueError(f"{name}: metadata frames not in the loop: {sorted(missing)}")

    template = metadata[0]  # hotspot, nominal size and delay are shared by all frames
    return [{**template, "filename": filename} for filename in frames]
