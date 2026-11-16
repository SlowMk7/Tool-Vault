import math

import pytest

from gu.errors import DesignError
from gu.spec import parse_spec
from gu.units import to_mm


@pytest.mark.parametrize("value,units,expected", [
    (12, "in", 304.8),
    ("12", "in", 304.8),
    ("12 1/2", "in", 317.5),
    ("12-1/2", "in", 317.5),
    ("3/4", "in", 19.05),
    ('12.5"', "mm", 317.5),
    ("12.5in", "mm", 317.5),
    ("300mm", "in", 300.0),
    ("30 cm", "mm", 300.0),
    (88.9, "mm", 88.9),
])
def test_lengths_convert_to_mm(value, units, expected):
    assert to_mm(value, units) == pytest.approx(expected)


@pytest.mark.parametrize("bad", ["abc", "1/0", True, None, "12 1/2 ft"])
def test_unreadable_lengths_are_rejected(bad):
    with pytest.raises(ValueError):
        to_mm(bad, "mm")


def test_inch_and_mm_designs_resolve_identically(small):
    inch = dict(small, units="in")
    inch["drawer"] = {"width": 130 / 25.4, "depth": 90 / 25.4, "height": "60mm"}
    inch["organizer"] = {"height": "40mm", "fit_clearance": "1mm"}
    a, b = parse_spec(small), parse_spec(inch)
    assert a.drawer_width == pytest.approx(b.drawer_width)
    assert a.drawer_depth == pytest.approx(b.drawer_depth)
    assert a.organizer_height == pytest.approx(b.organizer_height)
    assert a.fit_clearance == pytest.approx(b.fit_clearance)


def test_misspelled_setting_gets_a_suggestion(small):
    small["drawer"]["hieght"] = small["drawer"].pop("height")
    with pytest.raises(DesignError) as e:
        parse_spec(small)
    assert any('Did you mean "height"' in p for p in e.value.problems)


def test_missing_and_negative_values_are_all_reported_together(small):
    del small["drawer"]["width"]
    small["organizer"]["height"] = -5
    with pytest.raises(DesignError) as e:
        parse_spec(small)
    text = " ".join(e.value.problems)
    assert 'missing "width"' in text and "greater than zero" in text


def test_wrong_spec_version_is_rejected(small):
    small["spec_version"] = 2
    with pytest.raises(DesignError, match="spec_version"):
        parse_spec(small)


def test_organizer_taller_than_drawer_is_rejected(small):
    small["organizer"]["height"] = 70
    with pytest.raises(DesignError, match="taller than the drawer"):
        parse_spec(small)


def test_taper_from_owner_measurements():
    """12 in at the floor, 12 1/2 in at 3 1/2 in high -> about 4.09 degrees each side."""
    spec = parse_spec({
        "spec_version": 1, "design_id": "T", "units": "in",
        "drawer": {"width": 12, "depth": 13, "height": "3 1/2",
                   "taper": {"top_width": "12 1/2", "measured_at_height": "3 1/2"}},
        "organizer": {"height": 2}, "layout": {"columns": [{"id": "a"}]},
    })
    expected = math.degrees(math.atan(6.35 / 88.9))
    assert spec.taper.left == pytest.approx(expected)
    assert spec.taper.right == pytest.approx(expected)
    assert spec.taper.front == 0 and spec.taper.back == 0
    assert expected == pytest.approx(4.0856, abs=1e-3)


def test_one_sided_taper_and_direct_angles(small):
    small["drawer"]["taper"] = {"top_width": 140, "width_sides": "left", "measured_at_height": 60}
    s = parse_spec(small)
    assert s.taper.left == pytest.approx(math.degrees(math.atan(10 / 60)))
    assert s.taper.right == 0
    small["drawer"]["taper"] = {"angles_deg": {"left": 3, "back": 5}}
    s = parse_spec(small)
    assert (s.taper.left, s.taper.right, s.taper.front, s.taper.back) == (3, 0, 0, 5)


def test_drawer_narrower_at_top_is_rejected(small):
    small["drawer"]["taper"] = {"top_width": 120, "measured_at_height": 60}
    with pytest.raises(DesignError, match="narrower at the top"):
        parse_spec(small)


def test_unknown_printer_profile_suggests_closest(small):
    small["printer"] = {"profile": "bambu-p1"}
    with pytest.raises(DesignError, match="Did you mean"):
        parse_spec(small)


def test_custom_printer_and_margin(small):
    small["printer"] = {"name": "My printer", "bed_width_mm": 300, "bed_depth_mm": 280,
                        "max_height_mm": 300, "margin_mm": 0}
    s = parse_spec(small)
    assert s.printer.usable == (300, 280, 300)
