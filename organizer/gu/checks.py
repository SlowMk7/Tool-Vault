"""Checks on finished pieces: printer fit, minimum size and mesh validity."""

from __future__ import annotations

from pathlib import Path

import trimesh

from .spec import Printer


def fits_printer(size: tuple[float, float, float], printer: Printer) -> tuple[bool, bool]:
    """Return (fits, needs_rotation). Pieces print floor-down; 90° rotation allowed."""
    sx, sy, sz = size
    ux, uy, uz = printer.usable
    if sz > uz + 1e-6:
        return False, False
    if sx <= ux + 1e-6 and sy <= uy + 1e-6:
        return True, False
    if sy <= ux + 1e-6 and sx <= uy + 1e-6:
        return True, True
    return False, False


def mesh_check(stl_path: Path) -> dict:
    """Reload an exported STL and check it is a closed, single, printable solid."""
    m = trimesh.load(stl_path, force="mesh")
    bodies = m.split(only_watertight=False)
    lo, hi = m.bounds
    return {
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "separate_bodies": int(len(bodies)),
        "triangles": int(len(m.faces)),
        "volume_mm3": float(m.volume),
        "size_mm": [float(v) for v in (hi - lo)],
    }
