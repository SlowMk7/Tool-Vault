"""Run the whole pipeline: design file -> checked STL sections + report."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from build123d import export_stl

from . import __version__
from .checks import fits_printer, mesh_check
from .errors import DesignError, Problems
from .geometry import build_organizer, cut_section
from .layout import Resolved, resolve
from .report import layout_svg
from .seams import plan_sections
from .spec import Spec, load_spec

PLA_DENSITY = 1.24  # g/cm³
STL_TOLERANCE = 0.02  # mm
STL_ANGULAR = 0.15    # radians


@dataclass
class Result:
    out_dir: Path
    files: list[Path] = field(default_factory=list)
    report: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def generator_version() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=Path(__file__).parent, timeout=5).stdout.strip()
    except Exception:
        sha = ""
    return f"{__version__}+{sha}" if sha else __version__


def check_design(path: str | Path) -> tuple[Spec, Resolved, list, list, list[str]]:
    """Everything except 3D geometry: fast feedback on a design file."""
    spec = load_spec(path)
    res = resolve(spec)
    sections, seams, seam_warnings = plan_sections(res, spec.seams)
    _precheck_printer(res)
    return spec, res, sections, seams, res.warnings + seam_warnings


def _precheck_printer(res: Resolved) -> None:
    """Catch compartments that can never fit the printer, before building anything."""
    p = Problems()
    ux, uy, _ = res.spec.printer.usable
    t = res.divider
    for c in res.compartments:
        if c.id in res.floor_seam_compartments:
            continue  # a floor seam splits it; the section check below is definitive
        need = (c.width + 2 * t, c.depth + 2 * t)
        if not (need[0] <= ux and need[1] <= uy) and not (need[1] <= ux and need[0] <= uy):
            p.add(f'Compartment "{c.id}" ({c.width:.0f} × {c.depth:.0f} mm plus walls) is larger than the '
                  f"usable bed of the {res.spec.printer.name} ({ux:.0f} × {uy:.0f} mm), so no seam along walls "
                  "can make it printable. Add a divider through it, let a seam cross its floor "
                  '(list it in that seam\'s "through"), or choose a larger printer.')
    p.raise_if_any()


def generate(path: str | Path, out_root: str | Path = "output", preview: bool = False) -> Result:
    spec, res, sections, seams, warnings = check_design(path)
    out_dir = Path(out_root) / spec.label
    out_dir.mkdir(parents=True, exist_ok=True)
    result = Result(out_dir=out_dir, warnings=list(warnings))

    body, geo_warnings = build_organizer(res)
    result.warnings += geo_warnings
    if not body.is_valid:
        raise DesignError(["The 3D geometry engine produced an invalid solid for this design. "
                           "This is a generator problem, not a design mistake; please report it with the design file."])

    p = Problems()
    pieces = []
    cons = spec.construction
    for s in sections:
        piece = cut_section(body, res, s.region) if len(sections) > 1 else body
        solids = piece.solids()
        bb = piece.bounding_box()
        size = (bb.size.X, bb.size.Y, bb.size.Z)
        fits, rotate = fits_printer(size, spec.printer)
        if len(solids) != 1:
            p.add(f"Section {s.name} came out as {len(solids)} separate pieces. Move the seam so each section "
                  "is one connected piece.")
        if not piece.is_valid:
            p.add(f"Section {s.name} is not a valid solid (generator problem; please report it).")
        if not fits:
            ux, uy, uz = spec.printer.usable
            p.add(f"Section {s.name} is {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} mm, which does not fit the "
                  f"usable area of the {spec.printer.name} ({ux:.0f} × {uy:.0f} × {uz:.0f} mm). "
                  "Add a seam to split it further.")
        if min(size[0], size[1]) < cons.min_section_mm:
            p.add(f"Section {s.name} is only {min(size[0], size[1]):.1f} mm across; the minimum is "
                  f"{cons.min_section_mm:.0f} mm. Move or remove a seam so no section is that narrow.")
        pieces.append((s, piece, size, rotate))
    p.raise_if_any()

    # Export and verify every file by reading it back.
    section_reports = []
    total_volume = 0.0
    for s, piece, size, rotate in pieces:
        stl = out_dir / f"{spec.label}_{s.name}.stl"
        export_stl(piece, stl, tolerance=STL_TOLERANCE, angular_tolerance=STL_ANGULAR)
        mesh = mesh_check(stl)
        problems = []
        if not mesh["watertight"] or not mesh["winding_consistent"]:
            problems.append("mesh is not closed")
        if mesh["separate_bodies"] != 1:
            problems.append(f"mesh has {mesh['separate_bodies']} bodies")
        vol_err = abs(mesh["volume_mm3"] - piece.volume) / piece.volume
        if vol_err > 0.005:
            problems.append(f"mesh volume differs from CAD volume by {vol_err:.1%}")
        if problems:
            raise DesignError([f"Exported file {stl.name} failed its check: {', '.join(problems)}."])
        total_volume += piece.volume
        result.files.append(stl)
        section_reports.append({
            "section": s.name,
            "file": stl.name,
            "compartments": s.compartments,
            "size_mm": [round(v, 2) for v in size],
            "fits_printer": True,
            "rotate_90_on_bed": rotate,
            "volume_cm3": round(piece.volume / 1000, 2),
            "solid_weight_pla_g": round(piece.volume / 1000 * PLA_DENSITY, 1),
            "mesh": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in mesh.items()
                     if k != "size_mm"},
            "region_interior_mm": s.region.as_dict(),
        })

    assembly = out_dir / f"{spec.label}_assembly-preview.stl"
    export_stl(body, assembly, tolerance=STL_TOLERANCE, angular_tolerance=STL_ANGULAR)
    result.files.append(assembly)

    svg = out_dir / f"{spec.label}_layout.svg"
    svg.write_text(layout_svg(res, sections))
    result.files.append(svg)

    bb = body.bounding_box()
    result.report = {
        "design": {"design_id": spec.design_id, "revision": spec.revision, "name": spec.name,
                   "spec_sha256": spec.spec_hash, "units_in_file": spec.units},
        "generator_version": generator_version(),
        "status": {"geometry_checks": "passed",
                   "physical_verification": "NOT VERIFIED - print and test before selling"},
        "resolved": {
            "outside_at_floor_mm": [round(res.outer_width, 2), round(res.outer_depth, 2)],
            "outside_overall_mm": [round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)],
            "interior_at_floor_mm": [round(res.interior_width, 2), round(res.interior_depth, 2)],
            "height_mm": round(res.height, 2),
            "wall_angles_deg": {k: round(v, 3) for k, v in res.angles.items()},
            "fit_clearance_per_side_mm": round(spec.fit_clearance, 2),
            "outside_corner_radius_mm": round(res.outer_radius, 2),
            "construction_mm": vars(spec.construction),
            "compartments_interior_coords": [c.as_dict() for c in res.compartments],
            "shared_walls": [list(w) for w in res.shared_walls],
        },
        "printer": {"name": spec.printer.name, "usable_mm": list(spec.printer.usable),
                    "margin_mm": spec.printer.margin_mm},
        "seams": [d.as_dict() for d in seams],
        "sections": section_reports,
        "totals": {
            "sections": len(section_reports),
            "volume_cm3": round(total_volume / 1000, 1),
            "solid_weight_pla_g": round(total_volume / 1000 * PLA_DENSITY, 0),
            "weight_note": "Upper bound if printed 100% solid. Use the slicer for real grams and print time.",
        },
        "warnings": result.warnings,
        "files": [f.name for f in result.files],
    }
    report_path = out_dir / f"{spec.label}_report.json"
    report_path.write_text(json.dumps(result.report, indent=2))
    result.files.append(report_path)

    if preview:
        from .preview import render_png
        png = out_dir / f"{spec.label}_preview.png"
        render_png([f for f in result.files if f.suffix == ".stl" and "assembly" not in f.name], png,
                   explode=12, title=f"{spec.label} sections")
        result.files.append(png)
    return result
