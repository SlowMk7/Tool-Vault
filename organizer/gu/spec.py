"""Reading and checking the design file (spec version 1).

The design file records what the customer asked for. It never contains
derived geometry; that is produced by layout.py. All lengths are converted
to millimetres here.

Unit rules:
  * "units" ("mm" or "in") applies to the drawer, organizer and layout
    sections. Any value there may also carry its own unit, e.g. "1mm".
  * "construction" and "printer" values are always millimetres (their keys
    end in _mm) because they are engineering settings.
"""

from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import Problems
from .printers import DEFAULT_MARGIN_MM, PRINTERS
from .units import normalise_units, to_mm

SPEC_VERSION = 1

TOP_KEYS = {"spec_version", "design_id", "revision", "name", "notes", "units", "drawer",
            "organizer", "construction", "layout", "seams", "printer"}
DRAWER_KEYS = {"width", "depth", "height", "corner_radius", "taper"}
TAPER_KEYS = {"top_width", "top_depth", "measured_at_height", "width_sides", "depth_sides", "angles_deg"}
ORGANIZER_KEYS = {"height", "fit_clearance"}
PRINTER_KEYS = {"profile", "name", "bed_width_mm", "bed_depth_mm", "max_height_mm", "margin_mm"}
SEAM_KEYS = {"between", "owner", "through", "note"}


@dataclass
class Construction:
    """Engineering settings (millimetres). Defaults are starting points to be
    confirmed by physical tests, not final values."""

    perimeter_wall_mm: float = 3.0
    divider_wall_mm: float = 3.0
    floor_mm: float = 1.6
    top_edge_radius_mm: float = 0.8
    bottom_chamfer_mm: float = 0.5
    seam_gap_mm: float = 0.15
    min_compartment_mm: float = 15.0
    min_open_gap_mm: float = 10.0
    min_section_mm: float = 40.0


@dataclass
class Taper:
    """Outward lean of each outside wall in degrees (0 = vertical)."""

    left: float = 0.0
    right: float = 0.0
    front: float = 0.0
    back: float = 0.0
    source: str = "none"   # none | top_dimensions | angles


@dataclass
class Printer:
    name: str
    bed_width_mm: float
    bed_depth_mm: float
    max_height_mm: float
    margin_mm: float = DEFAULT_MARGIN_MM

    @property
    def usable(self) -> tuple[float, float, float]:
        m = self.margin_mm
        return self.bed_width_mm - 2 * m, self.bed_depth_mm - 2 * m, self.max_height_mm


@dataclass
class SeamRequest:
    between: tuple[str, str]
    owner: str          # one of the two compartment ids, or "split"
    through: tuple[str, ...] = ()   # compartments this seam may cross (floor-only joint)


@dataclass
class Spec:
    design_id: str
    revision: int
    name: str
    units: str
    drawer_width: float
    drawer_depth: float
    drawer_height: float | None
    drawer_corner_radius: float
    taper: Taper
    organizer_height: float
    fit_clearance: float
    construction: Construction
    layout: dict            # raw layout section; lengths converted in layout.py
    seams: list[SeamRequest]
    printer: Printer
    spec_hash: str
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.design_id}-r{self.revision}"


def _check_keys(obj: dict, allowed: set[str], where: str, problems: Problems) -> None:
    for key in obj:
        if key not in allowed:
            close = difflib.get_close_matches(key, sorted(allowed), n=1)
            hint = f' Did you mean "{close[0]}"?' if close else ""
            problems.add(f'Unknown setting "{key}" in {where}.{hint}')


def _length(obj: dict, key: str, units: str, where: str, problems: Problems,
            required: bool = True, default: float | None = None, positive: bool = True) -> float | None:
    if key not in obj:
        if required:
            problems.add(f'{where} is missing "{key}".')
        return default
    try:
        mm = to_mm(obj[key], units)
    except ValueError as e:
        problems.add(f'{where} "{key}": {e}.')
        return default
    if positive and mm <= 0:
        problems.add(f'{where} "{key}" must be greater than zero (got {obj[key]!r}).')
        return default
    if not positive and mm < 0:
        problems.add(f'{where} "{key}" cannot be negative (got {obj[key]!r}).')
        return default
    return mm


def _number(obj: dict, key: str, where: str, problems: Problems, default: float) -> float:
    if key not in obj:
        return default
    v = obj[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        problems.add(f'{where} "{key}" must be a number in millimetres (got {v!r}).')
        return default
    if v < 0:
        problems.add(f'{where} "{key}" cannot be negative.')
        return default
    return float(v)


def canonical_hash(data: dict) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def load_spec(path: str | Path) -> Spec:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        from .errors import DesignError
        raise DesignError([f"{path.name} is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})."])
    return parse_spec(data)


def parse_spec(data: Any) -> Spec:
    p = Problems()
    if not isinstance(data, dict):
        p.add("The design file must be a JSON object.")
        p.raise_if_any()
    _check_keys(data, TOP_KEYS, "the design file", p)

    version = data.get("spec_version")
    if version != SPEC_VERSION:
        p.add(f"spec_version must be {SPEC_VERSION} (got {version!r}). This generator reads version {SPEC_VERSION} files.")

    design_id = str(data.get("design_id", "")).strip()
    if not design_id:
        p.add('The design file needs a "design_id", for example "GU-0101".')
    revision = data.get("revision", 1)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        p.add('"revision" must be a whole number of 1 or more.')
        revision = 1

    try:
        units = normalise_units(str(data.get("units", "mm")))
    except ValueError as e:
        p.add(f"{e}.")
        units = "mm"

    # --- drawer ---------------------------------------------------------------
    drawer = data.get("drawer")
    if not isinstance(drawer, dict):
        p.add('The design file needs a "drawer" section with at least width and depth.')
        drawer = {}
    _check_keys(drawer, DRAWER_KEYS, '"drawer"', p)
    dw = _length(drawer, "width", units, "drawer", p)
    dd = _length(drawer, "depth", units, "drawer", p)
    dh = _length(drawer, "height", units, "drawer", p, required=False)
    radius = _length(drawer, "corner_radius", units, "drawer", p, required=False, default=0.0, positive=False)
    taper = _parse_taper(drawer.get("taper"), units, dw, dd, dh, p)

    # --- organizer ------------------------------------------------------------
    org = data.get("organizer")
    if not isinstance(org, dict):
        p.add('The design file needs an "organizer" section with a "height".')
        org = {}
    _check_keys(org, ORGANIZER_KEYS, '"organizer"', p)
    oh = _length(org, "height", units, "organizer", p)
    clearance = _length(org, "fit_clearance", "mm" if "fit_clearance" not in org else units,
                        "organizer", p, required=False, default=1.0, positive=False)

    # --- construction ---------------------------------------------------------
    cons_raw = data.get("construction", {})
    if not isinstance(cons_raw, dict):
        p.add('"construction" must be a section of settings.')
        cons_raw = {}
    defaults = Construction()
    _check_keys(cons_raw, set(vars(defaults)), '"construction"', p)
    cons = Construction(**{k: _number(cons_raw, k, '"construction"', p, v) for k, v in vars(defaults).items()})
    for k in ("perimeter_wall_mm", "divider_wall_mm", "floor_mm"):
        if getattr(cons, k) <= 0:
            p.add(f'"construction" "{k}" must be greater than zero.')
    thinnest = min(cons.divider_wall_mm, cons.perimeter_wall_mm)
    max_radius = (thinnest - cons.seam_gap_mm) / 2 - 0.3
    if cons.top_edge_radius_mm > max(max_radius, 0):
        p.add(f"top_edge_radius_mm ({cons.top_edge_radius_mm}) is too large for {thinnest} mm walls; "
              f"use {max(max_radius, 0):.2f} mm or less so a wall split at a seam still has a flat top.")

    # --- layout and seams (detailed checks happen in layout.py / seams.py) ---
    layout = data.get("layout")
    if not isinstance(layout, dict):
        p.add('The design file needs a "layout" section describing the compartments.')
        layout = {}

    seams: list[SeamRequest] = []
    raw_seams = data.get("seams", [])
    if not isinstance(raw_seams, list):
        p.add('"seams" must be a list (use [] for a one-piece organizer).')
        raw_seams = []
    for i, s in enumerate(raw_seams, 1):
        where = f"seam {i}"
        if not isinstance(s, dict):
            p.add(f"{where} must be a section like {{\"between\": [\"A\", \"B\"], \"owner\": \"A\"}}.")
            continue
        _check_keys(s, SEAM_KEYS, where, p)
        between = s.get("between")
        if not (isinstance(between, list) and len(between) == 2 and all(isinstance(b, str) for b in between)):
            p.add(f'{where}: "between" must list exactly two compartment ids, e.g. ["forks", "knives"].')
            continue
        owner = s.get("owner", "split")
        if owner not in (between[0], between[1], "split"):
            p.add(f'{where}: "owner" must be "{between[0]}", "{between[1]}" or "split" (got {owner!r}).')
            continue
        through = s.get("through", [])
        if not (isinstance(through, list) and all(isinstance(t, str) for t in through)):
            p.add(f'{where}: "through" must be a list of compartment ids the seam may cross, e.g. ["drawer-front"].')
            continue
        seams.append(SeamRequest((between[0], between[1]), owner, tuple(through)))

    # --- printer ----------------------------------------------------------------
    printer = _parse_printer(data.get("printer"), p)

    # --- cross checks -----------------------------------------------------------
    if dh is not None and oh is not None and oh > dh + 1e-6:
        p.add(f"The organizer height ({oh:.1f} mm) is taller than the drawer ({dh:.1f} mm).")
    if dw is not None and dd is not None and clearance is not None:
        if dw - 2 * clearance - 2 * cons.perimeter_wall_mm <= 0 or dd - 2 * clearance - 2 * cons.perimeter_wall_mm <= 0:
            p.add("The drawer is too small for the walls and clearance.")
    if radius and dw and dd and radius * 2 >= min(dw, dd):
        p.add("The drawer corner radius is larger than half the drawer size.")

    p.raise_if_any()
    return Spec(
        design_id=design_id, revision=revision, name=str(data.get("name", "")), units=units,
        drawer_width=dw, drawer_depth=dd, drawer_height=dh, drawer_corner_radius=radius or 0.0,
        taper=taper, organizer_height=oh, fit_clearance=clearance, construction=cons,
        layout=layout, seams=seams, printer=printer, spec_hash=canonical_hash(data), raw=data,
    )


def _parse_taper(raw: Any, units: str, dw, dd, dh, p: Problems) -> Taper:
    import math

    if raw is None:
        return Taper()
    if not isinstance(raw, dict):
        p.add('"taper" must be a section, e.g. {"top_width": "12 1/2", "measured_at_height": "3 1/2"}.')
        return Taper()
    _check_keys(raw, TAPER_KEYS, '"drawer" "taper"', p)
    if "angles_deg" in raw:
        if any(k in raw for k in ("top_width", "top_depth")):
            p.add('Use either "angles_deg" or top measurements in "taper", not both.')
        angles = raw["angles_deg"]
        if not isinstance(angles, dict):
            p.add('"angles_deg" must look like {"left": 4, "right": 4, "front": 0, "back": 0}.')
            return Taper()
        _check_keys(angles, {"left", "right", "front", "back"}, '"angles_deg"', p)
        t = Taper(source="angles")
        for side in ("left", "right", "front", "back"):
            v = angles.get(side, 0)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                p.add(f'"angles_deg" "{side}" must be a number of degrees.')
                continue
            setattr(t, side, float(v))
    else:
        h = _length(raw, "measured_at_height", units, '"taper"', p, required=False)
        if h is None:
            h = dh
        if h is None:
            p.add('"taper" needs "measured_at_height" (or the drawer "height") to work out the wall angle.')
            return Taper()
        t = Taper(source="top_dimensions")
        for axis, base, key, sides_key, sides in (
            ("width", dw, "top_width", "width_sides", ("left", "right")),
            ("depth", dd, "top_depth", "depth_sides", ("front", "back")),
        ):
            if key not in raw or base is None:
                continue
            top = _length(raw, key, units, '"taper"', p)
            if top is None:
                continue
            diff = top - base
            if diff < -1e-6:
                p.add(f"The drawer is narrower at the top ({top:.1f} mm) than at the floor ({base:.1f} mm) "
                      f"across its {axis}. Re-measure: an organizer cannot be inserted past a narrower top.")
                continue
            which = raw.get(sides_key, "both")
            if which == "both":
                per = {sides[0]: diff / 2, sides[1]: diff / 2}
            elif which in sides:
                per = {which: diff}
            else:
                p.add(f'"{sides_key}" must be "both", "{sides[0]}" or "{sides[1]}".')
                continue
            for side, offset in per.items():
                setattr(t, side, math.degrees(math.atan2(offset, h)))
    for side in ("left", "right", "front", "back"):
        a = getattr(t, side)
        if a < 0:
            p.add(f"The {side} wall angle is negative ({a:.1f}°). Only outward-leaning walls are supported.")
        elif a > 20:
            p.add(f"The {side} wall angle ({a:.1f}°) is over the 20° limit. Please re-check the measurements.")
    return t


def _parse_printer(raw: Any, p: Problems) -> Printer:
    if raw is None:
        raw = {"profile": "bambu-p1s"}
    if not isinstance(raw, dict):
        p.add('"printer" must be a section, e.g. {"profile": "bambu-p1s"}.')
        raw = {"profile": "bambu-p1s"}
    _check_keys(raw, PRINTER_KEYS, '"printer"', p)
    base: dict = {}
    if "profile" in raw:
        prof = raw["profile"]
        if prof not in PRINTERS:
            close = difflib.get_close_matches(str(prof), list(PRINTERS), n=1)
            hint = f' Did you mean "{close[0]}"?' if close else ""
            p.add(f'Unknown printer profile "{prof}".{hint} Known: {", ".join(PRINTERS)}. '
                  "Or enter bed_width_mm, bed_depth_mm and max_height_mm yourself.")
        else:
            base = dict(PRINTERS[prof])
    base.update({k: v for k, v in raw.items() if k != "profile"})
    missing = [k for k in ("bed_width_mm", "bed_depth_mm", "max_height_mm") if k not in base]
    if missing:
        p.add(f'"printer" is missing {", ".join(missing)} (or choose a "profile").')
        return Printer("unknown", 256, 256, 256)
    vals = {}
    for k in ("bed_width_mm", "bed_depth_mm", "max_height_mm", "margin_mm"):
        v = base.get(k, DEFAULT_MARGIN_MM)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            p.add(f'"printer" "{k}" must be a positive number of millimetres.')
            v = DEFAULT_MARGIN_MM
        vals[k] = float(v)
    return Printer(name=str(base.get("name", "custom printer")), **vals)
