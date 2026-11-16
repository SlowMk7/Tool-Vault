#!/usr/bin/env bash
# Slice every STL in a folder with PrusaSlicer (if installed) to prove the
# files are printable and to get real filament weights.
# Usage: tools/slice_check.sh output/GU-0001-r1
# Settings: 0.4 mm nozzle, 0.2 mm layers, 2 perimeters, 15% infill, PLA.
# Print TIMES use PrusaSlicer's default (slow) machine limits; use Bambu
# Studio for realistic times. Weights are realistic.
set -u
dir="${1:?give a folder of STL files}"
mkdir -p "$dir/slice-check"
for f in "$dir"/*_P*.stl; do
  b=$(basename "$f" .stl)
  prusa-slicer --export-gcode --bed-shape 0x0,256x0,256x256,0x256 --center 128,128 \
    --nozzle-diameter 0.4 --layer-height 0.2 --first-layer-height 0.2 --perimeters 2 \
    --fill-density 15% --filament-diameter 1.75 --filament-density 1.24 \
    --output "$dir/slice-check/$b.gcode" "$f" > "$dir/slice-check/$b.log" 2>&1
  status=$?
  grams=$(grep -m1 '^; filament used \[g\]' "$dir/slice-check/$b.gcode" 2>/dev/null | cut -d= -f2)
  echo "$b: exit $status, filament${grams:- ?} g"
done
rm -f "$dir"/slice-check/*.gcode
