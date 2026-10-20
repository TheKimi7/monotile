#!/usr/bin/env python3
"""Generate the Nothing-style dot menu icons (SVG) in this folder.

    python3 assets/make_menu_icons.py
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
WHITE, RED = "#f2f2f2", "#d71921"


def hexagon_ring(radius, per_edge):
    """Points along a pointy-top hexagon outline: corners plus (per_edge - 1) per side."""
    corners = [(radius * math.cos(math.radians(90 + 60 * i)), radius * math.sin(math.radians(90 + 60 * i)))
               for i in range(6)]
    pts = []
    for i in range(6):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 6]
        for k in range(per_edge):
            t = k / per_edge
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return pts


def svg(dots, centre_r):
    body = "".join(f'<circle cx="{32 + x:.2f}" cy="{32 - y:.2f}" r="{r}" fill="{WHITE}"/>' for x, y, r in dots)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
            f'{body}<circle cx="32" cy="32" r="{centre_r}" fill="{RED}"/></svg>\n')


def disc(gap):
    """Solid white disc with a red centre dot; `gap` adds a dark ring around the dot."""
    ring = f'<circle cx="32" cy="32" r="11" fill="#000000"/>' if gap else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
            f'<circle cx="32" cy="32" r="28" fill="{WHITE}"/>{ring}'
            f'<circle cx="32" cy="32" r="{7.5 if gap else 8.5}" fill="{RED}"/></svg>\n')


VARIANTS = {
    "monotile-menu-disc": disc(False),
    "monotile-menu-disc-gap": disc(True),
    "monotile-menu-hex6": svg([(x, y, 4.6) for x, y in hexagon_ring(22, 1)], 6.0),
    "monotile-menu-hex12": svg([(x, y, 3.6) for x, y in hexagon_ring(25, 2)], 5.6),
    "monotile-menu-hex19": svg([(x, y, 3.4) for x, y in hexagon_ring(13, 1)] +
                               [(x, y, 3.4) for x, y in hexagon_ring(26, 2)], 4.2),
}

if __name__ == "__main__":
    for name, text in VARIANTS.items():
        with open(os.path.join(HERE, name + ".svg"), "w") as f:
            f.write(text)
        print("wrote", name + ".svg")
