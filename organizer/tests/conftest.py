import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

# A small, fast design: 2 compartments side by side sharing one divider.
SMALL = {
    "spec_version": 1,
    "design_id": "GU-TEST",
    "revision": 1,
    "units": "mm",
    "drawer": {"width": 130, "depth": 90, "height": 60},
    "organizer": {"height": 40, "fit_clearance": 1.0},
    "construction": {"perimeter_wall_mm": 3.0, "divider_wall_mm": 3.0, "floor_mm": 1.6},
    "layout": {"columns": [{"id": "a", "fill": 1}, {"id": "b", "fill": 1}]},
    "seams": [],
    "printer": {"profile": "bambu-p1s"},
}


@pytest.fixture
def small():
    return copy.deepcopy(SMALL)
