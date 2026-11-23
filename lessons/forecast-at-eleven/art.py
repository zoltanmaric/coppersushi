"""Copper Sushi day-ahead forecast lesson panels."""

from functools import lru_cache
from math import cos, pi, sin
from PIL import Image, ImageDraw, ImageFont

BG, PAPER, MINT = "#202222", "#edf0ed", "#16cba4"
MUTED, GRID, PURPLE, COPPER = "#bbc3bf", "#49524e", "#c69af5", "#efae7d"
TITLES = (
    "The forecast at eleven",
    "One quarter. Two prices.",
    "Rewind to the decision",
    "When did the data arrive?",
    "What changed by noon?",
    "Replay the decision",
)


@lru_cache
def font(size, bold):
    names = (
        ("Arial Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf")
        if bold
        else ("Arial.ttf", "DejaVuSans.ttf", "arial.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def label(d, x, y, value, size, color=PAPER, bold=False, anchor="lt"):
    d.text((x, y), value, font=font(size, bold), fill=color, anchor=anchor)


def ramp(p, start, end):
    t = min(1, max(0, (p - start) / (end - start)))
    return t * t * (3 - 2 * t)


def opening(d, p):
    label(d, 76, 229, "TODAY  /  GERMAN TIME", 25, MINT, True)
    label(d, 67, 283, "11:00", 161, PAPER, True)
    label(d, 78, 489, "What price can you forecast", 40)
    label(d, 78, 544, "for tomorrow at 18:00?", 40)
    cx, cy, radius = 965, 375, 167
    for i in range(60):
        a = i * pi / 30 - pi / 2
        major = i % 5 == 0
        length = 18 if major else 7
        d.line(
            [
                (cx + (radius - length) * cos(a), cy + (radius - length) * sin(a)),
                (cx + radius * cos(a), cy + radius * sin(a)),
            ],
            fill=MUTED if major else GRID,
            width=4 if major else 2,
        )
    for a, length, color in ((pi / 2, 120, MINT), (-pi / 2, 86, PAPER)):
        d.line(
            (cx, cy, cx + length * cos(a), cy - length * sin(a)), fill=color, width=8
        )
    d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=MINT)
    label(d, cx, 583, "TOMORROW  /  18:00–18:15", 24, MUTED, True, "mt")


def frame(scene: int, progress: float) -> Image.Image:
    image = Image.new("RGB", (1280, 720), BG)
    d = ImageDraw.Draw(image)
    label(d, 76, 44, "COPPER SUSHI", 26, MINT, True)
    label(d, 1203, 45, "DAY-AHEAD FORECASTING", 21, MUTED, True, "rt")
    d.line((76, 90, 1204, 90), fill=GRID, width=2)
    label(d, 73, 122, TITLES[scene], 65, PAPER, True)
    opening(d, progress) if scene == 0 else detail(d, scene, progress)
    return image


def footer(d, text):
    d.line((76, 602, 1204, 602), fill=GRID, width=2)
    label(d, 76, 627, text, 30)


def timeline(d, start=130, end=1150, y=430):
    d.line((start, y, end, y), fill=GRID, width=4)
    for i in range(21):
        x = start + (end - start) * i / 20
        d.line((x, y, x, y + (12 if i % 5 == 0 else 6)), fill=GRID, width=2)


def dot(d, x, y, color):
    d.ellipse((x - 10, y - 10, x + 10, y + 10), fill=color)


def editions(d, scene, p):
    label(d, 76, 229, "KPLER  /  ILLUSTRATIVE EDITIONS", 25, MUTED, True)
    label(d, 1204, 229, "TOMORROW  /  18:00–18:15", 25, MUTED, True, "rt")
    timeline(d)
    show_new = scene == 2 or p >= 0.42
    gate = int(1070 - 402 * ramp(p, 0.04, 0.48)) if scene == 2 else None
    for x, price, at in ((250, "€80", "10:36"), (947, "€65", "11:16")):
        if x > 900 and not show_new:
            continue
        color = MINT if gate is None or x <= gate else MUTED
        label(d, x, 300, price, 82, color, True, "mt")
        d.line((x, 385, x, 430), fill=color, width=3)
        dot(d, x, 430, color)
        label(d, x, 460, at, 48, color, True, "mt")
    if gate is not None:
        d.line((gate, 294, gate, 514), fill=COPPER, width=5)
        label(
            d,
            gate,
            541,
            "11:00 cutoff" if p >= 0.48 else "Rewinding",
            32,
            COPPER,
            True,
            "mt",
        )
    footer(
        d,
        "At 11:00, the latest available price was €80/MWh."
        if scene == 2 and p >= 0.48
        else "Both prices refer to the same 15 minutes of delivery.",
    )


def wind(d, p):
    label(d, 76, 231, "WIND FORECAST  /  ILLUSTRATIVE ARRIVAL", 25, MUTED, True)
    timeline(d)
    cutoff = 850
    d.line((cutoff, 300, cutoff, 521), fill=COPPER, width=4)
    label(d, cutoff, 542, "11:00 cutoff", 31, COPPER, True, "mt")
    for x, term, at, color in (
        (250, "ISSUED", "10:50", PAPER),
        (1030, "RECEIVED", "11:03", PURPLE),
    ):
        if term == "RECEIVED" and p < 0.50:
            continue
        label(d, x, 318, term, 24, color, True, "mt")
        label(d, x, 361, at, 49, color, True, "mt")
        dot(d, x, 430, color)
    end = 250 + 780 * ramp(p, 0.13, 0.50)
    d.line((250, 430, end, 430), fill=PURPLE, width=5)
    dot(d, end, 430, PURPLE)
    footer(
        d,
        "Three minutes late. Exclude this edition from the 11:00 replay."
        if p >= 0.50
        else "The provider issued the forecast at 10:50.",
    )


def scores(d, p):
    label(d, 76, 224, "ENERGY-ARENA  /  EISER", 25, MINT, True)
    label(d, 1204, 224, "2–8 OCTOBER 2026", 25, MUTED, True, "rt")
    label(d, 76, 284, "Weighted interval score (€/MWh)", 36)
    for y, time, value, k, color in (
        (384, "11:00", 11.44, ramp(p, 0.02, 0.3), MINT),
        (486, "Noon", 7.16, ramp(p, 0.45, 0.71), PURPLE),
    ):
        label(d, 76, y + 2, time, 43, PAPER, True)
        length = 650 * value / 11.44 * k
        if length:
            d.rectangle((273, y, 273 + length, y + 47), fill=color)
            label(d, 290 + length, y + 2, f"{value:.2f}", 42, color, True)
    footer(d, "Same 672 delivery quarters. A lower score is better.")


def exercise(d, p):
    label(d, 76, 229, "HANDS-ON  /  LOCAL REPLAY", 25, MINT, True)
    for y, time, price, shown in (
        (306, "11:00", "€80", p > 0.22),
        (459, "11:20", "€65", p > 0.60),
    ):
        label(d, 78, y, "python replay.py " + time, 49, PAPER, True)
        if shown:
            label(d, 890, y - 6, price, 62, MINT, True)
            label(d, 1044, y + 17, "/MWh", 30, MUTED)
        d.line((76, y + 88, 1204, y + 88), fill=GRID, width=2)
    footer(d, "Move the cutoff. Which edition becomes available?")


def detail(d, scene, p):
    if scene in (1, 2):
        editions(d, scene, p)
    elif scene == 3:
        wind(d, p)
    elif scene == 4:
        scores(d, p)
    elif scene == 5:
        exercise(d, p)
