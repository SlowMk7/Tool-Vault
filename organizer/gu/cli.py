"""Command line.

    python -m gu check    examples/GU-EX01.json     # fast: check the design only
    python -m gu generate examples/GU-EX01.json     # build STL sections + report
    python -m gu generate examples/GU-EX01.json --preview --out output
"""

from __future__ import annotations

import argparse
import sys
import time

from .errors import DesignError
from .generate import check_design, generate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m gu", description="Ground Up drawer organizer generator")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="check a design file without building 3D files")
    c.add_argument("design")
    g = sub.add_parser("generate", help="build printable STL sections from a design file")
    g.add_argument("design")
    g.add_argument("--out", default="output", help="output folder (default: output)")
    g.add_argument("--preview", action="store_true", help="also save a PNG picture of the sections")
    args = ap.parse_args(argv)

    started = time.time()
    try:
        if args.command == "check":
            spec, res, sections, _, warnings = check_design(args.design)
            print(f"OK: {spec.label} is a valid design.")
            print(f"  Outside at floor: {res.outer_width:.1f} x {res.outer_depth:.1f} mm, "
                  f"height {res.height:.1f} mm, {len(res.compartments)} compartments, {len(sections)} section(s).")
            for s in sections:
                print(f"  {s.name}: {', '.join(s.compartments)}")
        else:
            result = generate(args.design, args.out, preview=args.preview)
            r = result.report
            print(f"OK: generated {r['design']['design_id']}-r{r['design']['revision']} "
                  f"in {time.time() - started:.1f} s -> {result.out_dir}")
            for s in r["sections"]:
                sx, sy, sz = s["size_mm"]
                turn = " (rotate 90° on the bed)" if s["rotate_90_on_bed"] else ""
                print(f"  {s['file']}: {sx:.1f} x {sy:.1f} x {sz:.1f} mm, "
                      f"<= {s['solid_weight_pla_g']:.0f} g PLA if solid{turn}")
            print(f"  Total upper bound: {r['totals']['solid_weight_pla_g']:.0f} g PLA. "
                  "Physical fit is NOT verified until printed.")
            warnings = result.warnings
        for w in warnings:
            print(f"  WARNING: {w}")
        return 0
    except DesignError as e:
        print("This design cannot be generated yet:", file=sys.stderr)
        for prob in e.problems:
            print(f"  - {prob}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
