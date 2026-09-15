"""
ภาพรูปทรงเรขาคณิตซ้อนกัน สำหรับโจทย์เชาวน์ปัญญา "นับรูปทรง"

วาดขึ้นเองทั้งหมดด้วยคณิตศาสตร์ ไม่ได้ลอกใบงานของใครมา

แนวคิดสำคัญ — ภาพสร้างจาก seed แบบเดิมทุกครั้ง (deterministic)
เซิร์ฟเวอร์จึงรู้จำนวนที่ถูกต้องได้โดยไม่ต้องเก็บตำแหน่งรูปเป็นร้อย ๆ ตัวลงฐานข้อมูล
เก็บแค่ seed สั้น ๆ ในช่อง icon ก็พอ

ผลลัพธ์เป็น SVG ที่แตะรูปทีละรูปได้ (แต่ละรูปอยู่ใน <g class="fsh" data-i="...">)
หน้าเด็กจึงทำเครื่องหมายทีละรูปได้เหมือนเอาดินสอวงบนกระดาษ
"""

from __future__ import annotations

import math
import random

W, H = 300, 340          # ขนาดผืนภาพ
PAD = 10                 # เว้นขอบไม่ให้รูปล้นออกนอกกรอบ
LINE = 2.6               # ความหนาเส้นขอบ เท่ากันทุกรูปเหมือนใบงาน

SHAPES = {
    "circle":   "วงกลม",
    "square":   "สี่เหลี่ยม",
    "triangle": "สามเหลี่ยม",
}

COLORS = {
    "red":   {"name": "แดง",    "hex": "#E0554B"},
    "blue":  {"name": "น้ำเงิน", "hex": "#3B8FD8"},
    "green": {"name": "เขียว",   "hex": "#4B9A5B"},
}

# ขนาดรูป (รัศมี) กับน้ำหนักการสุ่ม — รูปเล็กเยอะกว่ารูปใหญ่ ภาพจะได้ไม่ทึบ
SIZE_POOL = [16] * 4 + [22] * 4 + [28] * 3 + [36] * 2 + [46]

# ความหนาแน่นของภาพ (จำนวนรูปต่อคู่ ชนิด×สี)
DENSITY = {
    "easy": {"other": (1, 4), "target": (3, 6)},   # รวมราว 24 รูป
    "hard": {"other": (2, 6), "target": (4, 9)},   # รวมราว 40 รูป
}


def combos() -> list[tuple[str, str]]:
    """คู่ ชนิด×สี ทั้ง 9 แบบ"""
    return [(s, c) for s in SHAPES for c in COLORS]


def label(shape: str, color: str) -> str:
    """ชื่อไทยของเป้าหมาย เช่น "สามเหลี่ยมสีแดง" """
    s = SHAPES.get(shape, shape)
    c = COLORS.get(color, {}).get("name", color)
    return f"{s}สี{c}"


def _poly(points: list[tuple[float, float]]) -> str:
    head = "M %.1f %.1f" % points[0]
    rest = "".join(" L %.1f %.1f" % p for p in points[1:])
    return head + rest + " Z"


def _path_for(kind: str, cx: float, cy: float, r: float, angle: float) -> str:
    """เส้นรอบรูปของแต่ละชนิด — คืนเป็น path เดียวกันหมด โค้ดจะได้ไม่แตกเป็นหลายทาง"""
    if kind == "circle":
        return ("M %.1f %.1f a %.1f %.1f 0 1 0 %.1f 0 a %.1f %.1f 0 1 0 %.1f 0 Z"
                % (cx - r, cy, r, r, r * 2, r, r, -r * 2))

    if kind == "square":
        half = r * 0.80
        pts = []
        for base in (45, 135, 225, 315):
            t = math.radians(base + angle)
            d = half * math.sqrt(2)
            pts.append((cx + d * math.cos(t), cy + d * math.sin(t)))
        return _poly(pts)

    # สามเหลี่ยมด้านเท่า ยอดชี้ขึ้นก่อนแล้วค่อยหมุน
    pts = []
    for base in (-90, 30, 150):
        t = math.radians(base + angle)
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return _poly(pts)


def build(seed: int, level: str = "easy",
          target: tuple[str, str] | None = None) -> dict:
    """
    สร้างภาพหนึ่งใบ

    คืน {"svg": ..., "counts": {(shape,color): n}, "total": n}
    เรียกด้วย seed เดิมกี่ครั้งก็ได้ภาพเดิมเป๊ะ
    """
    rnd = random.Random(int(seed))
    rule = DENSITY.get(level, DENSITY["easy"])

    counts: dict[tuple[str, str], int] = {}
    for combo in combos():
        lo, hi = rule["target"] if combo == target else rule["other"]
        counts[combo] = rnd.randint(lo, hi)

    # เรียงลำดับการวางแบบสลับชนิดกันไป ไม่ใช่วางสีเดียวกันรวดเดียวจนแน่นมุมเดียว
    queue = [combo for combo, n in counts.items() for _ in range(n)]
    rnd.shuffle(queue)

    # แบ่งผืนภาพเป็นตาราง แล้วไล่วางทีละช่อง รูปจะได้กระจายทั่วทั้งภาพ
    # ไม่กระจุกอยู่ครึ่งบนแล้วเหลือที่ว่างโล่ง ๆ ครึ่งล่าง
    cols, rows = 4, 5
    cells = [(cx, cy) for cy in range(rows) for cx in range(cols)]
    anchors: list[tuple[int, int]] = []
    while len(anchors) < len(queue) + len(cells):
        batch = cells[:]
        rnd.shuffle(batch)
        anchors.extend(batch)

    def cell_point(cell: tuple[int, int], r: float) -> tuple[float, float]:
        cw, ch = W / cols, H / rows
        x = (cell[0] + rnd.uniform(0.15, 0.85)) * cw
        y = (cell[1] + rnd.uniform(0.15, 0.85)) * ch
        # ดึงกลับเข้ากรอบ ไม่ให้รูปใหญ่ล้นขอบ
        x = min(max(x, PAD + r), W - PAD - r)
        y = min(max(y, PAD + r), H - PAD - r)
        return x, y

    placed: list[dict] = []
    by_combo: dict[tuple[str, str], list[dict]] = {}
    ai = 0
    for kind, color in queue:
        same = by_combo.setdefault((kind, color), [])
        r = float(rnd.choice(SIZE_POOL))
        spot = None
        for attempt in range(24):
            # ผ่อนเกณฑ์ลงถ้าหาที่ว่างไม่ได้ เพื่อให้ได้ครบจำนวนเสมอ
            need = 0.85 if attempt < 16 else 0.60
            x, y = cell_point(anchors[ai], r)
            ai += 1
            if all(math.hypot(x - p["x"], y - p["y"]) >= (r + p["r"]) * need
                   for p in same):
                spot = (x, y)
                break
        if spot is None:
            spot = cell_point(anchors[ai], r)
            ai += 1
        item = {"kind": kind, "color": color, "x": spot[0], "y": spot[1],
                "r": r, "a": rnd.uniform(0, 360) if kind != "circle" else 0.0}
        placed.append(item)
        same.append(item)

    # รูปใหญ่วาดก่อน รูปเล็กวาดทีหลัง — รูปเล็กจะได้อยู่บนสุดและแตะโดนเสมอ
    placed.sort(key=lambda p: -p["r"])

    parts = ['<svg class="findsvg" viewBox="0 0 %d %d" '
             'xmlns="http://www.w3.org/2000/svg">' % (W, H),
             '<rect class="fs-paper" width="%d" height="%d" rx="14"/>' % (W, H),
             '<g class="fs-shapes">']
    for i, p in enumerate(placed):
        d = _path_for(p["kind"], p["x"], p["y"], p["r"], p["a"])
        hexc = COLORS[p["color"]]["hex"]
        parts.append(
            '<g class="fsh" data-i="%d" data-cx="%.1f" data-cy="%.1f" style="--c:%s">'
            '<path class="fs-bg" d="%s"/>'
            '<path class="fs-ln" d="%s"/>'
            '</g>' % (i, p["x"], p["y"], hexc, d, d))
    parts.append('</g><g class="fs-marks"></g></svg>')

    return {"svg": "".join(parts), "counts": counts, "total": len(placed)}


def spec(raw: str) -> dict | None:
    """
    อ่านโจทย์จากช่อง icon — รูปแบบ "seed|shape|color|level"

        "3140|triangle|red|easy"

    คืน None ถ้ารูปแบบไม่ถูกต้อง
    """
    parts = [p.strip() for p in (raw or "").split("|")]
    if len(parts) < 3:
        return None
    try:
        seed = int(parts[0])
    except ValueError:
        return None
    shape, color = parts[1], parts[2]
    if shape not in SHAPES or color not in COLORS:
        return None
    level = parts[3] if len(parts) > 3 and parts[3] in DENSITY else "easy"
    return {"seed": seed, "shape": shape, "color": color, "level": level}


def answer_of(raw: str) -> int | None:
    """จำนวนที่ถูกต้องของโจทย์นี้ — ใช้ตอนสร้างตัวเลือกและตอนตรวจ"""
    s = spec(raw)
    if not s:
        return None
    scene = build(s["seed"], s["level"], (s["shape"], s["color"]))
    return scene["counts"][(s["shape"], s["color"])]


def swatch(shape: str, color: str, size: int = 44) -> str:
    """
    รูปตัวอย่างเล็ก ๆ ของเป้าหมาย — เด็กอนุบาลที่ยังอ่านไม่ออกดูรูปนี้แล้วรู้ทันที
    ว่าต้องหาอะไร โดยไม่ต้องอ่านคำว่า "สามเหลี่ยมสีแดง"
    """
    r = size / 2 - 4
    d = _path_for(shape, size / 2, size / 2, r, 0)
    return ('<svg class="fs-swatch" viewBox="0 0 %d %d" width="%d" height="%d" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<path d="%s" fill="none" stroke="%s" stroke-width="3" '
            'stroke-linejoin="round"/></svg>'
            % (size, size, size, size, d, COLORS[color]["hex"]))


def scene_of(raw: str) -> dict | None:
    """ภาพ + ป้ายชื่อเป้าหมาย สำหรับส่งให้หน้าเว็บวาด (ไม่มีคำตอบติดไปด้วย)"""
    s = spec(raw)
    if not s:
        return None
    scene = build(s["seed"], s["level"], (s["shape"], s["color"]))
    return {
        "svg": scene["svg"],
        "swatch": swatch(s["shape"], s["color"]),
        "target": label(s["shape"], s["color"]),
        "shape": s["shape"],
        "color": s["color"],
        "hex": COLORS[s["color"]]["hex"],
        "total": scene["total"],
    }
