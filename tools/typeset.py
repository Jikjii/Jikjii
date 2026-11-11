"""
typeset.py - sets text as outlines so every SVG on the profile renders the
same in every browser, the GitHub mobile app included.

GitHub shows README images through <img>, which loads no web fonts, so text
drawn with <text> falls back to whatever the viewer has installed. Here each
run is shaped with HarfBuzz (kerning and all), each glyph is drawn once into
<defs>, and the run is placed with <use> references inside one scaled group.

    face = Face("fonts/SchibstedGrotesk-Medium.ttf", "M")
    doc = Doc(880, 340)
    doc.text(40, 140, "Geraldo Grell", face, 64, "#fff6e8", tracking=-0.02)
    doc.save("assets/hero.svg")
"""

from __future__ import annotations

import html
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


class Face:
    def __init__(self, path: str | Path, key: str):
        self.path = Path(path)
        self.key = key
        data = self.path.read_bytes()
        self._hb_face = hb.Face(data)
        self._hb_font = hb.Font(self._hb_face)
        self.upem = self._hb_face.upem
        self._tt = TTFont(self.path)
        self._glyphs = self._tt.getGlyphSet()
        self._order = self._tt.getGlyphOrder()
        self._paths: dict[int, str] = {}

    def shape(self, text: str, tracking: float = 0.0):
        """[(gid, x, y)] in font units, plus the run's advance."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self._hb_font, buf, {"kern": True, "liga": True, "calt": True})
        track = round(tracking * self.upem)
        out, pen_x = [], 0
        for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
            out.append((info.codepoint, pen_x + pos.x_offset, -pos.y_offset))
            pen_x += pos.x_advance + (track if i < len(buf.glyph_infos) - 1 else 0)
        return out, pen_x

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        return self.shape(text, tracking)[1] * size / self.upem

    def lsb(self, text: str, size: float) -> float:
        """Left side bearing of the first glyph, for optical left alignment."""
        if not text:
            return 0.0
        gid = self.shape(text[:1])[0][0][0]
        return self._tt["hmtx"][self._order[gid]][1] * size / self.upem

    def glyph_path(self, gid: int) -> str:
        if gid not in self._paths:
            pen = SVGPathPen(self._glyphs, ntos=lambda v: f"{v:g}" if v == int(v) else f"{v:.1f}")
            self._glyphs[self._order[gid]].draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
            self._paths[gid] = pen.getCommands()
        return self._paths[gid]

    def wrap(self, text: str, size: float, width: float, tracking: float = 0.0, max_lines: int = 99):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if not cur or self.width(trial, size, tracking) <= width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            kept = lines[:max_lines]
            last = kept[-1]
            while last and self.width(last + "…", size, tracking) > width:
                last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
            kept[-1] = last.rstrip(" ,;:—-") + "…"
            return kept, True
        return lines, False


def fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


class Doc:
    """A small SVG writer: shapes, outlined text, CSS, and a <title>."""

    def __init__(self, width: float, height: float, title: str = ""):
        self.w, self.h = width, height
        self.title = title
        self.defs: list[str] = []
        self.body: list[str] = []
        self.css: list[str] = []
        self._glyph_ids: set[str] = set()

    def add(self, markup: str):
        self.body.append(markup)

    def rect(self, x, y, w, h, fill="none", rx=0, stroke=None, sw=1, extra=""):
        a = f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}"'
        if rx:
            a += f' rx="{fmt(rx)}"'
        a += f' fill="{fill}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{fmt(sw)}"'
        self.body.append(a + (f" {extra}" if extra else "") + "/>")

    def text(self, x, y, s, face: Face, size, fill, tracking=0.0, anchor="start",
             opacity=None, cls=None) -> float:
        """Draw s with its baseline at y. Returns the drawn width in px."""
        if not s:
            return 0.0
        glyphs, adv = face.shape(s, tracking)
        scale = size / face.upem
        width = adv * scale
        if anchor == "end":
            x -= width
        elif anchor == "middle":
            x -= width / 2
        uses = []
        for gid, gx, gy in glyphs:
            path = face.glyph_path(gid)
            if not path:
                continue  # spaces
            gid_ref = f"{face.key}{gid}"
            if gid_ref not in self._glyph_ids:
                self._glyph_ids.add(gid_ref)
                self.defs.append(f'<path id="{gid_ref}" d="{path}"/>')
            uses.append(f'<use href="#{gid_ref}" x="{gx}"' + (f' y="{gy}"' if gy else "") + "/>")
        attrs = f'transform="translate({fmt(x)} {fmt(y)}) scale({scale:.6g})" fill="{fill}"'
        if opacity is not None:
            attrs += f' opacity="{fmt(opacity)}"'
        if cls:
            attrs += f' class="{cls}"'
        self.body.append(f"<g {attrs}>{''.join(uses)}</g>")
        return width

    def svg(self) -> str:
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(self.w)}" height="{fmt(self.h)}" '
                f'viewBox="0 0 {fmt(self.w)} {fmt(self.h)}" role="img"'
                + (f' aria-label="{html.escape(self.title)}"' if self.title else "") + ">")
        parts = [head]
        if self.title:
            parts.append(f"<title>{html.escape(self.title)}</title>")
        if self.css:
            parts.append("<style>" + "".join(self.css) + "</style>")
        if self.defs:
            parts.append("<defs>" + "".join(self.defs) + "</defs>")
        parts.extend(self.body)
        parts.append("</svg>\n")
        return "\n".join(parts)

    def save(self, path: str | Path) -> bool:
        """Write only when the content changed; returns True if it did."""
        path = Path(path)
        new = self.svg()
        if path.exists() and path.read_text() == new:
            return False
        path.write_text(new)
        return True
