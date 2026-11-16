"""Built-in printer profiles.

Sizes are the manufacturers' advertised build volumes in millimetres. The
usable area is reduced by `margin_mm` on every side (default 2 mm, because
the owner prefers to use the bed fully). Verify a profile with a real print
before relying on it near the limit. Any printer can also be entered by hand
in the design file.
"""

from __future__ import annotations

PRINTERS: dict[str, dict] = {
    "bambu-h2s": {"name": "Bambu Lab H2S", "bed_width_mm": 340, "bed_depth_mm": 320, "max_height_mm": 340},
    "bambu-h2d": {"name": "Bambu Lab H2D (one nozzle)", "bed_width_mm": 325, "bed_depth_mm": 320, "max_height_mm": 325},
    "bambu-a1-mini": {"name": "Bambu Lab A1 mini", "bed_width_mm": 180, "bed_depth_mm": 180, "max_height_mm": 180},
    "bambu-a1": {"name": "Bambu Lab A1", "bed_width_mm": 256, "bed_depth_mm": 256, "max_height_mm": 256},
    "bambu-p1s": {"name": "Bambu Lab P1S", "bed_width_mm": 256, "bed_depth_mm": 256, "max_height_mm": 256},
    "bambu-p1p": {"name": "Bambu Lab P1P", "bed_width_mm": 256, "bed_depth_mm": 256, "max_height_mm": 256},
    "bambu-x1c": {"name": "Bambu Lab X1 Carbon", "bed_width_mm": 256, "bed_depth_mm": 256, "max_height_mm": 256},
    "prusa-mk4": {"name": "Prusa MK4", "bed_width_mm": 250, "bed_depth_mm": 210, "max_height_mm": 220},
    "prusa-core-one": {"name": "Prusa CORE One", "bed_width_mm": 250, "bed_depth_mm": 220, "max_height_mm": 270},
}

DEFAULT_MARGIN_MM = 2.0
