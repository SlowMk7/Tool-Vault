"""Stage 0 geometry feasibility test.

Builds one small sample organizer (120 x 80 mm footprint, 40 mm tall) that
contains every risky feature the real generator needs:

  1. Tapered outside walls (10 degrees on the left and right sides).
  2. Rounded outside corners (6 mm radius) on a tapered wall.
  3. A shared divider wall between two compartments.
  4. Rounded top wall edges (fillet) and a small bottom chamfer.
  5. A seam that splits the organizer into two printable pieces, built two
     ways: "owner" (one piece keeps the whole divider) and "split" (each
     piece keeps half of the divider).

Every result is measured, not assumed: STL meshes are reloaded and checked
for closed (watertight) geometry, wall thicknesses are measured by ray
casting, and piece volumes are compared with the whole organizer.

Run:  .venv/bin/python organizer/stage0/feasibility.py
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import trimesh
from build123d import (
    Axis,
    Box,
    Plane,
    Pos,
    RectangleRounded,
    Rectangle,
    chamfer,
    export_stl,
    extrude,
    fillet,
    loft,
)

OUT = Path(__file__).parent / "output"

# --- sample parameters (example values, not the owner's drawer) ---------------
W, D, H = 120.0, 80.0, 40.0        # outer footprint at the floor, organizer height
TAPER_DEG = 10.0                   # left and right walls lean outward
R_CORNER = 6.0                     # outside corner radius
T_PERIM = 3.0                      # perimeter wall thickness (horizontal)
T_DIV = 3.0                        # divider thickness
FLOOR = 1.6
TOP_FILLET = 0.8
BOTTOM_CHAMFER = 0.5
SEAM_GAP = 0.15

tan = math.tan(math.radians(TAPER_DEG))


def rounded_slab(w: float, d: float, r: float, z: float, cx: float, cy: float):
    """A flat rounded rectangle at height z, centred at (cx, cy)."""
    return Plane.XY.offset(z) * Pos(cx, cy) * RectangleRounded(w, d, r)


def build_whole():
    t0 = time.time()
    grow = H * tan  # how far each tapered side moves outward at the top
    outer = loft(
        [
            rounded_slab(W, D, R_CORNER, 0, W / 2, D / 2),
            rounded_slab(W + 2 * grow, D, R_CORNER, H, W / 2, D / 2),
        ],
        ruled=True,
    )
    outer = chamfer(outer.edges().group_by(Axis.Z)[0], BOTTOM_CHAMFER)

    # Interior cavity: inset by the perimeter thickness, from floor to above top.
    z0, z1 = FLOOR, H + 1.0
    inner_r = max(R_CORNER - T_PERIM, 0.5)
    cavity = loft(
        [
            rounded_slab(W - 2 * T_PERIM + 2 * z0 * tan, D - 2 * T_PERIM, inner_r, z0, W / 2, D / 2),
            rounded_slab(W - 2 * T_PERIM + 2 * z1 * tan, D - 2 * T_PERIM, inner_r, z1, W / 2, D / 2),
        ],
        ruled=True,
    )
    shell = outer - cavity

    # Divider: a slab through the middle, deliberately overlapping the
    # perimeter (never just touching it), then clipped by the outer body.
    divider = Pos(W / 2, D / 2, H / 2) * Box(T_DIV, D + 20, H)
    divider = divider & outer
    body = shell + divider

    top_edges = body.edges().group_by(Axis.Z)[-1]
    body = fillet(top_edges, TOP_FILLET)
    return body, time.time() - t0, len(top_edges)


def region_box(x0: float, x1: float):
    big = 1000.0
    return Pos((x0 + x1) / 2, D / 2, H / 2) * Box(x1 - x0, D + big, H + 10)


def cut_sections(body, mode: str):
    """Split the body along the divider. Returns (left, right)."""
    p = W / 2 - T_DIV / 2   # left face of divider
    q = W / 2 + T_DIV / 2   # right face of divider
    far = 500.0
    if mode == "owner":     # left piece owns the whole divider
        left_x1, right_x0 = q, q + SEAM_GAP
    elif mode == "split":   # each piece gets half the divider
        mid = (p + q) / 2
        left_x1, right_x0 = mid - SEAM_GAP / 2, mid + SEAM_GAP / 2
    else:
        raise ValueError(mode)
    left = body & region_box(-far, left_x1)
    right = body & region_box(right_x0, far)
    return left, right


def mesh_report(path: Path) -> dict:
    m = trimesh.load(path, force="mesh")
    bodies = m.split(only_watertight=False)
    lo, hi = m.bounds
    return {
        "file": path.name,
        "triangles": int(len(m.faces)),
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "separate_bodies": int(len(bodies)),
        "volume_mm3": round(float(m.volume), 1),
        "size_mm": [round(float(v), 2) for v in (hi - lo)],
    }


def ray_walls(path: Path, y: float, z: float) -> list[float]:
    """Cast a ray along +X and return the thickness of each solid run crossed."""
    m = trimesh.load(path, force="mesh")
    origin = np.array([[-50.0, y, z]])
    hits, _, _ = m.ray.intersects_location(origin, np.array([[1.0, 0, 0]]), multiple_hits=True)
    xs = sorted(set(round(float(h[0]), 4) for h in hits))
    return [round(xs[i + 1] - xs[i], 3) for i in range(0, len(xs) - 1, 2)]


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {"parameters": {
        "outer_floor_mm": [W, D], "height_mm": H, "taper_deg_left_right": TAPER_DEG,
        "corner_radius_mm": R_CORNER, "perimeter_wall_mm": T_PERIM, "divider_mm": T_DIV,
        "floor_mm": FLOOR, "top_fillet_mm": TOP_FILLET, "bottom_chamfer_mm": BOTTOM_CHAMFER,
        "seam_gap_mm": SEAM_GAP}}

    body, secs, n_top = build_whole()
    results["whole"] = {
        "build_seconds": round(secs, 2), "occt_valid": body.is_valid,
        "top_edges_filleted": n_top, "volume_mm3": round(body.volume, 1)}
    whole_stl = OUT / "whole.stl"
    export_stl(body, whole_stl, tolerance=0.01, angular_tolerance=0.1)
    results["whole"]["mesh"] = mesh_report(whole_stl)

    # Measured geometry checks.
    expected_top_w = W + 2 * H * tan
    mid_z = H / 2
    expected_mid_w = W + 2 * mid_z * tan
    walls = ray_walls(whole_stl, D / 2, mid_z)
    results["whole"]["measured"] = {
        "top_width_expected_mm": round(expected_top_w, 2),
        "walls_crossed_at_mid_height_mm": walls,
        "expected_walls_mm": [T_PERIM, T_DIV, T_PERIM],
        "outer_width_at_mid_height_expected_mm": round(expected_mid_w, 2),
    }
    # Outer width at mid height from the ray hits.
    m = trimesh.load(whole_stl, force="mesh")
    hits, _, _ = m.ray.intersects_location(np.array([[-50.0, D / 2, mid_z]]), np.array([[1.0, 0, 0]]), multiple_hits=True)
    xs = sorted(float(h[0]) for h in hits)
    results["whole"]["measured"]["outer_width_at_mid_height_mm"] = round(xs[-1] - xs[0], 3)

    for mode in ("owner", "split"):
        t0 = time.time()
        left, right = cut_sections(body, mode)
        entry: dict = {"cut_seconds": round(time.time() - t0, 2)}
        for name, piece in (("left", left), ("right", right)):
            p = OUT / f"seam_{mode}_{name}.stl"
            export_stl(piece, p, tolerance=0.01, angular_tolerance=0.1)
            entry[name] = mesh_report(p)
            entry[name]["occt_valid"] = piece.is_valid
            entry[name]["walls_crossed_at_mid_height_mm"] = ray_walls(p, D / 2, mid_z)
        removed = body.volume - left.volume - right.volume
        entry["volume_removed_by_seam_gap_mm3"] = round(removed, 2)
        results[f"seam_{mode}"] = entry

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
