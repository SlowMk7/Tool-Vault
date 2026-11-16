"""Geometry tests: build real solids and STL files, then measure them."""

import hashlib
import json
import math

import numpy as np
import pytest
import trimesh

from gu.errors import DesignError
from gu.generate import generate
from tests.conftest import EXAMPLES


def wall_runs(stl, y, z):
    """Thickness of each solid run crossed by a ray along +X at (y, z)."""
    m = trimesh.load(stl, force="mesh")
    hits, _, _ = m.ray.intersects_location(np.array([[-100.0, y, z]]), np.array([[1.0, 0, 0]]),
                                           multiple_hits=True)
    xs = sorted({round(float(h[0]), 4) for h in hits})
    return xs, [round(xs[i + 1] - xs[i], 3) for i in range(0, len(xs) - 1, 2)]


def write(tmp_path, spec):
    path = tmp_path / "design.json"
    path.write_text(json.dumps(spec))
    return path


def test_one_piece_dimensions_and_shared_divider(small, tmp_path):
    r = generate(write(tmp_path, small), tmp_path / "out")
    (sec,) = r.report["sections"]
    assert sec["size_mm"] == pytest.approx([128, 88, 40], abs=0.01)
    assert sec["mesh"]["watertight"] and sec["mesh"]["separate_bodies"] == 1
    stl = r.out_dir / sec["file"]
    xs, runs = wall_runs(stl, 44, 20)
    # perimeter, one shared divider (not two), perimeter
    assert runs == pytest.approx([3.0, 3.0, 3.0], abs=0.01)
    assert xs[2] == pytest.approx(3 + 59.5, abs=0.01)   # divider starts after compartment a


def test_floor_is_solid_and_continuous(small, tmp_path):
    r = generate(write(tmp_path, small), tmp_path / "out")
    m = trimesh.load(r.out_dir / r.report["sections"][0]["file"], force="mesh")
    # Rays straight down inside each compartment must hit the floor top at 1.6 mm.
    pts = np.array([[30, 44, 50], [95, 44, 50]], dtype=float)
    hits, idx, _ = m.ray.intersects_location(pts, np.tile([0, 0, -1.0], (2, 1)), multiple_hits=False)
    assert sorted(h[2] for h in hits) == pytest.approx([1.6, 1.6], abs=0.01)


@pytest.mark.parametrize("owner,left_runs,right_runs", [
    ("a", [3.0, 3.0], [3.0]),            # left keeps the whole divider, right is open at the seam
    ("split", [3.0, 1.425], [1.425, 3.0]),  # each keeps half (3.0 - 0.15 gap) / 2
])
def test_seam_wall_ownership(small, tmp_path, owner, left_runs, right_runs):
    small["seams"] = [{"between": ["a", "b"], "owner": owner}]
    r = generate(write(tmp_path, small), tmp_path / "out")
    left, right = r.report["sections"]
    for sec, expected in ((left, left_runs), (right, right_runs)):
        assert sec["mesh"]["watertight"] and sec["mesh"]["separate_bodies"] == 1
        _, runs = wall_runs(r.out_dir / sec["file"], 44, 20)
        assert runs == pytest.approx(expected, abs=0.01)


def test_seam_volume_is_conserved(small, tmp_path):
    """Sections add up to the whole organizer minus only the seam gap slice."""
    whole = generate(write(tmp_path, small), tmp_path / "whole").report["totals"]["volume_cm3"]
    small["seams"] = [{"between": ["a", "b"], "owner": "split"}]
    parts = generate(write(tmp_path, small), tmp_path / "split").report["totals"]["volume_cm3"]
    # The 0.15 mm gap removes a slice through the divider: 0.15 x 82 x (40 - 1.6) plus floor and perimeter.
    removed = whole - parts
    assert 0.4 < removed < 0.65


def test_taper_matches_measurements(small, tmp_path):
    small["drawer"]["taper"] = {"angles_deg": {"left": 4, "right": 4}}
    r = generate(write(tmp_path, small), tmp_path / "out")
    stl = r.out_dir / r.report["sections"][0]["file"]
    for z in (5.0, 20.0, 35.0):
        xs, runs = wall_runs(stl, 44, z)
        expected_width = 128 + 2 * z * math.tan(math.radians(4))
        assert xs[-1] - xs[0] == pytest.approx(expected_width, abs=0.01)
        # The divider stays vertical and reaches both leaning outside walls (3 runs, no gaps).
        assert len(runs) == 3
        assert runs[1] == pytest.approx(3.0, abs=0.01)


def test_rounded_corners_and_owner_example_build(tmp_path):
    r = generate(EXAMPLES / "GU-EX02-bathroom.json", tmp_path / "out")
    assert r.report["totals"]["sections"] == 4
    for sec in r.report["sections"]:
        assert sec["mesh"]["watertight"] and sec["mesh"]["separate_bodies"] == 1
        assert sec["fits_printer"]


def test_owner_drawer_example_four_pieces(tmp_path):
    r = generate(EXAMPLES / "GU-0001-owner-drawer.json", tmp_path / "out")
    rep = r.report
    assert rep["totals"]["sections"] == 4
    assert rep["resolved"]["wall_angles_deg"]["left"] == pytest.approx(4.086, abs=0.001)
    assert rep["resolved"]["outside_at_floor_mm"] == pytest.approx([302.8, 328.2], abs=0.01)
    for sec in rep["sections"]:
        assert sec["mesh"]["watertight"] and sec["mesh"]["separate_bodies"] == 1
        assert max(sec["size_mm"][:2]) <= 252


def test_same_input_gives_identical_files(small, tmp_path):
    small["seams"] = [{"between": ["a", "b"], "owner": "split"}]
    path = write(tmp_path, small)
    digests = []
    for run in ("one", "two"):
        r = generate(path, tmp_path / run)
        digests.append([hashlib.sha256((r.out_dir / s["file"]).read_bytes()).hexdigest()
                        for s in r.report["sections"]])
    assert digests[0] == digests[1]


def test_piece_too_big_for_printer_is_explained(small, tmp_path):
    small["printer"] = {"name": "tiny", "bed_width_mm": 100, "bed_depth_mm": 100, "max_height_mm": 100}
    with pytest.raises(DesignError, match="does not fit the usable area"):
        generate(write(tmp_path, small), tmp_path / "out")


def test_compartment_bigger_than_bed_is_caught_early(small, tmp_path):
    small["printer"] = {"name": "tiny", "bed_width_mm": 60, "bed_depth_mm": 60, "max_height_mm": 100}
    with pytest.raises(DesignError, match="no seam along walls"):
        generate(write(tmp_path, small), tmp_path / "out")


def test_narrow_section_is_rejected(tmp_path, small):
    small["layout"] = {"columns": [{"id": "a", "size": 20}, {"id": "b", "fill": 1}]}
    small["seams"] = [{"between": ["a", "b"], "owner": "a"}]
    with pytest.raises(DesignError, match="minimum is 40 mm"):
        generate(write(tmp_path, small), tmp_path / "out")


def test_photo_order_with_floor_seam(tmp_path):
    """Full-width front bin is wider than a P1S bed; the floor seam makes it printable."""
    r = generate(EXAMPLES / "GU-0002-from-photo.json", tmp_path / "out")
    assert r.report["totals"]["sections"] == 4
    for sec in r.report["sections"]:
        assert sec["mesh"]["watertight"] and sec["mesh"]["separate_bodies"] == 1
        assert max(sec["size_mm"][:2]) <= 252
    assert any("floor-only" in w for w in r.warnings)
    assert r.report["resolved"]["outside_overall_mm"][2] == pytest.approx(88.9, abs=0.01)


def test_wide_bin_without_floor_seam_is_refused_with_advice(tmp_path):
    spec = json.loads((EXAMPLES / "GU-0002-from-photo.json").read_text())
    spec["seams"][2].pop("through")
    with pytest.raises(DesignError, match='cut through compartment "gadgets"'):
        generate(write(tmp_path, spec), tmp_path / "out")
