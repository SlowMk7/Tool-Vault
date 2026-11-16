import pytest

from gu.errors import DesignError
from gu.layout import resolve
from gu.seams import plan_sections
from gu.spec import parse_spec


def rects(*items):
    return {"compartments": [dict(zip(("id", "x", "y", "width", "depth"), i)) for i in items]}


def test_columns_share_one_wall_and_fill_the_interior(small):
    res = resolve(parse_spec(small))
    a, b = res.compartments
    assert res.interior_width == pytest.approx(122) and res.interior_depth == pytest.approx(82)
    assert a.width == pytest.approx(59.5) and b.width == pytest.approx(59.5)
    assert b.x0 - a.x1 == pytest.approx(3.0)          # exactly one divider between them
    assert res.shared_walls == [("a", "b")]


def test_nested_rows_and_fixed_sizes(small):
    small["layout"] = {"rows": [
        {"size": 30, "columns": [{"id": "a", "size": 40}, {"id": "b", "fill": 1}]},
        {"fill": 1, "id": "c"},
    ]}
    res = resolve(parse_spec(small))
    a, b, c = res.compartments
    assert (a.width, a.depth) == pytest.approx((40, 30))
    assert b.width == pytest.approx(122 - 40 - 3)
    assert c.y0 == pytest.approx(33) and c.depth == pytest.approx(82 - 33)


def test_sizes_that_do_not_add_up_are_rejected_not_stretched(small):
    small["layout"] = {"columns": [{"id": "a", "size": 50}, {"id": "b", "size": 50}]}
    with pytest.raises(DesignError, match="do not|add up"):
        resolve(parse_spec(small))


def test_overlap_is_detected(small):
    small["layout"] = rects(("a", 0, 0, 60, 82), ("b", 50, 0, 72, 82))
    with pytest.raises(DesignError, match="overlap"):
        resolve(parse_spec(small))


def test_too_close_and_sliver_gaps_are_detected(small):
    small["layout"] = rects(("a", 0, 0, 50, 82), ("b", 52, 0, 70, 82))
    with pytest.raises(DesignError, match="only 2.00 mm apart"):
        resolve(parse_spec(small))
    small["layout"] = rects(("a", 0, 0, 50, 82), ("b", 58, 0, 64, 82))
    with pytest.raises(DesignError, match="unusable sliver"):
        resolve(parse_spec(small))


def test_open_floor_area_is_allowed(small):
    # b sits away from the right and back walls, leaving usable open floor.
    small["layout"] = rects(("a", 0, 0, 50, 82), ("b", 53, 0, 40, 50))
    res = resolve(parse_spec(small))
    assert len(res.compartments) == 2


def test_compartment_outside_or_too_small(small):
    small["layout"] = rects(("a", 0, 0, 130, 82))
    with pytest.raises(DesignError, match="outside the organizer"):
        resolve(parse_spec(small))
    small["layout"] = rects(("a", 0, 0, 10, 82))
    with pytest.raises(DesignError, match="minimum"):
        resolve(parse_spec(small))


def test_gap_to_perimeter_must_be_zero_or_usable(small):
    small["layout"] = rects(("a", 2, 0, 60, 82))
    with pytest.raises(DesignError, match="from the left perimeter wall"):
        resolve(parse_spec(small))


def test_duplicate_ids(small):
    small["layout"] = {"columns": [{"id": "a"}, {"id": "a"}]}
    with pytest.raises(DesignError, match="unique"):
        resolve(parse_spec(small))


# ------------------------------------------------------------------- seams

def plan(spec_dict):
    res = resolve(parse_spec(spec_dict))
    return res, plan_sections(res, res.spec.seams)


@pytest.mark.parametrize("owner,low_end,high_start", [
    ("a", 62.5, 62.65),          # a keeps the whole wall (59.5 + 3), gap on b's side
    ("b", 59.35, 59.5),          # b keeps the whole wall
    ("split", 60.925, 61.075),   # wall split down the middle
])
def test_seam_positions_for_each_owner(small, owner, low_end, high_start):
    small["seams"] = [{"between": ["a", "b"], "owner": owner}]
    _, (sections, details, warnings) = plan(small)
    left, right = sections
    assert left.region.x1 == pytest.approx(low_end)
    assert right.region.x0 == pytest.approx(high_start)
    assert left.compartments == ["a"] and right.compartments == ["b"]
    assert warnings == []


def test_seam_needs_a_shared_wall(small):
    small["layout"] = rects(("a", 0, 0, 50, 82), ("b", 53, 0, 40, 50), ("c", 53, 53, 40, 29))
    small["seams"] = [{"between": ["a", "c"], "owner": "a"}]   # a and c do share a wall
    plan(small)
    # b/c share a wall, but a straight seam on it would run on through compartment a.
    small["seams"] = [{"between": ["b", "c"], "owner": "split"}]
    with pytest.raises(DesignError, match='cut through compartment "a"'):
        plan(small)
    small["layout"] = rects(("a", 0, 0, 50, 40), ("b", 70, 45, 52, 37))
    small["seams"] = [{"between": ["a", "b"], "owner": "a"}]
    with pytest.raises(DesignError, match="do not share a divider"):
        plan(small)


def test_seam_through_a_compartment_is_rejected_with_advice():
    spec = {
        "spec_version": 1, "design_id": "T", "units": "mm",
        "drawer": {"width": 206, "depth": 106}, "organizer": {"height": 40},
        # front row: two halves; back row: one long compartment
        "layout": {"rows": [
            {"size": 47, "columns": [{"id": "a"}, {"id": "b"}]},
            {"fill": 1, "id": "long"},
        ]},
        "seams": [{"between": ["a", "b"], "owner": "split"}],
    }
    with pytest.raises(DesignError, match='cut through compartment "long"'):
        plan(spec)
    # Splitting front from back first makes the same seam valid (region by region).
    spec["seams"] = [{"between": ["a", "long"], "owner": "a"}, {"between": ["a", "b"], "owner": "split"}]
    _, (sections, _, _) = plan(spec)
    assert len(sections) == 3


def test_seam_across_open_floor_warns(small):
    # Nothing behind a and b: the seam's back part runs over open floor (43..82 mm).
    small["layout"] = rects(("a", 0, 0, 50, 40), ("b", 53, 0, 69, 40))
    small["seams"] = [{"between": ["a", "b"], "owner": "a"}]
    _, (_, _, warnings) = plan(small)
    assert warnings and "crosses 39 mm of floor with no wall" in warnings[0]


def test_seam_along_a_wall_face_is_not_open_floor(small):
    # The seam at x=53 runs along c's right-hand wall, so no warning.
    small["layout"] = rects(("a", 0, 0, 50, 40), ("b", 53, 0, 69, 40), ("c", 0, 43, 50, 39))
    small["seams"] = [{"between": ["a", "b"], "owner": "a"}]
    _, (_, _, warnings) = plan(small)
    assert warnings == []


def test_sections_are_numbered_front_left_first(small):
    small["layout"] = {"rows": [
        {"fill": 1, "columns": [{"id": "fl"}, {"id": "fr"}]},
        {"fill": 1, "columns": [{"id": "bl"}, {"id": "br"}]},
    ]}
    small["seams"] = [{"between": ["fl", "bl"], "owner": "fl"},
                      {"between": ["fl", "fr"], "owner": "split"},
                      {"between": ["bl", "br"], "owner": "split"}]
    _, (sections, _, _) = plan(small)
    assert [s.compartments for s in sections] == [["fl"], ["fr"], ["bl"], ["br"]]
    assert [s.name for s in sections] == ["P1-of-4", "P2-of-4", "P3-of-4", "P4-of-4"]


def test_seam_between_already_separated_compartments(small):
    small["seams"] = [{"between": ["a", "b"], "owner": "a"}, {"between": ["a", "b"], "owner": "a"}]
    with pytest.raises(DesignError, match="already in different sections"):
        plan(small)


def test_floor_seam_needs_explicit_opt_in_and_is_reported():
    spec = {
        "spec_version": 1, "design_id": "T", "units": "mm",
        "drawer": {"width": 206, "depth": 106}, "organizer": {"height": 40},
        "layout": {"rows": [{"size": 47, "columns": [{"id": "a"}, {"id": "b"}]}, {"fill": 1, "id": "long"}]},
        "seams": [{"between": ["a", "b"], "owner": "split", "through": ["long"]}],
    }
    res, (sections, _, warnings) = plan(spec)
    assert len(sections) == 2
    assert res.floor_seam_compartments == {"long"}
    assert "floor-only" in warnings[0] and "'long'" in warnings[0]


def test_through_must_name_a_crossed_compartment(small):
    small["seams"] = [{"between": ["a", "b"], "owner": "a", "through": ["b"]}]
    with pytest.raises(DesignError, match="does not cross"):
        plan(small)
