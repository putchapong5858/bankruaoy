# -*- coding: utf-8 -*-
"""
ฉากให้เด็กแตะหาของในภาพ และตัวการ์ตูนให้แตะชี้อวัยวะ
(โจทย์ชนิด "tapscene")

แนวคิด
    ฉากหนึ่ง = ภาพพื้นหลังวาดด้วย SVG + ของในฉากหลายชิ้น ชิ้นละ 1 จุดแตะ
    โจทย์ 1 ข้อ = ฉากหนึ่ง + ของ 1 ชิ้นที่เป็นคำตอบ
    เก็บไว้ในคอลัมน์ icon เป็น "ฉาก|ชิ้นที่ถูก" เช่น "bedroom|toothbrush"
    จึงไม่ต้องเพิ่มตารางหรือคอลัมน์ในฐานข้อมูลเลย

ความปลอดภัยของเฉลย
    ภาพที่ส่งให้เบราว์เซอร์มี "ของทุกชิ้น" เท่า ๆ กัน ไม่มีเครื่องหมายว่าชิ้นไหนถูก
    การตรวจยังทำที่เซิร์ฟเวอร์เหมือนโจทย์เลือกตอบปกติ (ชิ้นที่แตะ = ตัวเลือกที่เลือก)

หมายเหตุเรื่องการแตะของเด็กเล็ก
    - จุดแตะทุกจุดกว้างอย่างน้อย ~84px บนภาพขนาดจริง (นิ้วเด็กอนุบาลกดติดแน่)
    - ของที่มีเป็นคู่ (ตา หู มือ เท้า) นับเป็นจุดแตะเดียวกัน แตะข้างไหนก็ได้
      ไม่ใช่ว่ากดข้างซ้ายแล้วเงียบ ซึ่งเด็กจะคิดว่าเครื่องเสีย
"""

# ── ชิ้นของในฉาก: (คีย์, คำไทย, อีโมจิ, x, y) ──────────────
# พิกัดอยู่บนผืนผ้าใบ 640 x 420 วางให้ห่างกันอย่างน้อย 96px

PLACES: dict[str, dict] = {
    "bedroom": {
        "name": "ในห้องนอน",
        "bg": "room",
        "items": [
            ("bed",        "เตียง",     "🛏️", 120, 300),
            ("sock",       "ถุงเท้า",    "🧦", 268, 300),
            ("clock",      "นาฬิกา",    "⏰", 120, 170),
            ("book",       "หนังสือ",   "📕", 268, 170),
            ("teddy",      "ตุ๊กตาหมี", "🧸", 416, 300),
            ("shirt",      "เสื้อ",      "👕", 416, 170),
            ("lamp",       "หลอดไฟ",    "💡", 556, 170),
            ("toothbrush", "แปรงสีฟัน", "🪥", 556, 300),
        ],
    },
    "kitchen": {
        "name": "ในห้องครัว",
        "bg": "room",
        "items": [
            ("plate", "จาน",    "🍽️", 120, 170),
            ("glass", "แก้วน้ำ", "🥛", 268, 170),
            ("spoon", "ช้อน",   "🥄", 416, 170),
            ("pan",   "กระทะ",  "🍳", 556, 170),
            ("rice",  "ข้าว",    "🍚", 120, 300),
            ("egg",   "ไข่",     "🥚", 268, 300),
            ("kettle", "กาน้ำ",  "🫖", 416, 300),
            ("banana", "กล้วย",  "🍌", 556, 300),
        ],
    },
    "classroom": {
        "name": "ในห้องเรียน",
        "bg": "room",
        "items": [
            ("pencil",   "ดินสอ",      "✏️", 120, 170),
            ("book",     "หนังสือ",    "📕", 268, 170),
            ("scissors", "กรรไกร",     "✂️", 416, 170),
            ("ruler",    "ไม้บรรทัด",  "📏", 556, 170),
            ("bag",      "กระเป๋า",     "🎒", 120, 300),
            ("crayon",   "สีเทียน",     "🖍️", 268, 300),
            ("chair",    "เก้าอี้",      "🪑", 416, 300),
            ("bin",      "ถังขยะ",      "🗑️", 556, 300),
        ],
    },
    "market": {
        "name": "ที่ตลาด",
        "bg": "market",
        "items": [
            ("apple",      "แอปเปิล",   "🍎", 120, 186),
            ("banana",     "กล้วย",      "🍌", 268, 186),
            ("watermelon", "แตงโม",     "🍉", 416, 186),
            ("mango",      "มะม่วง",     "🥭", 556, 186),
            ("carrot",     "แครอท",      "🥕", 120, 316),
            ("tomato",     "มะเขือเทศ",  "🍅", 268, 316),
            ("fish",       "ปลา",        "🐟", 416, 316),
            ("egg",        "ไข่",         "🥚", 556, 316),
        ],
    },
    "playground": {
        "name": "ที่สนามเด็กเล่น",
        "bg": "outdoor",
        "items": [
            ("sun",       "พระอาทิตย์", "☀️", 120, 128),
            ("bird",      "นก",          "🐦", 268, 128),
            ("kite",      "ว่าว",         "🪁", 416, 128),
            ("butterfly", "ผีเสื้อ",      "🦋", 556, 128),
            ("ball",      "ลูกบอล",      "⚽", 120, 300),
            ("tree",      "ต้นไม้",       "🌳", 268, 300),
            ("flower",    "ดอกไม้",      "🌸", 416, 300),
            ("bicycle",   "รถจักรยาน",   "🚲", 556, 300),
        ],
    },
    "farm": {
        "name": "ที่ฟาร์ม",
        "bg": "outdoor",
        "items": [
            ("bird",   "นก",       "🐦", 120, 128),
            ("cloud",  "ก้อนเมฆ",  "☁️", 268, 128),
            ("tree",   "ต้นไม้",    "🌳", 416, 128),
            ("sun",    "พระอาทิตย์", "☀️", 556, 128),
            ("chicken", "ไก่",      "🐔", 120, 300),
            ("cow",    "วัว",       "🐮", 268, 300),
            ("pig",    "หมู",       "🐷", 416, 300),
            ("duck",   "เป็ด",      "🦆", 556, 300),
        ],
    },
    "bathroom": {
        "name": "ในห้องน้ำ",
        "bg": "tile",
        "items": [
            ("toothbrush", "แปรงสีฟัน",   "🪥", 120, 170),
            ("soap",       "สบู่",         "🧼", 268, 170),
            ("shampoo",    "แชมพู",       "🧴", 416, 170),
            ("mask",       "หน้ากากอนามัย", "😷", 556, 170),
            ("sponge",     "ฟองน้ำ",      "🧽", 120, 300),
            ("tissue",     "กระดาษชำระ",   "🧻", 268, 300),
            ("bucket",     "ถังน้ำ",       "🪣", 416, 300),
            ("shower",     "ฝักบัว",       "🚿", 556, 300),
        ],
    },
}

# ── ตัวการ์ตูนให้แตะชี้อวัยวะ ────────────────────────────
# จุดแตะเป็นวงรี วางทับบนรูปที่วาดไว้ ของที่มีเป็นคู่รวมเป็นจุดเดียว
# รูปแบบ: (คีย์, คำไทย, [รูปทรงจุดแตะ...])  รูปทรง = ("circle", cx, cy, r)
#                                                หรือ ("ellipse", cx, cy, rx, ry)

BODY_PARTS: list[tuple[str, str, list[tuple]]] = [
    ("hair",     "ผม",   [("ellipse", 170, 54, 64, 30)]),
    ("eye",      "ตา",   [("circle", 146, 86, 20), ("circle", 194, 86, 20)]),
    ("ear",      "หู",   [("circle", 94, 96, 21), ("circle", 246, 96, 21)]),
    ("nose",     "จมูก", [("circle", 170, 106, 18)]),
    ("mouth",    "ปาก",  [("ellipse", 170, 136, 26, 15)]),
    ("neck",     "คอ",   [("ellipse", 170, 172, 24, 15)]),
    ("shoulder", "ไหล่", [("circle", 118, 200, 22), ("circle", 222, 200, 22)]),
    ("arm",      "แขน",  [("circle", 80, 268, 26), ("circle", 260, 268, 26)]),
    ("hand",     "มือ",  [("circle", 66, 340, 24), ("circle", 274, 340, 24)]),
    ("tummy",    "ท้อง", [("circle", 170, 262, 38)]),
    ("knee",     "เข่า", [("circle", 138, 392, 22), ("circle", 202, 392, 22)]),
    ("foot",     "เท้า", [("ellipse", 134, 462, 30, 17),
                          ("ellipse", 206, 462, 30, 17)]),
]

# ── ภาพตัดให้เห็นอวัยวะภายใน (วิทยาศาสตร์ ป.1 เรื่องร่างกายของเรา) ──
# วางจุดแตะให้ห่างกันพอ ไม่ให้วงทับกันจนเด็กกดอวัยวะหนึ่งแล้วไปโดนอีกอวัยวะ
ORGAN_PARTS: list[tuple[str, str, list[tuple]]] = [
    ("brain",     "สมอง",         [("ellipse", 170, 76, 38, 28)]),
    ("lung",      "ปอด",          [("circle", 128, 228, 27),
                                   ("circle", 212, 228, 27)]),
    ("heart",     "หัวใจ",        [("circle", 170, 276, 25)]),
    ("stomach",   "กระเพาะอาหาร", [("circle", 126, 326, 24)]),
    ("intestine", "ลำไส้",         [("ellipse", 171, 362, 31, 24)]),
    ("bone",      "กระดูก",       [("circle", 138, 440, 24),
                                   ("circle", 202, 440, 24)]),
]

BODY = {"name": "ตัวหนู (ชี้อวัยวะ)", "bg": "body",
        "items": [(k, th, "", 0, 0) for k, th, _s in BODY_PARTS]}
ORGANS = {"name": "อวัยวะภายในของเรา", "bg": "organs",
          "items": [(k, th, "", 0, 0) for k, th, _s in ORGAN_PARTS]}

SCENES: dict[str, dict] = {**PLACES, "body": BODY, "organs": ORGANS}

# ─────────────────────────── พื้นหลัง ───────────────────────────

def _bg_room() -> str:
    """ห้องในบ้าน — ผนังอ่อน พื้นไม้ มีหน้าต่างให้รู้ว่าเป็นห้อง"""
    dots = "".join(
        '<circle cx="%d" cy="%d" r="3.4" fill="#F0E2C8"/>' % (x, y)
        for y in range(70, 330, 64) for x in range(36, 640, 64))
    return (
        '<rect x="0" y="0" width="640" height="420" fill="#FFFBF2"/>'
        + dots +
        '<rect x="0" y="330" width="640" height="90" fill="#F2E2CB"/>'
        '<path d="M0,330 H640" stroke="#E0CBAC" stroke-width="4"/>'
        '<path d="M0,352 H640" stroke="#E8D5B8" stroke-width="2"/>'
    )


def _bg_market() -> str:
    """ตลาด — ผ้าใบกันแดดลายทางด้านบน แผงวางของ 2 ชั้น"""
    stripes = "".join(
        '<rect x="%d" y="0" width="40" height="42" fill="%s"/>'
        % (x, "#F8C9C0" if (x // 40) % 2 == 0 else "#FFF1E8")
        for x in range(0, 640, 40))
    return (
        '<rect x="0" y="0" width="640" height="420" fill="#FFFCF5"/>'
        + stripes +
        '<path d="M0,42 H640" stroke="#EBB3A6" stroke-width="4"/>'
        '<rect x="24" y="232" width="592" height="18" rx="9" fill="#E7D3B4"/>'
        '<rect x="24" y="362" width="592" height="18" rx="9" fill="#E7D3B4"/>'
    )


def _bg_outdoor() -> str:
    """นอกบ้าน — ท้องฟ้า เนินหญ้า"""
    return (
        '<rect x="0" y="0" width="640" height="420" fill="#EAF6FE"/>'
        '<path d="M0,250 Q160,206 320,250 T640,250 V420 H0 Z" fill="#DEF2D7"/>'
        '<path d="M0,250 Q160,206 320,250 T640,250" stroke="#BFE2B3" '
        'stroke-width="4" fill="none"/>'
        '<g opacity=".55" fill="#FFFFFF">'
        '<ellipse cx="96" cy="60" rx="46" ry="22"/>'
        '<ellipse cx="136" cy="52" rx="34" ry="18"/>'
        '<ellipse cx="470" cy="76" rx="40" ry="19"/>'
        '</g>'
    )


def _bg_body() -> str:
    """ตัวการ์ตูนเด็ก วาดเอง ไม่ติดลิขสิทธิ์ใคร — สมมาตรรอบแกน x=170"""
    skin, line, cloth = "#FBDCC4", "#C98F62", "#7FC4E8"
    return (
        '<rect x="0" y="0" width="340" height="500" fill="#FFFDF8"/>'
        # ขา
        f'<path d="M148,330 V452" stroke="{skin}" stroke-width="34" '
        'stroke-linecap="round"/>'
        f'<path d="M192,330 V452" stroke="{skin}" stroke-width="34" '
        'stroke-linecap="round"/>'
        f'<path d="M148,330 V452" stroke="{line}" stroke-width="2" '
        'stroke-linecap="round" fill="none" opacity=".35"/>'
        # เท้า
        f'<ellipse cx="134" cy="462" rx="30" ry="17" fill="{skin}" '
        f'stroke="{line}" stroke-width="2.4"/>'
        f'<ellipse cx="206" cy="462" rx="30" ry="17" fill="{skin}" '
        f'stroke="{line}" stroke-width="2.4"/>'
        # ลำตัว (เสื้อ)
        f'<rect x="112" y="186" width="116" height="150" rx="34" fill="{cloth}" '
        'stroke="#5AA8D0" stroke-width="2.6"/>'
        # แขน
        f'<path d="M118,206 L74,330" stroke="{skin}" stroke-width="30" '
        'stroke-linecap="round"/>'
        f'<path d="M222,206 L266,330" stroke="{skin}" stroke-width="30" '
        'stroke-linecap="round"/>'
        # มือ
        f'<circle cx="66" cy="340" r="22" fill="{skin}" stroke="{line}" '
        'stroke-width="2.4"/>'
        f'<circle cx="274" cy="340" r="22" fill="{skin}" stroke="{line}" '
        'stroke-width="2.4"/>'
        # คอ
        f'<rect x="156" y="152" width="28" height="42" rx="12" fill="{skin}" '
        f'stroke="{line}" stroke-width="2.4"/>'
        # หู
        f'<circle cx="94" cy="96" r="19" fill="{skin}" stroke="{line}" '
        'stroke-width="2.6"/>'
        f'<circle cx="246" cy="96" r="19" fill="{skin}" stroke="{line}" '
        'stroke-width="2.6"/>'
        # หัว
        f'<circle cx="170" cy="100" r="66" fill="{skin}" stroke="{line}" '
        'stroke-width="2.8"/>'
        # ผม
        '<path d="M104,88 Q112,24 170,24 Q228,24 236,88 Q212,62 170,62 '
        'Q128,62 104,88 Z" fill="#53382A"/>'
        # ตา จมูก ปาก
        '<circle cx="146" cy="88" r="7.5" fill="#3B2C22"/>'
        '<circle cx="194" cy="88" r="7.5" fill="#3B2C22"/>'
        '<circle cx="148.6" cy="85.4" r="2.4" fill="#FFFFFF"/>'
        '<circle cx="196.6" cy="85.4" r="2.4" fill="#FFFFFF"/>'
        f'<path d="M166,104 Q170,112 174,104" stroke="{line}" stroke-width="2.8" '
        'fill="none" stroke-linecap="round"/>'
        '<path d="M154,128 Q170,144 186,128" stroke="#C4625C" stroke-width="3.4" '
        'fill="none" stroke-linecap="round"/>'
        # แก้มชมพูให้ดูเป็นมิตร
        '<circle cx="130" cy="112" r="9" fill="#F7B6B0" opacity=".7"/>'
        '<circle cx="210" cy="112" r="9" fill="#F7B6B0" opacity=".7"/>'
    )


def _bg_tile() -> str:
    """ห้องน้ำ — ผนังกระเบื้องสี่เหลี่ยม พื้นเปียกเล็กน้อย"""
    grid = "".join(
        f'<path d="M{x},0 V330" stroke="#DCEAF2" stroke-width="3"/>'
        for x in range(0, 641, 80))
    grid += "".join(
        f'<path d="M0,{y} H640" stroke="#DCEAF2" stroke-width="3"/>'
        for y in range(0, 331, 66))
    return ('<rect x="0" y="0" width="640" height="420" fill="#F4FBFE"/>'
            + grid +
            '<rect x="0" y="330" width="640" height="90" fill="#DFF0F7"/>'
            '<path d="M0,330 H640" stroke="#BCDBE8" stroke-width="4"/>'
            '<g opacity=".5" fill="#BCDBE8">'
            '<ellipse cx="120" cy="392" rx="52" ry="11"/>'
            '<ellipse cx="420" cy="400" rx="66" ry="12"/></g>')


def _bg_organs() -> str:
    """ภาพตัดให้เห็นอวัยวะภายใน วาดเองทั้งหมด ไม่ติดลิขสิทธิ์ใคร
    วาดแบบการ์ตูนใสคล้ายรูปในหนังสือเรียน ไม่ใช่ภาพกายวิภาคจริง
    เพื่อให้เด็ก ป.1 ดูแล้วไม่ตกใจ · ตำแหน่งอวัยวะวางตามรูปในหนังสือ
    (กระเพาะอาหารอยู่ใต้หัวใจค่อนไปทางซ้ายของภาพ ลำไส้อยู่ล่างสุด)"""
    skin, line, bone = "#FBDCC4", "#C98F62", "#F4F1E4"
    ribs = "".join(
        f'<path d="M126,{y} q44,-12 88,0" stroke="{bone}" stroke-width="10" '
        f'fill="none" stroke-linecap="round"/>'
        f'<path d="M126,{y} q44,-12 88,0" stroke="#CFC6AA" stroke-width="2" '
        f'fill="none" stroke-linecap="round" opacity=".8"/>'
        for y in (206, 228, 250, 272))
    return (
        '<rect x="0" y="0" width="340" height="520" fill="#FFFDF8"/>'
        # ── ขา พร้อมกระดูกขาที่เห็นชัด ──
        f'<path d="M138,392 V474" stroke="{skin}" stroke-width="46" '
        'stroke-linecap="round"/>'
        f'<path d="M202,392 V474" stroke="{skin}" stroke-width="46" '
        'stroke-linecap="round"/>'
        + "".join(
            f'<g><path d="M{x},404 V470" stroke="{bone}" stroke-width="20" '
            f'stroke-linecap="round"/>'
            f'<path d="M{x},404 V470" stroke="#BDB49A" stroke-width="2.6" '
            f'fill="none"/>'
            f'<circle cx="{x}" cy="404" r="12" fill="{bone}" '
            f'stroke="#BDB49A" stroke-width="2.6"/>'
            f'<circle cx="{x}" cy="470" r="12" fill="{bone}" '
            f'stroke="#BDB49A" stroke-width="2.6"/></g>' for x in (138, 202))
        + f'<ellipse cx="132" cy="492" rx="28" ry="15" fill="{skin}" '
          f'stroke="{line}" stroke-width="2.4"/>'
          f'<ellipse cx="208" cy="492" rx="28" ry="15" fill="{skin}" '
          f'stroke="{line}" stroke-width="2.4"/>'
        # ── แขน ──
        f'<path d="M112,206 L74,330" stroke="{skin}" stroke-width="28" '
        'stroke-linecap="round"/>'
        f'<path d="M228,206 L266,330" stroke="{skin}" stroke-width="28" '
        'stroke-linecap="round"/>'
        f'<circle cx="68" cy="340" r="20" fill="{skin}" stroke="{line}" '
        'stroke-width="2.4"/>'
        f'<circle cx="272" cy="340" r="20" fill="{skin}" stroke="{line}" '
        'stroke-width="2.4"/>'
        # ── ลำตัวแบบใส + ซี่โครง ──
        f'<rect x="98" y="176" width="144" height="224" rx="42" '
        f'fill="#FDF0E4" stroke="{line}" stroke-width="3"/>'
        + ribs +
        # ── ปอด ──
        '<path d="M130,198 q20,4 20,28 v28 q0,24 -22,24 q-20,0 -20,-26 '
        'v-30 q0,-24 22,-24 Z" fill="#F6B8B0" stroke="#C4625C" '
        'stroke-width="4" stroke-linejoin="round"/>'
        '<path d="M210,198 q-20,4 -20,28 v28 q0,24 22,24 q20,0 20,-26 '
        'v-30 q0,-24 -22,-24 Z" fill="#F6B8B0" stroke="#C4625C" '
        'stroke-width="4" stroke-linejoin="round"/>'
        '<path d="M130,214 v52 M210,214 v52" stroke="#DC8F87" '
        'stroke-width="3" opacity=".7"/>'
        # ── หัวใจ ──
        '<path d="M170,296 q-27,-17 -27,-34 a13.5,13.5 0 0,1 27,-7 '
        'a13.5,13.5 0 0,1 27,7 q0,17 -27,34 Z" fill="#E2574C" '
        'stroke="#A8322A" stroke-width="4" stroke-linejoin="round"/>'
        # ── กระเพาะอาหาร (ถุงรูปถั่ว มีหลอดอาหารเข้าด้านบน) ──
        '<path d="M124,294 v12 q-20,8 -20,24 q0,22 24,24 q20,2 24,-14 '
        'q3,-12 -5,-20" fill="#F3907E" stroke="#AE4435" stroke-width="4" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        '<path d="M110,322 q18,8 34,0" stroke="#C9604F" stroke-width="3" '
        'fill="none" opacity=".6"/>'
        # ── ลำไส้ (ลำไส้ใหญ่เป็นกรอบ ลำไส้เล็กขดอยู่ข้างใน) ──
        '<path d="M148,384 V344 q0,-10 10,-10 h26 q10,0 10,10 v40" '
        'fill="none" stroke="#E8927C" stroke-width="13" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M158,362 q14,-7 28,0 q13,7 0,13 q-14,6 -28,0 '
        'q-12,-6 0,-13 Z" fill="none" stroke="#F6B9A6" stroke-width="8"/>'
        # ── คอ + หัว ──
        f'<rect x="156" y="150" width="28" height="36" rx="12" fill="{skin}" '
        f'stroke="{line}" stroke-width="2.4"/>'
        f'<circle cx="170" cy="96" r="62" fill="{skin}" stroke="{line}" '
        'stroke-width="2.8"/>'
        # ── สมอง (อยู่ครึ่งบนของศีรษะ เหลือที่ให้หน้าตา) ──
        '<path d="M136,78 q0,-30 34,-30 q34,0 34,30 q0,24 -34,24 '
        'q-34,0 -34,-24 Z" fill="#F6AFC2" stroke="#C4607C" '
        'stroke-width="4" stroke-linejoin="round"/>'
        '<path d="M170,50 V100 M144,62 q26,9 52,0 M142,84 q28,10 56,0" '
        'stroke="#C4607C" stroke-width="3" fill="none" opacity=".75"/>'
        # ── หน้าตา ──
        '<circle cx="152" cy="124" r="5.5" fill="#3B2C22"/>'
        '<circle cx="188" cy="124" r="5.5" fill="#3B2C22"/>'
        '<path d="M160,142 q10,9 20,0" stroke="#C4625C" stroke-width="3" '
        'fill="none" stroke-linecap="round"/>'
        '<circle cx="134" cy="132" r="7" fill="#F7B6B0" opacity=".65"/>'
        '<circle cx="206" cy="132" r="7" fill="#F7B6B0" opacity=".65"/>'
    )


_BGS = {"room": _bg_room, "market": _bg_market, "outdoor": _bg_outdoor,
        "tile": _bg_tile, "body": _bg_body, "organs": _bg_organs}

# ฉากที่เป็น "รูปวาด" ไม่ใช่ฉากวางอีโมจิ — จุดแตะเป็นรูปทรงทับบนภาพ
FIGURES = {
    "body":   {"vb": "0 0 340 500", "bg": _bg_body},
    "organs": {"vb": "0 0 340 520", "bg": _bg_organs},
}


# ─────────────────────────── สร้างภาพ ───────────────────────────

def _spot(key: str, inner: str) -> str:
    return '<g class="tsp" data-key="%s">%s</g>' % (key, inner)


def _place_svg(scene: dict) -> str:
    """ฉากของจริง — อีโมจิชิ้นใหญ่ ๆ มีวงกลมใสเป็นพื้นที่กด"""
    parts = ['<svg class="tsvg" viewBox="0 0 640 420" '
             'xmlns="http://www.w3.org/2000/svg" role="img">',
             _BGS[scene["bg"]]()]
    for key, _th, emo, x, y in scene["items"]:
        inner = (
            '<circle class="ts-pad" cx="%d" cy="%d" r="46"/>'
            '<text class="ts-emo" x="%d" y="%d" text-anchor="middle" '
            'dominant-baseline="central">%s</text>'
            '<circle class="ts-ring" cx="%d" cy="%d" r="46"/>'
            '<g class="ts-mark" transform="translate(%d,%d)">'
            '<circle class="ts-mdot" r="15"/>'
            '<text class="ts-mtxt" text-anchor="middle" '
            'dominant-baseline="central"></text></g>'
            % (x, y, x, y, emo, x, y, x + 36, y - 36)
        )
        parts.append(_spot(key, inner))
    parts.append("</svg>")
    return "".join(parts)


def _figure_svg(scene_key: str) -> str:
    """ฉากที่เป็นรูปวาด — ตัวหนู หรือ ภาพอวัยวะภายใน"""
    f = FIGURES[scene_key]
    partlist = BODY_PARTS if scene_key == "body" else ORGAN_PARTS
    parts = [f'<svg class="tsvg body" viewBox="{f["vb"]}" '
             'xmlns="http://www.w3.org/2000/svg" role="img">',
             f["bg"]()]
    for key, _th, shapes_ in partlist:
        inner = []
        last = shapes_[-1]
        for sh in shapes_:
            if sh[0] == "circle":
                _t, cx, cy, r = sh
                inner.append('<circle class="ts-pad" cx="%s" cy="%s" r="%s"/>'
                             % (cx, cy, r))
                inner.append('<circle class="ts-ring" cx="%s" cy="%s" r="%s"/>'
                             % (cx, cy, r))
            else:
                _t, cx, cy, rx, ry = sh
                inner.append('<ellipse class="ts-pad" cx="%s" cy="%s" rx="%s" '
                             'ry="%s"/>' % (cx, cy, rx, ry))
                inner.append('<ellipse class="ts-ring" cx="%s" cy="%s" rx="%s" '
                             'ry="%s"/>' % (cx, cy, rx, ry))
        mx, my = last[1], last[2]
        inner.append('<g class="ts-mark" transform="translate(%s,%s)">'
                     '<circle class="ts-mdot" r="14"/>'
                     '<text class="ts-mtxt" text-anchor="middle" '
                     'dominant-baseline="central"></text></g>'
                     % (mx + 26, my - 24))
        parts.append(_spot(key, "".join(inner)))
    parts.append("</svg>")
    return "".join(parts)


def svg_of(scene_key: str) -> str:
    scene = SCENES.get(scene_key)
    if not scene:
        return ""
    return (_figure_svg(scene_key) if scene_key in FIGURES
            else _place_svg(scene))


# ─────────────────────────── อ่านโจทย์ ───────────────────────────

def spec(raw: str) -> dict | None:
    """
    อ่านโจทย์จากช่อง icon — รูปแบบ "ฉาก|ชิ้นที่ถูก"

        "bedroom|toothbrush"   แตะหาแปรงสีฟันในห้องนอน
        "body|ear"             แตะที่หูของตัวการ์ตูน

    คืน None ถ้าชื่อฉากหรือชื่อชิ้นไม่มีอยู่จริง
    """
    parts = [p.strip() for p in (raw or "").split("|")]
    if len(parts) < 2 or parts[0] not in SCENES:
        return None
    scene = SCENES[parts[0]]
    keys = [k for k, _th, _e, _x, _y in scene["items"]]
    if parts[1] not in keys:
        return None
    return {"scene": parts[0], "target": parts[1], "name": scene["name"]}


def items_of(scene_key: str) -> list[tuple[str, str]]:
    """[(คีย์, คำไทย)] ของทุกชิ้นในฉาก เรียงตามลำดับที่วาด"""
    scene = SCENES.get(scene_key)
    if not scene:
        return []
    return [(k, th) for k, th, _e, _x, _y in scene["items"]]


def label_of(scene_key: str, item_key: str) -> str:
    for k, th in items_of(scene_key):
        if k == item_key:
            return th
    return ""


def prompt_for(raw: str) -> str:
    """โจทย์อัตโนมัติ เผื่อครูไม่ได้พิมพ์เอง"""
    s = spec(raw)
    if not s:
        return ""
    th = label_of(s["scene"], s["target"])
    if s["scene"] in FIGURES:
        return "แตะที่%sสิ" % th
    return "%s มี%sอยู่ แตะหาให้เจอสิ" % (s["name"], th)


def payload(raw: str, options: list[dict]) -> dict | None:
    """
    ชุดข้อมูลที่ส่งให้เบราว์เซอร์ — ไม่มีเฉลยติดไปด้วย

    spots เชื่อมชิ้นในภาพกับ id ของตัวเลือก (ตัวเลือกถูกสร้างเรียงตามลำดับชิ้น)
    เด็กแตะชิ้นไหน เบราว์เซอร์ก็ส่ง id ของตัวเลือกนั้นไปตรวจที่เซิร์ฟเวอร์
    เหมือนโจทย์เลือกตอบทุกอย่าง
    """
    s = spec(raw)
    if not s:
        return None
    items = items_of(s["scene"])
    opts = sorted(options or [], key=lambda o: o.get("sort_order") or 0)
    if len(opts) != len(items):
        return None                       # ข้อมูลไม่ตรงกัน ไม่ส่งไปให้พัง
    spots = [{"key": k, "label": th, "option_id": o["id"]}
             for (k, th), o in zip(items, opts)]
    return {"svg": svg_of(s["scene"]), "spots": spots,
            "scene": s["scene"], "name": s["name"],
            "body": s["scene"] in FIGURES}


def options_for(raw: str) -> list[dict] | None:
    """สร้างตัวเลือก 1 ตัวต่อ 1 ชิ้นในฉาก ติ๊กถูกที่ชิ้นที่เป็นคำตอบ"""
    s = spec(raw)
    if not s:
        return None
    return [
        {"sort_order": i + 1, "label": th, "image_url": None,
         "is_correct": k == s["target"], "match_value": None}
        for i, (k, th) in enumerate(items_of(s["scene"]))
    ]


def choices() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """รายการฉากกับชิ้นของในฉาก สำหรับทำดรอปดาวน์ในหน้าแอดมิน"""
    return [(key, SCENES[key]["name"], items_of(key)) for key in SCENES]
