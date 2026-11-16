# Ground Up Woodworking — Drawer Organizer Generator

Milestone 1. The generator reads a design file (your drawer measurements plus a compartment layout) and produces numbered, printable STL sections that are checked against your printer.

> **Status:** the geometry is built and tested by software only. **Nothing here has been physically printed and fit-tested yet.** Do not sell a design until it has been printed and checked.

## What it does today

| Works now | Not built yet (planned) |
|---|---|
| Design files in **mm or inches** (fractions like `"12 1/2"` allowed) | Website, payments, database, dashboard |
| Straight drawers, and **tapered (leaning) outside walls** from top/bottom measurements or angles | Choosing seam positions automatically |
| Rounded drawer corners | Finger scoops, labels, embossed piece numbers |
| Compartments with **shared walls** (one wall between neighbours, never two) | Drawer lips, rails and obstructions |
| Open floor areas that stay floor | L-shaped or non-rectangular sections |
| **Seams you choose**, region by region, with "who keeps the wall" control | 3MF and printer-specific project files |
| Section size checked against the printer bed | Assembly instructions PDF |
| Every STL re-read and checked as a closed, single, printable solid | |
| Clear error messages for impossible designs | |

## How to run it (step by step)

You need Python 3.11 or newer.

```bash
cd organizer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # one time only

.venv/bin/python -m gu check    examples/GU-0001-owner-drawer.json   # quick check, no 3D files
.venv/bin/python -m gu generate examples/GU-0001-owner-drawer.json   # builds the files
.venv/bin/python -m pytest tests                                       # runs all 59 tests (~10 s)
```

Files go into `output/<design-id>-r<revision>/`:

| File | What it is |
|---|---|
| `GU-0001-r1_P1-of-4.stl` … | The printable sections. Drag them into Bambu Studio. P1 is front-left, then left to right, front to back. |
| `GU-0001-r1_assembly-preview.stl` | The whole organizer in one piece, for viewing only. Not for printing. |
| `GU-0001-r1_layout.svg` | Top-down diagram (open in any web browser). Front is at the bottom. |
| `GU-0001-r1_report.json` | All resolved dimensions, sections, seams, weights and warnings. |

The section STLs keep their assembly position. Bambu Studio places each one on the bed automatically. Print every section floor-down.

## The design file, explained

See `examples/GU-0002-from-photo.json` (the owner's photo as a customer order, with a floor seam), `examples/GU-0001-owner-drawer.json` (rows/columns style) and `examples/GU-EX02-bathroom.json` (exact rectangles style).

- **`units`**: `"in"` or `"mm"`. This applies to the drawer, organizer and layout values. Any of those values can also carry its own unit, e.g. `"1mm"`.
- **`drawer`**: inside `width` and `depth` measured at the floor, plus `height` and `corner_radius`. An optional `taper` takes either `top_width` / `top_depth` with `measured_at_height`, or `angles_deg` per side.
- **`organizer`**: the `height`, and `fit_clearance`, which is the gap left on each side between the organizer and the drawer (default 1 mm).
- **`construction`**: engineering settings, always in millimetres. Defaults are 3.0 mm perimeter and divider walls, a 1.6 mm floor, 0.8 mm top-edge rounding and a 0.15 mm seam gap. **These are starting values to confirm with test prints, not final values.**
- **`layout`**: give it in one of two ways:
  - `"rows"` / `"columns"`: nested splits. Each part has a `"size"`, or `"fill"` to share the leftover space.
  - `"compartments"`: exact rectangles, `x`, `y`, `width`, `depth`, measured from the inside front-left corner. Sizes are the usable inside sizes. Neighbours sharing a wall must be exactly one divider thickness apart.
- **`seams`**: each seam names two compartments that share a wall.
  - `"owner"` decides who keeps that wall: one of the two compartment names, or `"split"` (each side keeps half).
  - Seams are applied in order. Each one only cuts the section that currently contains both compartments, which is how you get stepped seams.
  - Walls running across a seam are simply cut. Each piece carries its part of the wall, so the wall continues across the joint.
  - **Floor seams:** a seam may continue across a compartment's floor only if you list that compartment in `"through"`, e.g. `"through": ["gadgets"]`. You need this when a compartment is wider than the printer bed. That part of the joint has no wall (a floor-only butt joint), so the generator always warns about it.
- **`printer`**: a `profile` (`bambu-p1s`, `bambu-a1`, `bambu-a1-mini`, `bambu-x1c`, `bambu-p1p`, `prusa-mk4`, `prusa-core-one`), or your own `bed_width_mm`, `bed_depth_mm`, `max_height_mm`. The default `margin_mm` is 2.

### Coordinates

- Millimetres. X runs left to right, Y runs front to back, Z runs up.
- "Front" is the side nearest you when the drawer is open.
- Compartment positions are measured from the inside front-left corner of the perimeter wall, at floor level.

## How the geometry is built

1. The outside is a solid whose walls can each lean at their own angle, with a small chamfer on the bottom edge.
2. The inside is hollowed out above the floor, leaving the perimeter wall and a continuous floor.
3. Divider walls come from a frame around each compartment. Frames of neighbours overlap exactly, so a shared wall is built once. Dividers that meet a leaning outside wall are extended so they always join it.
4. The top edges are rounded.
5. The organizer is cut into sections at your seams. A 0.15 mm gap is removed at each seam so slightly oversize prints still fit.

## What has been tested

- **59 automated tests**, all passing. They cover:
  - unit conversion, including inches and fractions;
  - design-file errors;
  - overlaps, slivers and minimum sizes;
  - shared walls, built once;
  - taper angle and measured widths;
  - wall thickness at seams, for both ownership styles;
  - floor height;
  - volume conservation at seams;
  - printer-fit errors;
  - identical output from identical input;
  - both example designs end to end.
- **Every exported STL is reloaded and checked**: closed mesh, one body, and volume matching the CAD model.
- **Both examples sliced successfully in PrusaSlicer 2.7** with no errors. Run `tools/slice_check.sh output/GU-0001-r1` if PrusaSlicer is installed.
- **Not tested:** any physical print, the fit in a real drawer, seam alignment, strength, Bambu Studio slicing.

## Stage 0 feasibility test

`stage0/feasibility.py` proved that build123d can make the risky features (tapered and rounded walls, shared divider, rounded top edges, both seam styles) as valid solids, with measured dimensions matching the design. Its results are in `stage0/output/results.json`.
