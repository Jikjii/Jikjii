"""
wall.py - the light wall from jikjii.github.io/geraldo, ported from
assets/site.js / tools/make-og.mjs so the profile glows with the same noise,
the same palettes and the same 19px tiles on a 20px grid.

The integer hashing matches JavaScript's Math.imul and >>> exactly, so a
palette and a moment T give the same tiles here as on the site.
"""

from __future__ import annotations

import math

BG = "#140c08"
UNLIT = "#201309"

# The palettes from content.js on the site. `margin` is Margin Lab's signal
# yellow; `dusk` is Crewroom's page.
PALETTES = {
    "amber": {"seed": 0, "stops": ["#ff2d00", "#ff5400", "#ff6b1a", "#ff8510", "#ff9f1c", "#ffb703",
                                   "#ffc933", "#ffd60a", "#ffe566", "#ff8a3d", "#ff4d1a"]},
    "ember": {"seed": 67, "stops": ["#ff2d00", "#ff5400", "#ff9f1c", "#ffd60a", "#ff8a3d", "#ff6b1a"]},
    "dusk": {"seed": 43, "stops": ["#7b5cff", "#b45cff", "#ff5cc8", "#ff8a8a", "#ffc49a", "#d98cff"]},
    "rose": {"seed": 53, "stops": ["#ff3d6e", "#ff6b8b", "#ff9eb5", "#ffc2d1", "#ffe0e8", "#ff7a9c"]},
    "margin": {"seed": 61, "stops": ["#facc15", "#fde047", "#f3f4f6", "#fde047", "#facc15", "#fef08a"]},
    # Status tiles use a narrow, saturated slice of each palette: one colour per row
    # with a little shimmer, never a red that reads as an alarm or a pale that reads as off.
    "signal": {"seed": 0, "stops": ["#ff9f1c", "#ffb703", "#ff9f1c", "#ffaa12"]},
    "status-margin": {"seed": 61, "stops": ["#facc15", "#fde047", "#facc15", "#f7c814"]},
    "status-dusk": {"seed": 43, "stops": ["#7b5cff", "#9a5cff", "#b45cff", "#9a5cff"]},
    "status-rose": {"seed": 53, "stops": ["#ff3d6e", "#ff6b8b", "#ff5c7d"]},
}

M32 = 0xFFFFFFFF


def _i32(v: int) -> int:
    v &= M32
    return v - (1 << 32) if v & 0x80000000 else v


def _imul(a: int, b: int) -> int:
    return _i32((a & M32) * (b & M32))


def hash3(x: int, y: int, z: int) -> float:
    h = _i32(_imul(x, 0x27D4EB2D) + _imul(y, 0x165667B1) + _imul(z, 0x61C88647))
    h = _imul(h ^ ((h & M32) >> 16), 0x7FEB352D)
    h = _imul(h ^ ((h & M32) >> 15), 0x846CA68B)
    h ^= (h & M32) >> 16
    return (h & M32) / 4294967296


def noise3(x: float, y: float, z: float) -> float:
    xi, yi, zi = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - xi, y - yi, z - zi
    u, v, w = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)

    def lerp(a, b, t):
        return a + (b - a) * t

    x00 = lerp(hash3(xi, yi, zi), hash3(xi + 1, yi, zi), u)
    x10 = lerp(hash3(xi, yi + 1, zi), hash3(xi + 1, yi + 1, zi), u)
    x01 = lerp(hash3(xi, yi, zi + 1), hash3(xi + 1, yi, zi + 1), u)
    x11 = lerp(hash3(xi, yi + 1, zi + 1), hash3(xi + 1, yi + 1, zi + 1), u)
    return lerp(lerp(x00, x10, v), lerp(x01, x11, v), w)


def fbm(x: float, y: float, z: float) -> float:
    return 0.62 * noise3(x, y, z) + 0.38 * noise3(x * 2.17 + 11.3, y * 2.17 + 7.9, z * 2.17 + 3.1)


def sm(u: float) -> float:
    return 0.0 if u <= 0 else 1.0 if u >= 1 else u * u * (3 - 2 * u)


def _rgb(hex_: str):
    n = int(hex_.lstrip("#"), 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def hexs(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def build_lut(stops):
    rgb = [_rgb(s) for s in stops]
    n, lut = len(rgb), []
    for k in range(512):
        pos = (k / 512) * n
        seg = math.floor(pos)
        f = sm(pos - seg)
        a, b = rgb[seg % n], rgb[(seg + 1) % n]
        lut.append(tuple(math.sqrt(a[c] * a[c] * (1 - f) + b[c] * b[c] * f) for c in range(3)))
    return lut


class Wall:
    """Samples a palette's light wall at tile (i, j) and moment T."""

    def __init__(self, palette: str = "amber", T: float = 12 * 1.3675):
        p = PALETTES[palette]
        self.lut = build_lut(p["stops"])
        self.seed = p["seed"] * 0.07
        self.T = T
        self.hue = T * 0.012 + 12 * 0.04

    def brightness(self, i: float, j: float) -> float:
        T = self.T
        b = fbm(i * 0.1 + T * 0.06, j * 0.1 + T * 0.025, T * 0.09 + 47.1 + self.seed)
        b = (b - 0.02) / 0.98
        b = 0 if b <= 0 else b ** 0.95
        return (0.55 + 0.45 * min(b, 1)) * 0.935

    def color(self, i: float, j: float, b: float) -> str:
        T = self.T
        s = fbm(i * 0.05 + T * 0.04, j * 0.05 + T * 0.018, T * 0.05) + self.hue
        s -= math.floor(s)
        r, g, bl = self.lut[int(s * 512) % 512]
        m = (int(max(0.0, min(1.0, b)) * 63) + 0.5) / 64
        return hexs((r * m, g * m, bl * m))
