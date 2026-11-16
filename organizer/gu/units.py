"""Length parsing. Everything inside the generator is millimetres.

Accepted forms (the design file's "units" setting applies to bare numbers):

    304.8          a number in the design's units
    "12"           same, as text
    "12 1/2"       mixed fraction (also "12-1/2")
    "3/4"          plain fraction
    "12.5in"       explicit inches (also: in, inch, inches, ")
    "300mm"        explicit millimetres (also: mm, cm)
"""

from __future__ import annotations

import re

MM_PER_INCH = 25.4

_UNIT_SUFFIX = re.compile(r'^(.*?)\s*(mm|cm|inches|inch|in|")\s*$', re.IGNORECASE)
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_FRACTION = re.compile(r"^(?:(\d+(?:\.\d+)?)\s*[- ]\s*)?(\d+)\s*/\s*(\d+)$")

UNIT_FACTORS = {"mm": 1.0, "cm": 10.0, "in": MM_PER_INCH}


def normalise_units(name: str) -> str:
    n = name.strip().lower()
    if n in ("mm", "millimetre", "millimetres", "millimeter", "millimeters"):
        return "mm"
    if n in ("in", "inch", "inches", '"'):
        return "in"
    if n in ("cm",):
        return "cm"
    raise ValueError(f'unknown units "{name}" (use "mm" or "in")')


def to_mm(value: object, default_units: str) -> float:
    """Convert a length to millimetres. Raises ValueError with a readable message."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{value!r} is not a length")
    if isinstance(value, (int, float)):
        return float(value) * UNIT_FACTORS[default_units]
    if not isinstance(value, str):
        raise ValueError(f"{value!r} is not a length")

    text = value.strip()
    units = default_units
    m = _UNIT_SUFFIX.match(text)
    if m:
        text = m.group(1).strip()
        units = normalise_units(m.group(2))
    if _NUMBER.match(text):
        number = float(text)
    else:
        f = _FRACTION.match(text)
        if not f:
            raise ValueError(f'"{value}" is not a length I can read (examples: 12, "12 1/2", "300mm", "12.5in")')
        whole = float(f.group(1)) if f.group(1) else 0.0
        den = int(f.group(3))
        if den == 0:
            raise ValueError(f'"{value}" divides by zero')
        number = whole + int(f.group(2)) / den
    return number * UNIT_FACTORS[units]


def fmt_mm(mm: float, units: str = "mm") -> str:
    """Human-friendly length, with inches added for inch designs."""
    if units == "in":
        return f"{mm:.1f} mm ({mm / MM_PER_INCH:.3f} in)"
    return f"{mm:.1f} mm"
