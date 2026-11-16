"""Ground Up Woodworking drawer organizer generator.

Pipeline (each stage is its own module):

    spec.py      read + check the design file (what the customer asked for)
    layout.py    turn it into exact millimetre geometry (compartments, walls, taper)
    seams.py     turn the seam list into printable section regions
    geometry.py  build the 3D organizer and cut it into sections (build123d)
    checks.py    verify meshes and printer fit
    report.py    write the report and top-down diagram
    generate.py  run the whole pipeline
    cli.py       command line: `python -m gu generate design.json`
"""

__version__ = "0.1.0"
