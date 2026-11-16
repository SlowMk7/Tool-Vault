"""Turn the seam list into printable section regions.

How seams work (version 1):
  * Each seam names two compartments that share a divider wall.
  * The seam splits whichever current section contains both compartments,
    running straight across that section only. Seams applied one after
    another therefore give region-by-region (stepped) seam paths.
  * "owner" decides who keeps the divider:
        owner = one compartment id -> that side keeps the whole wall,
                                      the other side is open floor at the seam.
        owner = "split"            -> each side keeps half the wall.
  * A small seam gap (construction.seam_gap_mm) is removed at every seam so
    printed parts that come out slightly oversize still fit together.

Sections are axis-aligned rectangles in this version, stored as regions in
interior coordinates (infinite where they run out through the perimeter).
An automatic planner can later produce the same region list.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .errors import Problems
from .layout import TOL, Compartment, Resolved
from .spec import SeamRequest

INF = math.inf


@dataclass
class Region:
    x0: float = -INF
    x1: float = INF
    y0: float = -INF
    y1: float = INF

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def as_dict(self) -> dict:
        f = lambda v: None if math.isinf(v) else round(v, 3)  # noqa: E731
        return {"x0": f(self.x0), "x1": f(self.x1), "y0": f(self.y0), "y1": f(self.y1)}


@dataclass
class SeamDetail:
    between: tuple[str, str]
    owner: str
    axis: str            # "x" = the seam line runs front-to-back at a fixed x
    line: float          # seam position (interior coordinates)
    wall_from: float     # divider faces
    wall_to: float
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"between": list(self.between), "owner": self.owner,
                "seam_line": f"{'x' if self.axis == 'x' else 'y'} = {self.line:.2f} mm (interior)",
                "divider_from_mm": round(self.wall_from, 3), "divider_to_mm": round(self.wall_to, 3)}


@dataclass
class Section:
    name: str
    region: Region
    compartments: list[str]


def plan_sections(res: Resolved, seams: list[SeamRequest]) -> tuple[list[Section], list[SeamDetail], list[str]]:
    p = Problems()
    warnings: list[str] = []
    t = res.divider
    gap = res.spec.construction.seam_gap_mm
    regions: list[Region] = [Region()]
    details: list[SeamDetail] = []

    for n, seam in enumerate(seams, 1):
        a, b = (res.by_id(i) for i in seam.between)
        missing = [i for i, c in zip(seam.between, (a, b)) if c is None]
        if missing:
            p.add(f"Seam {n}: no compartment called {', '.join(repr(m) for m in missing)}.")
            continue
        found = _shared_wall(a, b, t)
        if found is None:
            p.add(f'Seam {n}: "{a.id}" and "{b.id}" do not share a divider wall, so there is no wall to put the '
                  "seam on. Choose two compartments directly next to each other.")
            continue
        axis, low, high = found
        if axis == "x":
            p_face, q_face = low.x1, high.x0
        else:
            p_face, q_face = low.y1, high.y0

        if seam.owner == low.id:
            line, cut_low, cut_high = q_face, q_face, q_face + gap
        elif seam.owner == high.id:
            line, cut_low, cut_high = p_face, p_face - gap, p_face
        else:
            mid = (p_face + q_face) / 2
            line, cut_low, cut_high = mid, mid - gap / 2, mid + gap / 2

        region = next((r for r in regions if r.contains(*a.centre) and r.contains(*b.centre)), None)
        if region is None:
            p.add(f'Seam {n}: "{a.id}" and "{b.id}" are already in different sections because of an earlier seam.')
            continue

        crossings = _crossings(res, region, axis, line, exclude=())
        if crossings:
            names = ", ".join(f'"{c.id}"' for c in crossings)
            p.add(f'Seam {n} (between "{a.id}" and "{b.id}") would cut through compartment {names}. '
                  "Seams must follow divider walls. Add a divider in line with this seam, or split the section "
                  "along a different wall first so this seam only crosses the part that has a wall.")
            continue

        detail = SeamDetail((a.id, b.id), seam.owner, axis, line, p_face, q_face)
        open_len = _open_floor_length(res, region, axis, line)
        if open_len > 1.0:
            detail.warnings.append(
                f'Seam {n} (between "{a.id}" and "{b.id}") crosses {open_len:.0f} mm of open floor with no wall. '
                "That part of the joint is floor-only and weaker; check it in a test print.")
        details.append(detail)
        warnings.extend(detail.warnings)

        regions.remove(region)
        if axis == "x":
            regions += [Region(region.x0, cut_low, region.y0, region.y1),
                        Region(cut_high, region.x1, region.y0, region.y1)]
        else:
            regions += [Region(region.x0, region.x1, region.y0, cut_low),
                        Region(region.x0, region.x1, cut_high, region.y1)]

    p.raise_if_any()

    regions.sort(key=lambda r: (r.y0, r.x0))
    sections = []
    total = len(regions)
    for i, r in enumerate(regions, 1):
        inside = [c.id for c in res.compartments if r.contains(*c.centre)]
        sections.append(Section(f"P{i}-of-{total}", r, inside))
    return sections, details, warnings


def _shared_wall(a: Compartment, b: Compartment, t: float):
    """Return (axis, low, high) if a and b share one divider, else None."""
    oy = min(a.y1, b.y1) - max(a.y0, b.y0)
    ox = min(a.x1, b.x1) - max(a.x0, b.x0)
    if oy > TOL:
        if abs(b.x0 - a.x1 - t) <= TOL:
            return "x", a, b
        if abs(a.x0 - b.x1 - t) <= TOL:
            return "x", b, a
    if ox > TOL:
        if abs(b.y0 - a.y1 - t) <= TOL:
            return "y", a, b
        if abs(a.y0 - b.y1 - t) <= TOL:
            return "y", b, a
    return None


def _span(region: Region, axis: str, res: Resolved) -> tuple[float, float]:
    """The part of the seam line that lies inside the organizer interior."""
    if axis == "x":
        return max(region.y0, 0.0), min(region.y1, res.interior_depth)
    return max(region.x0, 0.0), min(region.x1, res.interior_width)


def _crossings(res: Resolved, region: Region, axis: str, line: float, exclude) -> list[Compartment]:
    lo, hi = _span(region, axis, res)
    out = []
    for c in res.compartments:
        if c.id in exclude:
            continue
        if axis == "x":
            along_lo, along_hi, across_lo, across_hi = c.y0, c.y1, c.x0, c.x1
        else:
            along_lo, along_hi, across_lo, across_hi = c.x0, c.x1, c.y0, c.y1
        if min(along_hi, hi) - max(along_lo, lo) > TOL and across_lo + TOL < line < across_hi - TOL:
            out.append(c)
    return out


def _open_floor_length(res: Resolved, region: Region, axis: str, line: float) -> float:
    """Length of the seam line (inside the interior) not running along any wall."""
    lo, hi = _span(region, axis, res)
    t = res.divider
    covered: list[tuple[float, float]] = []
    for c in res.compartments:
        flush = res.flush(c)
        if axis == "x":
            faces = (c.x0, c.x1)
            a_lo = c.y0 - (0 if flush["front"] else t)
            a_hi = c.y1 + (0 if flush["back"] else t)
            near = (faces[0] - t - TOL <= line <= faces[0] + TOL) or (faces[1] - TOL <= line <= faces[1] + t + TOL)
        else:
            faces = (c.y0, c.y1)
            a_lo = c.x0 - (0 if flush["left"] else t)
            a_hi = c.x1 + (0 if flush["right"] else t)
            near = (faces[0] - t - TOL <= line <= faces[0] + TOL) or (faces[1] - TOL <= line <= faces[1] + t + TOL)
        if near:
            covered.append((max(a_lo, lo), min(a_hi, hi)))
    covered = sorted(iv for iv in covered if iv[1] > iv[0])
    total, cursor = 0.0, lo
    for s, e in covered:
        if s > cursor:
            total += s - cursor
        cursor = max(cursor, e)
    if hi > cursor:
        total += hi - cursor
    return total
