# -*- coding: utf-8 -*-
"""
รูปสัตว์แทนภาพที่ติดลายน้ำ — วาดเป็น SVG เอง ไม่ติดลิขสิทธิ์

ในไฟล์ Animals.docx ที่ครูส่งมา มี 6 ภาพที่ยังติดลายน้ำ/แถบเครดิตของเว็บขายภาพ
(ลิง แมว หมี เต่า ยีราฟ ม้า) จึงวาดขึ้นใหม่เองให้ครบชุด สไตล์การ์ตูนน่ารัก
พื้นขาว ขนาด 400x400 ให้เข้ากับอีก 14 ภาพที่สะอาดอยู่แล้ว
"""

W = 400

# จานสีกลางที่ใช้ร่วมกันทุกตัว ภาพชุดนี้จะได้ดูเป็นชุดเดียวกัน
INK = "#3A2A1C"
WHITE = "#FFFFFF"
PINK = "#F6A8B8"
BROWN, LBROWN, DBROWN = "#A9763F", "#E8C39B", "#7A4E23"
CREAM = "#FDF4E6"
ORANGE, DORANGE = "#F2A65A", "#D9832F"
GREEN, DGREEN = "#82C882", "#57A257"
SHELL, DSHELL = "#A5702F", "#82571F"
YELLOW, DYELLOW = "#F5C86B", "#D98B3A"
GREY = "#B9C3CB"


def svg(body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {W}" '
            f'width="{W}" height="{W}">'
            f'<rect width="{W}" height="{W}" fill="{WHITE}"/>{body}</svg>')


def ground(y=352, rx=126, color="#EFEFEF"):
    return f'<ellipse cx="200" cy="{y}" rx="{rx}" ry="13" fill="{color}"/>'


def eyes(lx, rx, cy, r=12, ink=INK):
    """ตากลมโตพร้อมประกายแบบการ์ตูนเด็ก"""
    return (f'<circle cx="{lx}" cy="{cy}" r="{r}" fill="{ink}"/>'
            f'<circle cx="{rx}" cy="{cy}" r="{r}" fill="{ink}"/>'
            f'<circle cx="{lx + r*0.34:.1f}" cy="{cy - r*0.36:.1f}" r="{r*0.33:.1f}" fill="{WHITE}"/>'
            f'<circle cx="{rx + r*0.34:.1f}" cy="{cy - r*0.36:.1f}" r="{r*0.33:.1f}" fill="{WHITE}"/>')


def blush(lx, rx, cy, rx_=13, ry_=8):
    return (f'<ellipse cx="{lx}" cy="{cy}" rx="{rx_}" ry="{ry_}" fill="{PINK}" opacity=".7"/>'
            f'<ellipse cx="{rx}" cy="{cy}" rx="{rx_}" ry="{ry_}" fill="{PINK}" opacity=".7"/>')


ICONS = {}

# ── ลิง ─────────────────────────────────────────────────
ICONS["monkey"] = svg(
    ground() +
    # หาง ม้วนอยู่ข้างหลัง
    f'<path d="M262 300 q58 6 52 -44 q-4 -34 -34 -28 q-22 5 -14 24" '
    f'fill="none" stroke="{BROWN}" stroke-width="13" stroke-linecap="round"/>'
    # ขา
    f'<ellipse cx="160" cy="330" rx="34" ry="21" fill="{BROWN}"/>'
    f'<ellipse cx="240" cy="330" rx="34" ry="21" fill="{BROWN}"/>'
    f'<ellipse cx="156" cy="333" rx="22" ry="13" fill="{LBROWN}"/>'
    f'<ellipse cx="244" cy="333" rx="22" ry="13" fill="{LBROWN}"/>'
    # ตัว
    f'<ellipse cx="200" cy="272" rx="74" ry="66" fill="{BROWN}"/>'
    f'<ellipse cx="200" cy="284" rx="50" ry="50" fill="{LBROWN}"/>'
    # แขน
    f'<ellipse cx="126" cy="272" rx="20" ry="38" fill="{BROWN}" transform="rotate(16 126 272)"/>'
    f'<ellipse cx="274" cy="272" rx="20" ry="38" fill="{BROWN}" transform="rotate(-16 274 272)"/>'
    # หู
    f'<circle cx="124" cy="150" r="27" fill="{BROWN}"/>'
    f'<circle cx="276" cy="150" r="27" fill="{BROWN}"/>'
    f'<circle cx="124" cy="150" r="15" fill="{LBROWN}"/>'
    f'<circle cx="276" cy="150" r="15" fill="{LBROWN}"/>'
    # หัว
    f'<circle cx="200" cy="148" r="74" fill="{BROWN}"/>'
    f'<ellipse cx="200" cy="164" rx="56" ry="50" fill="{LBROWN}"/>'
    f'<path d="M144 124 q56 -46 112 0 q-56 -22 -112 0Z" fill="{LBROWN}"/>'
    + eyes(180, 220, 152, 13) +
    f'<ellipse cx="192" cy="186" rx="4" ry="3" fill="{DBROWN}"/>'
    f'<ellipse cx="208" cy="186" rx="4" ry="3" fill="{DBROWN}"/>'
    f'<path d="M182 200 q18 14 36 0" fill="none" stroke="{DBROWN}" '
    f'stroke-width="4.5" stroke-linecap="round"/>'
    + blush(158, 242, 180))

# ── แมว ─────────────────────────────────────────────────
ICONS["cat"] = svg(
    ground() +
    # หาง
    f'<path d="M272 312 q64 -4 46 -62 q-8 -26 -30 -18" fill="none" '
    f'stroke="{ORANGE}" stroke-width="20" stroke-linecap="round"/>'
    # ตัว — ลายส้มเป็นหย่อมข้างตัว ไม่ผ่าครึ่งตรง ๆ จะได้ดูเป็นแมวลายสามสี
    f'<ellipse cx="200" cy="280" rx="78" ry="62" fill="{CREAM}"/>'
    f'<ellipse cx="243" cy="262" rx="44" ry="40" fill="{ORANGE}"/>'
    f'<ellipse cx="192" cy="292" rx="38" ry="32" fill="#FFFCF4"/>'
    # ขาหน้า — ต้องมีเส้นขอบอ่อน ๆ ไม่งั้นขาวชนขาวจนกลืนเป็นก้อนเดียว
    f'<ellipse cx="168" cy="330" rx="25" ry="15" fill="{CREAM}" '
    f'stroke="#E4D6C0" stroke-width="3"/>'
    f'<ellipse cx="232" cy="330" rx="25" ry="15" fill="{CREAM}" '
    f'stroke="#E4D6C0" stroke-width="3"/>'
    f'<path d="M162 324 v10 M174 324 v10 M226 324 v10 M238 324 v10" '
    f'stroke="#E4D6C0" stroke-width="3" stroke-linecap="round"/>'
    # หู
    f'<path d="M136 108 l10 -62 l52 34Z" fill="{CREAM}"/>'
    f'<path d="M264 108 l-10 -62 l-52 34Z" fill="{ORANGE}"/>'
    f'<path d="M148 100 l6 -36 l30 20Z" fill="{PINK}"/>'
    f'<path d="M252 100 l-6 -36 l-30 20Z" fill="{PINK}"/>'
    # หัว
    f'<circle cx="200" cy="150" r="76" fill="{CREAM}"/>'
    f'<ellipse cx="234" cy="142" rx="38" ry="52" fill="{ORANGE}"/>'
    + eyes(174, 228, 146, 15) +
    f'<path d="M200 168 l-11 9 h22Z" fill="{PINK}"/>'
    f'<path d="M200 178 v7 M200 185 q-12 12 -22 2 M200 185 q12 12 22 2" '
    f'fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round"/>'
    # หนวด
    f'<path d="M150 166 l-42 -10 M150 178 l-44 6 M250 166 l42 -10 M250 178 l44 6" '
    f'fill="none" stroke="{INK}" stroke-width="3.4" stroke-linecap="round" opacity=".6"/>'
    + blush(148, 252, 176))

# ── หมี ─────────────────────────────────────────────────
ICONS["bear"] = svg(
    ground() +
    # หู
    f'<circle cx="142" cy="96" r="30" fill="{BROWN}"/>'
    f'<circle cx="258" cy="96" r="30" fill="{BROWN}"/>'
    f'<circle cx="142" cy="96" r="16" fill="{LBROWN}"/>'
    f'<circle cx="258" cy="96" r="16" fill="{LBROWN}"/>'
    # ตัว
    f'<ellipse cx="200" cy="286" rx="84" ry="62" fill="{BROWN}"/>'
    f'<ellipse cx="200" cy="296" rx="56" ry="46" fill="{LBROWN}"/>'
    f'<ellipse cx="128" cy="286" rx="22" ry="34" fill="{DBROWN}" transform="rotate(14 128 286)"/>'
    f'<ellipse cx="272" cy="286" rx="22" ry="34" fill="{DBROWN}" transform="rotate(-14 272 286)"/>'
    f'<ellipse cx="164" cy="332" rx="30" ry="18" fill="{DBROWN}"/>'
    f'<ellipse cx="236" cy="332" rx="30" ry="18" fill="{DBROWN}"/>'
    f'<ellipse cx="164" cy="334" rx="18" ry="10" fill="{LBROWN}"/>'
    f'<ellipse cx="236" cy="334" rx="18" ry="10" fill="{LBROWN}"/>'
    # หัว
    f'<circle cx="200" cy="158" r="80" fill="{BROWN}"/>'
    f'<ellipse cx="200" cy="192" rx="48" ry="38" fill="{LBROWN}"/>'
    + eyes(172, 228, 150, 13) +
    f'<ellipse cx="200" cy="180" rx="15" ry="11" fill="{INK}"/>'
    f'<path d="M200 191 v10 M200 201 q-13 13 -24 2 M200 201 q13 13 24 2" '
    f'fill="none" stroke="{INK}" stroke-width="4.4" stroke-linecap="round"/>'
    + blush(146, 254, 186))

# ── เต่า (มองจากด้านบน) ────────────────────────────────
_plates = "".join(
    f'<circle cx="{200 + dx}" cy="{196 + dy}" r="{r}" fill="{DSHELL}" opacity=".55"/>'
    for dx, dy, r in [(0, 0, 30), (-62, -6, 24), (62, -6, 24),
                      (-32, -46, 20), (32, -46, 20), (-32, 44, 20), (32, 44, 20)])
ICONS["turtle"] = svg(
    ground(y=344, rx=134) +
    # ขา 4 ข้าง — ต้องยื่นพ้นขอบกระดองให้เห็นชัด ไม่งั้นโดนกระดองบังหมด
    f'<ellipse cx="92" cy="132" rx="42" ry="27" fill="{GREEN}" transform="rotate(-36 92 132)"/>'
    f'<ellipse cx="308" cy="132" rx="42" ry="27" fill="{GREEN}" transform="rotate(36 308 132)"/>'
    f'<ellipse cx="92" cy="260" rx="42" ry="27" fill="{GREEN}" transform="rotate(36 92 260)"/>'
    f'<ellipse cx="308" cy="260" rx="42" ry="27" fill="{GREEN}" transform="rotate(-36 308 260)"/>'
    # กระดอง
    f'<ellipse cx="200" cy="196" rx="116" ry="94" fill="{SHELL}"/>'
    + _plates +
    f'<ellipse cx="200" cy="196" rx="116" ry="94" fill="none" stroke="{DSHELL}" stroke-width="7"/>'
    # หัว
    f'<circle cx="200" cy="306" r="46" fill="{GREEN}"/>'
    f'<path d="M200 260 a46 46 0 0 0 0 92Z" fill="{DGREEN}" opacity=".25"/>'
    + eyes(184, 216, 300, 9) +
    f'<path d="M188 320 q12 11 24 0" fill="none" stroke="{INK}" '
    f'stroke-width="4" stroke-linecap="round"/>'
    + blush(168, 232, 316, 10, 6))

# ── ยีราฟ ───────────────────────────────────────────────
_spots = "".join(
    f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r*0.85:.0f}" fill="{DYELLOW}"/>'
    for cx, cy, r in [(172, 262, 15), (228, 252, 13), (168, 306, 12),
                      (232, 300, 14), (200, 286, 11), (190, 206, 9), (211, 176, 8)])
ICONS["giraffe"] = svg(
    ground() +
    # ขา
    f'<rect x="156" y="306" width="24" height="52" rx="12" fill="{YELLOW}"/>'
    f'<rect x="220" y="306" width="24" height="52" rx="12" fill="{YELLOW}"/>'
    f'<rect x="156" y="340" width="24" height="18" rx="9" fill="{DYELLOW}"/>'
    f'<rect x="220" y="340" width="24" height="18" rx="9" fill="{DYELLOW}"/>'
    # ตัว
    f'<ellipse cx="200" cy="282" rx="78" ry="64" fill="{YELLOW}"/>'
    # คอ
    f'<rect x="176" y="150" width="48" height="110" rx="24" fill="{YELLOW}"/>'
    + _spots +
    # เขา
    f'<path d="M172 86 l-6 -30 M228 86 l6 -30" stroke="{DYELLOW}" '
    f'stroke-width="9" stroke-linecap="round"/>'
    f'<circle cx="166" cy="54" r="10" fill="{DYELLOW}"/>'
    f'<circle cx="234" cy="54" r="10" fill="{DYELLOW}"/>'
    # หู
    f'<ellipse cx="128" cy="108" rx="26" ry="15" fill="{YELLOW}" transform="rotate(-22 128 108)"/>'
    f'<ellipse cx="272" cy="108" rx="26" ry="15" fill="{YELLOW}" transform="rotate(22 272 108)"/>'
    # หัว
    f'<ellipse cx="200" cy="116" rx="56" ry="50" fill="{YELLOW}"/>'
    f'<ellipse cx="200" cy="140" rx="34" ry="28" fill="#FBE3B4"/>'
    + eyes(178, 222, 106, 11) +
    f'<ellipse cx="190" cy="140" rx="4" ry="5" fill="{DYELLOW}"/>'
    f'<ellipse cx="210" cy="140" rx="4" ry="5" fill="{DYELLOW}"/>'
    f'<path d="M186 154 q14 11 28 0" fill="none" stroke="{DYELLOW}" '
    f'stroke-width="4" stroke-linecap="round"/>'
    + blush(152, 248, 132, 11, 7))

# ── ม้า ─────────────────────────────────────────────────
ICONS["horse"] = svg(
    ground() +
    # หาง
    f'<path d="M282 258 q46 16 34 74 q-6 20 -24 14 q-14 -6 -6 -24" '
    f'fill="{DBROWN}"/>'
    # ขา
    f'<rect x="150" y="300" width="26" height="58" rx="13" fill="#B5743C"/>'
    f'<rect x="224" y="300" width="26" height="58" rx="13" fill="#B5743C"/>'
    f'<rect x="150" y="340" width="26" height="18" rx="8" fill="{DBROWN}"/>'
    f'<rect x="224" y="340" width="26" height="18" rx="8" fill="{DBROWN}"/>'
    # ตัว
    f'<ellipse cx="200" cy="278" rx="86" ry="62" fill="#B5743C"/>'
    f'<ellipse cx="200" cy="296" rx="52" ry="42" fill="#E0A96D"/>'
    # คอ + แผงคอ (ให้แผงคอโผล่พ้นหัวออกมาทางซ้าย ไม่งั้นถูกหัวบังจนไม่เห็น)
    f'<rect x="174" y="150" width="52" height="96" rx="26" fill="#B5743C"/>'
    f'<path d="M158 92 q-40 46 -24 130 q20 -10 24 -40 q4 -52 26 -78Z" fill="{DBROWN}"/>'
    # หู
    f'<path d="M158 92 l-4 -44 l34 26Z" fill="#B5743C"/>'
    f'<path d="M242 92 l4 -44 l-34 26Z" fill="#B5743C"/>'
    # หัว
    f'<ellipse cx="200" cy="130" rx="58" ry="52" fill="#B5743C"/>'
    f'<ellipse cx="200" cy="164" rx="38" ry="30" fill="#E0A96D"/>'
    # ผมหน้าม้าเล็ก ๆ บนหัว
    f'<path d="M184 86 q10 -26 30 -14 q-14 2 -20 20Z" fill="{DBROWN}"/>'
    + eyes(176, 224, 122, 11) +
    f'<ellipse cx="189" cy="160" rx="4.5" ry="6" fill="{DBROWN}"/>'
    f'<ellipse cx="211" cy="160" rx="4.5" ry="6" fill="{DBROWN}"/>'
    f'<path d="M186 176 q14 11 28 0" fill="none" stroke="{DBROWN}" '
    f'stroke-width="4" stroke-linecap="round"/>'
    + blush(150, 250, 150, 11, 7))
