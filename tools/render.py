#!/usr/bin/env python3
"""
render.py - draws assets/*.svg and rewrites README.md's marked blocks from
profile.toml, log/sweeps.jsonl and log/shipped.jsonl.

No network and no clock: everything is a function of those three files, so
running it twice changes nothing and the workflow only commits real news.

    python tools/render.py            # write assets/ and README.md
    python tools/render.py --local    # point README at ./assets (for previews)
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from typeset import Doc, Face, fmt  # noqa: E402
from wall import BG, UNLIT, Wall, fbm, sm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ROOT / "fonts"

SANS = Face(FONTS / "SchibstedGrotesk-Regular.ttf", "r")
SANS_M = Face(FONTS / "SchibstedGrotesk-Medium.ttf", "m")
MONO = Face(FONTS / "IBMPlexMono-Regular.ttf", "c")
MONO_M = Face(FONTS / "IBMPlexMono-Medium.ttf", "d")

W = 880  # every full-width panel shares this width, so columns line up across images

THEMES = {
    "dark": dict(card=BG, edge="#3a2413", ink="#fff6e8", ink2="#cdbda9", ink3="#988877",
                 accent="#ff9f1c", accent_ink="#ff9f1c", link="#ffc8a0", unlit=UNLIT,
                 down="#ff5544", rule="#2b1a0d", on_accent=BG),
    "light": dict(card="#fffaf4", edge="#ecdbc6", ink="#1c120b", ink2="#5a483a", ink3="#7c6957",
                  accent="#ff9f1c", accent_ink="#a14a00", link="#9a4600", unlit="#f1e3d2",
                  down="#cf222e", rule="#f2e5d5", on_accent=BG),
}

# Hero copy colours: the hero is the site's dark wall in both themes.
HERO_INK, HERO_INK2, HERO_INK3 = "#fff6e8", "#d9c7b2", "#a08f7e"

STATE_LABEL = {"up": "OPERATIONAL", "down": "DOWN", "failing": "FAILING", "private": "PRIVATE REPO",
               "idle": "IDLE", "unknown": "NO DATA", "pending": "FIRST SWEEP PENDING"}

WARNINGS: list[str] = []


def warn(msg: str):
    if msg not in WARNINGS:
        WARNINGS.append(msg)
        print(f"warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------- data

def load():
    cfg = tomllib.loads((ROOT / "profile.toml").read_text())
    sweeps = [json.loads(l) for l in (ROOT / "log/sweeps.jsonl").read_text().splitlines() if l.strip()]
    shipped = [json.loads(l) for l in (ROOT / "log/shipped.jsonl").read_text().splitlines() if l.strip()]
    return cfg, sweeps, shipped


def parse_t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def bucket_of(t: datetime, hours: int) -> int:
    return int(t.timestamp() // (hours * 3600))


def history(cfg, sweeps):
    """Per service: the state in each of the last `window` six-hour buckets (oldest first)."""
    hours, window = cfg["site"]["sweep_hours"], cfg["site"]["window"]
    if not sweeps:
        return None, {}
    last_t = max(parse_t(r["t"]) for r in sweeps)
    last_b = bucket_of(last_t, hours)
    first_b = last_b - window + 1
    grid: dict[str, list] = {}
    latest: dict[str, dict] = {}
    for r in sorted(sweeps, key=lambda r: r["t"]):
        b = bucket_of(parse_t(r["t"]), hours)
        latest[r["id"]] = r
        if b >= first_b:
            grid.setdefault(r["id"], [None] * window)[b - first_b] = r["state"]
    return last_t, {"grid": grid, "latest": latest}


# ---------------------------------------------------------------- shared bits

def arrow(d: Doc, x: float, y: float, size: float, color: str, sw: float = 1.4):
    """A north-east arrow whose bottom-left corner sits at (x, y)."""
    s = size
    d.add(f'<path d="M{fmt(x)} {fmt(y)}L{fmt(x + s)} {fmt(y - s)}M{fmt(x + s * 0.32)} {fmt(y - s)}'
          f'H{fmt(x + s)}V{fmt(y - s * 0.68)}" fill="none" stroke="{color}" stroke-width="{fmt(sw)}" '
          f'stroke-linecap="square"/>')


def lit_color(palette: str, i: int, j: int) -> str:
    """A lit status tile: the palette's wall, kept bright so it never reads as off."""
    w = Wall(palette if palette == "signal" else f"status-{palette}")
    b = 0.8 + 0.2 * (w.brightness(i * 1.7, j * 2.3) - 0.51) / 0.42
    return w.color(i * 1.3, j * 3.1, max(0.74, min(1.0, b)))


def tile(d: Doc, x, y, s, state, t, palette, i, j):
    if state == "up":
        d.rect(x, y, s, s, lit_color(palette, i, j))
    elif state in ("down", "failing"):
        k = 1.4
        d.rect(x + k / 2, y + k / 2, s - k, s - k, t["unlit"], stroke=t["down"], sw=k)
    else:
        d.rect(x, y, s, s, t["unlit"])


# ---------------------------------------------------------------- hero

# Where the bloom sits in the hero, and which patch of the site's wall it shows
# (dx, dy shift hero tiles into the coordinates of the site's preview image).
HERO_BLOOM = dict(si=35.0, sj=8.5, radius=6.8, rx=1.3, rag=4.0, dx=-33, dy=6)


def floor_unlit(c: str) -> str:
    """Never darker than an unlit tile, so the bloom fades out instead of casting a shadow."""
    a, b = int(c[1:], 16), int(UNLIT[1:], 16)
    return "#" + "".join(f"{max((a >> s) & 255, (b >> s) & 255):02x}" for s in (16, 8, 0))


def hero_frame(T: float, cols: int, rows: int):
    """The site's bloom, moved right so the copy sits on unlit tiles."""
    w = Wall("amber", T)
    hb = HERO_BLOOM
    out = {}
    for j in range(rows):
        for i in range(cols):
            if i in (0, cols - 1) or j in (0, rows - 1):
                out[(i, j)] = UNLIT
                continue
            u, v = i + hb["dx"], j + hb["dy"]  # the same tile on the site's wall
            b = w.brightness(u, v)
            dist = math.hypot((i - hb["si"]) / hb["rx"], j - hb["sj"])
            e = hb["radius"] - dist + (fbm(u * 0.3, v * 0.3, 5.7) - 0.5) * hb["rag"]
            b = b * sm(e / 2.3) + 0.8 * math.exp(-(e * e) / 5)
            out[(i, j)] = UNLIT if b < 0.02 else floor_unlit(w.color(u, v, min(b, 1.0)))
    return out


def render_hero(cfg) -> Doc:
    p = cfg["person"]
    H, CELL, TILE = 360, 20, 19
    cols, rows = (W + 1) // CELL, (H + 1) // CELL
    d = Doc(W, H, title=f'{p["name"]}: {p["eyebrow"]}')
    d.css.append(
        ".f2,.f3{opacity:0}"
        ".f2{animation:f2 27s ease-in-out infinite}"
        ".f3{animation:f3 27s ease-in-out infinite}"
        "@keyframes f2{0%{opacity:0}30%{opacity:1}66%{opacity:1}67%{opacity:0}100%{opacity:0}}"
        "@keyframes f3{0%,30%{opacity:0}60%{opacity:1}72%{opacity:1}100%{opacity:0}}"
        ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.8s ease-out infinite}"
        "@keyframes pulse{0%{transform:scale(1);opacity:.75}80%,100%{transform:scale(3.2);opacity:0}}"
        "@media (prefers-reduced-motion:reduce){.f2,.f3,.pulse{animation:none;opacity:0}}"
    )
    d.defs.append(f'<clipPath id="c"><rect width="{W}" height="{H}" rx="16"/></clipPath>')
    d.add('<g clip-path="url(#c)">')
    d.rect(0, 0, W, H, BG)

    T0 = 12 * 1.3675  # the moment the site's preview image is drawn at
    frames = [hero_frame(T0 + k * 1.6, cols, rows) for k in range(3)]
    base = frames[0]
    unlit_d = "".join(f"M{i * CELL} {j * CELL}h{TILE}v{TILE}h-{TILE}z"
                      for (i, j), c in base.items() if c == UNLIT)
    d.add(f'<path fill="{UNLIT}" d="{unlit_d}"/>')
    d.add("<g>" + "".join(f'<rect x="{i * CELL}" y="{j * CELL}" width="{TILE}" height="{TILE}" fill="{c}"/>'
                          for (i, j), c in base.items() if c != UNLIT) + "</g>")
    # Frame 2 fades in over frame 1, frame 3 over frame 2, then frame 3 fades out
    # to reveal frame 1 again; each layer only carries the tiles it changes.
    beneath = [base, frames[1]]
    for k, fr in enumerate(frames[1:], start=2):
        d.add(f'<g class="f{k}">' + "".join(
            f'<rect x="{i * CELL}" y="{j * CELL}" width="{TILE}" height="{TILE}" fill="{c}"/>'
            for (i, j), c in fr.items() if any(c != b[(i, j)] for b in beneath[:k - 1])) + "</g>")
    d.add("</g>")
    d.rect(0.5, 0.5, W - 1, H - 1, rx=15.5, stroke="#33200f")

    x = 40
    eyebrow = p["eyebrow"].upper()
    d.text(x, 63, eyebrow, MONO_M, 11.5, "#ff9f1c", tracking=0.14)
    d.text(x - SANS_M.lsb(p["name"], 68), 140, p["name"], SANS_M, 68, HERO_INK, tracking=-0.028)
    y = 184
    for line in p["lede"]:
        d.text(x, y, line, SANS, 17.5, HERO_INK2)
        y += 25
    # status pill: a lit tile that pulses, the way the site's wall breathes
    py, ph = 264, 30
    label = p["status"].upper()
    lw = MONO_M.width(label, 11, 0.1)
    pw = 16 + 8 + 10 + lw + 14
    d.rect(x + 0.5, py + 0.5, pw - 1, ph - 1, "#1c1109", rx=5, stroke="#4a2c10")
    lx, ly = x + 16, py + ph / 2 - 4
    d.rect(lx, ly, 8, 8, "#ff9f1c", extra='class="pulse"')
    d.rect(lx, ly, 8, 8, "#ff9f1c")
    d.text(lx + 18, py + 19.2, label, MONO_M, 11, HERO_INK, tracking=0.1)
    d.text(x, 322, p["location"].upper(), MONO, 10.5, HERO_INK3, tracking=0.12)
    return d


# ---------------------------------------------------------------- buttons

def render_button(link, theme) -> Doc:
    t = THEMES[theme]
    label = link["label"].upper()
    h, padx, gap, asz = 40, 18, 10, 7.5
    lw = MONO_M.width(label, 12, 0.1)
    w = math.ceil(padx + lw + gap + asz + padx)
    d = Doc(w, h, title=link["label"])
    if link.get("primary"):
        bg, fg, edge = t["accent"], t["on_accent"], None
    else:
        bg, fg, edge = t["card"], t["link"], t["edge"]
    d.rect(0.5, 0.5, w - 1, h - 1, bg, rx=7, stroke=edge)
    d.text(padx, 24.3, label, MONO_M, 12, fg, tracking=0.1)
    arrow(d, padx + lw + gap, 24.3, asz, fg)
    return d


# ---------------------------------------------------------------- control plane

COL_NAME, COL_TEXT, COL_RIGHT = 44, 216, 856
STRIP_T, STRIP_GAP = 8, 1


def strip_x(window: int) -> float:
    return COL_RIGHT - (window * (STRIP_T + STRIP_GAP) - STRIP_GAP)


def render_board_head(cfg, last_t, theme) -> Doc:
    t = THEMES[theme]
    window = cfg["site"]["window"]
    days = window * cfg["site"]["sweep_hours"] // 24
    H = 112
    d = Doc(W, H, title="Control plane")
    d.text(-SANS_M.lsb("C", 24) + 1, 30, "Control plane", SANS_M, 24, t["ink"], tracking=-0.01)
    d.text(1, 57, "Things I run, not things I finished once. One tile per six-hour sweep, newest on the right.",
           SANS, 14, t["ink2"])
    # legend, right-aligned to the card edge
    items = [("up", "UP"), ("down", "DOWN"), ("none", "NO SIGNAL")]
    x = W
    for state, lab in reversed(items):
        lw = MONO.width(lab, 10.5, 0.08)
        x -= lw
        d.text(x, 29, lab, MONO, 10.5, t["ink3"], tracking=0.08)
        x -= 8 + 7
        tile(d, x, 21, 8, state, t, "signal", 3, 5)
        if state == "none":  # an unlit tile vanishes against the page; give it an edge
            d.rect(x + 0.5, 21.5, 7, 7, stroke=t["edge"])
        x -= 18
    swept = f'LAST SWEEP {last_t.strftime("%Y-%m-%d %H:%M UTC")}' if last_t else "AWAITING FIRST SWEEP"
    d.text(W, 57, swept, MONO, 10.5, t["ink3"], anchor="end", tracking=0.08)
    # column labels, aligned with the rows below
    y = 101
    d.text(COL_NAME, y, "SERVICE", MONO, 10, t["ink3"], tracking=0.14)
    d.text(COL_TEXT, y, "WHAT IT DOES", MONO, 10, t["ink3"], tracking=0.14)
    sx = strip_x(window)
    lab = f"LAST {days} DAYS"
    lw = d.text(sx, y, lab, MONO, 10, t["ink3"], tracking=0.14)
    nw = d.text(COL_RIGHT, y, "NOW", MONO, 10, t["ink3"], anchor="end", tracking=0.14)
    d.rect(sx + lw + 10, y - 3.5, COL_RIGHT - nw - 10 - (sx + lw + 10), 1, t["rule"] if theme == "light" else "#3a2413")
    return d


def describe(svc, rec, grid_row):
    state = rec["state"] if rec else "pending"
    line1, line2 = "", ""
    if rec:
        http = rec.get("http")
        ci = rec.get("ci")
        bits = []
        if http:
            if http.get("code"):
                bits.append(f'HTTP {http["code"]}' + (f' · {http["ms"]} MS' if http.get("ok") else ""))
            else:
                bits.append((http.get("error") or "no response").upper())
        if ci:
            verdict = {"success": "PASSED", "failure": "FAILED"}.get(ci["conclusion"], ci["conclusion"].upper())
            bits.append(f'RUN #{ci["run"]} {verdict}')
        line1 = " · ".join(bits)
        if state == "private":
            line1 = "SOURCE NOT PUBLIC YET"
        elif state == "unknown" and not bits:
            line1 = "GITHUB API DID NOT ANSWER"
        elif state == "idle" and not bits:
            line1 = f'LAST PUSH {rec["pushed"][:10]}' if rec.get("pushed") else "NO SCHEDULED RUNS"
    else:
        line1 = "WAITING FOR status.yml"
    if grid_row:
        seen = [s for s in grid_row if s in ("up", "down", "failing")]
        if len(seen) >= 4:
            up = sum(1 for s in seen if s == "up") / len(seen) * 100
            pct = "100" if up == 100 else f"{up:.1f}"
            line2 = f"7-DAY UPTIME {pct}%"
        elif seen:
            line2 = f"{len(seen)} SWEEP{'S' if len(seen) > 1 else ''} SO FAR"
    return state, line1, line2


def render_row(cfg, svc, rec, grid_row, theme, row_index) -> Doc:
    t = THEMES[theme]
    window = cfg["site"]["window"]
    H = 92
    state, line1, line2 = describe(svc, rec, grid_row)
    d = Doc(W, H, title=f'{svc["id"]}: {STATE_LABEL[state].lower()}')
    d.rect(0.5, 0.5, W - 1, H - 1, t["card"], rx=12, stroke=t["edge"])

    # lamp
    lx, ly, ls = 24, 26, 10
    palette = svc.get("palette", "signal")
    if state == "up":
        c = lit_color(palette, 7, row_index)
        d.defs.append('<filter id="g" x="-2" y="-2" width="5" height="5"><feGaussianBlur stdDeviation="3.2"/></filter>')
        d.css.append(".b{animation:b 3.6s ease-in-out infinite}@keyframes b{50%{opacity:.25}}"
                     "@media (prefers-reduced-motion:reduce){.b{animation:none}}")
        d.rect(lx, ly, ls, ls, c, extra=f'filter="url(#g)" opacity="{".75" if theme == "dark" else ".55"}" class="b"')
        d.rect(lx, ly, ls, ls, c)
    elif state in ("down", "failing"):
        d.rect(lx + 0.75, ly + 0.75, ls - 1.5, ls - 1.5, t["unlit"], stroke=t["down"], sw=1.5)
    else:
        d.rect(lx, ly, ls, ls, t["unlit"])

    # name + arrow when the row links somewhere
    nw = d.text(COL_NAME, 36, svc["id"], MONO_M, 15, t["ink"])
    if svc.get("_href"):
        arrow(d, COL_NAME + nw + 7, 35, 6.5, t["ink3"], sw=1.3)
    color = {"up": t["accent_ink"], "down": t["down"], "failing": t["down"]}.get(state, t["ink3"])
    d.text(COL_NAME, 58, STATE_LABEL[state], MONO_M, 10.5, color, tracking=0.1)

    # what it does
    width = strip_x(window) - 24 - COL_TEXT
    lines, cut = SANS.wrap(svc["summary"], 14, width, max_lines=2)
    if cut:
        warn(f'{svc["id"]}: summary is longer than two lines and was cut')
    for k, line in enumerate(lines):
        d.text(COL_TEXT, 35 + k * 20, line, SANS, 14, t["ink2"])
    tags = "  ·  ".join(svc.get("tags", []))
    tl, tcut = MONO.wrap(tags, 10.5, width, tracking=0.02, max_lines=1)
    d.text(COL_TEXT, 76, tl[0] if tl else "", MONO, 10.5, t["ink3"], tracking=0.02)

    # health strip
    sx = strip_x(window)
    row = grid_row or [None] * window
    for k, s in enumerate(row):
        st = s if s in ("up", "down", "failing") else "none"
        tile(d, sx + k * (STRIP_T + STRIP_GAP), 27, STRIP_T, st, t, palette, k, row_index)
    if line1:
        d.text(COL_RIGHT, 58, line1, MONO, 10.5, t["ink3"], anchor="end", tracking=0.06)
    if line2:
        d.text(COL_RIGHT, 76, line2, MONO, 10.5, t["ink3"], anchor="end", tracking=0.06)
    return d


# ---------------------------------------------------------------- shipped

def render_shipped(entries, theme, limit=6) -> Doc:
    t = THEMES[theme]
    dated = sorted((e for e in entries if e.get("date")), key=lambda e: e["date"], reverse=True)
    for e in entries:
        if not e.get("date"):
            warn(f'shipped: "{e["text"]}" ({e["service"]}) has no date yet, so it is not drawn')
    shown = dated[:limit]
    top, rh = 76, 34
    card_h = 10 + rh * len(shown) + (rh if len(dated) > limit else 0) + 4
    H = top + card_h
    d = Doc(W, H, title="Shipped")
    d.text(-SANS_M.lsb("S", 24) + 1, 30, "Shipped", SANS_M, 24, t["ink"], tracking=-0.01)
    d.text(1, 57, "Append-only. Newest first. Nothing gets edited out — same rule as the stores underneath the services above.",
           SANS, 14, t["ink2"])
    d.rect(0.5, top + 0.5, W - 1, card_h - 1, t["card"], rx=12, stroke=t["edge"])
    y = top + 10
    for k, e in enumerate(shown):
        base = y + 22
        if k:
            d.rect(24, y, W - 48, 1, t["rule"])
        d.text(24, base, "+", MONO_M, 13, t["accent_ink"])
        d.text(COL_NAME, base, e["service"], MONO_M, 12.5, t["ink"])
        dw = d.text(COL_RIGHT, base, e["date"], MONO, 11, t["ink3"], anchor="end", tracking=0.04)
        lines, cut = SANS.wrap(e["text"], 14, COL_RIGHT - dw - 28 - COL_TEXT, max_lines=1)
        if cut:
            warn(f'shipped: "{e["text"]}" is too long for one line and was cut')
        d.text(COL_TEXT, base, lines[0], SANS, 14, t["ink2"])
        y += rh
    if len(dated) > limit:
        d.rect(24, y, W - 48, 1, t["rule"])
        d.text(COL_NAME, y + 22, f"+ {len(dated) - limit} earlier in log/shipped.jsonl".upper(),
               MONO, 10.5, t["ink3"], tracking=0.08)
    return d, shown


# ---------------------------------------------------------------- stack

def render_stack(cfg, theme) -> Doc:
    t = THEMES[theme]
    groups = cfg.get("stack", [])
    top, rh = 76, 40
    card_h = 6 + rh * len(groups) + 6
    d = Doc(W, top + card_h, title="Stack")
    d.text(-SANS_M.lsb("S", 24) + 1, 30, "Stack", SANS_M, 24, t["ink"], tracking=-0.01)
    d.text(1, 57, cfg.get("stack_note", {}).get("text", ""), SANS, 14, t["ink2"])
    d.rect(0.5, top + 0.5, W - 1, card_h - 1, t["card"], rx=12, stroke=t["edge"])
    y = top + 6
    for k, g in enumerate(groups):
        if k:
            d.rect(24, y, W - 48, 1, t["rule"])
        base = y + 25.5
        d.text(COL_NAME, base - 0.5, g["label"].upper(), MONO, 10.5, t["ink3"], tracking=0.12)
        x = COL_TEXT
        for n, item in enumerate(g["items"]):
            if n:
                x += 11
                d.rect(x - 1.5, base - 5.5, 3, 3, t["accent"] if theme == "dark" else "#e0a35c")
                x += 12
            x += d.text(x, base, item, SANS, 14.5, t["ink"])
        if x > COL_RIGHT:
            warn(f'stack: "{g["label"]}" runs past the card; drop an item or split the group')
        y += rh
    return d


# ---------------------------------------------------------------- README

def asset_url(cfg, name: str, local: bool) -> str:
    data = (ASSETS / name).read_bytes()
    v = hashlib.sha256(data).hexdigest()[:10]
    if local:
        return f"assets/{name}"
    return f'https://raw.githubusercontent.com/{cfg["site"]["repo"]}/{cfg["site"]["branch"]}/assets/{name}?v={v}'


def picture(cfg, stem: str, alt: str, local: bool, width: str | None = "100%", height: int | None = None) -> str:
    size = (f' width="{width}"' if width else "") + (f' height="{height}"' if height else "")
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{asset_url(cfg, stem + "-dark.svg", local)}">'
            f'<img alt="{html.escape(alt, quote=True)}" src="{asset_url(cfg, stem + "-light.svg", local)}"{size}></picture>')


def replace_block(text: str, name: str, body: str) -> str:
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(text):
        warn(f"README.md has no {name} markers; skipped")
        return text
    return pat.sub(lambda m: m.group(1) + body + m.group(3), text)


def main():
    local = "--local" in sys.argv
    cfg, sweeps, shipped = load()
    ASSETS.mkdir(exist_ok=True)
    last_t, hist = history(cfg, sweeps)
    grid, latest = (hist.get("grid", {}), hist.get("latest", {})) if hist else ({}, {})
    p = cfg["person"]
    written = []

    def save(doc: Doc, name: str):
        if doc.save(ASSETS / name):
            written.append(name)

    save(render_hero(cfg), "hero.svg")
    for link in cfg.get("link", []):
        for th in THEMES:
            save(render_button(link, th), f'btn-{link["id"]}-{th}.svg')

    services = cfg.get("service", [])
    for svc in services:
        rec = latest.get(svc["id"])
        href = svc.get("link")
        if not href and svc.get("repo") and rec and rec.get("repo") == "public":
            href = f'https://github.com/{svc["repo"]}'
        svc["_href"] = href
    for th in THEMES:
        save(render_board_head(cfg, last_t, th), f"board-{th}.svg")
        for k, svc in enumerate(services):
            save(render_row(cfg, svc, latest.get(svc["id"]), grid.get(svc["id"]), th, k), f'svc-{svc["id"]}-{th}.svg')
        doc, shown = render_shipped(shipped, th)
        save(doc, f"shipped-{th}.svg")
        save(render_stack(cfg, th), f"stack-{th}.svg")

    # ---- README blocks
    readme_path = ROOT / "README.md"
    text = readme_path.read_text()
    hero_alt = (f'{p["name"]}, {p["eyebrow"].lower().replace(" · ", ", ")}. ' + " ".join(p["lede"]) +
                f' {p["status"].replace(" · ", ", ")}. {p["location"].replace(" · ", "; ")}.')
    hero_src = asset_url(cfg, "hero.svg", local)
    btns = []
    for link in cfg.get("link", []):
        btns.append(f'<a href="{html.escape(link["url"], quote=True)}">'
                    + picture(cfg, f'btn-{link["id"]}', link["label"], local, width=None, height=40) + "</a>")
    head = (f'\n<a href="{html.escape(p["portfolio"], quote=True)}"><img alt="{html.escape(hero_alt, quote=True)}" '
            f'src="{hero_src}" width="100%"></a>\n\n<p>\n' + "&nbsp;\n".join(btns) + "\n</p>\n")
    text = replace_block(text, "HERO", head)

    swept = last_t.strftime("%Y-%m-%d %H:%M UTC") if last_t else "awaiting first sweep"
    when = f"Last sweep {swept}." if last_t else "Waiting for the first sweep."
    rows = [picture(cfg, "board", f"Control plane: services I run, checked every six hours. {when}", local)]
    for svc in services:
        rec = latest.get(svc["id"])
        state, l1, l2 = describe(svc, rec, grid.get(svc["id"]))
        alt = f'{svc["id"]}: {STATE_LABEL[state].lower()}. {svc["summary"]} Tags: {", ".join(svc.get("tags", []))}.'
        extra = ". ".join(s.capitalize() for s in (l1.lower(), l2.lower()) if s)
        if extra and state != "private":
            alt += f" {extra}."
        pic = picture(cfg, f'svc-{svc["id"]}', alt, local)
        rows.append(f'<a href="{html.escape(svc["_href"], quote=True)}">{pic}</a>' if svc.get("_href") else pic)
    text = replace_block(text, "BOARD", "\n" + "\n".join(rows) + "\n")

    _, shown = render_shipped(shipped, "dark")
    alt = "Shipped, append-only, newest first: " + "; ".join(f'{e["date"]} {e["service"]}: {e["text"]}' for e in shown) + "."
    text = replace_block(text, "SHIPPED", "\n" + picture(cfg, "shipped", alt, local) + "\n")
    stack_alt = "Stack. " + " ".join(f'{g["label"]}: {", ".join(g["items"])}.' for g in cfg.get("stack", []))
    text = replace_block(text, "STACK", "\n" + picture(cfg, "stack", stack_alt, local) + "\n")
    text = replace_block(text, "UPDATED", swept)
    if readme_path.read_text() != text:
        readme_path.write_text(text)
        written.append("README.md")

    print(f"rendered {len(written)} changed file(s)" + (f": {', '.join(written)}" if written else ""))
    if WARNINGS:
        print(f"{len(WARNINGS)} warning(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
