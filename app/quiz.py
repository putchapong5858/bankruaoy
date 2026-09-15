"""
แบบฝึกหัด / ข้อสอบออนไลน์ ของบ้านครูอ้อย

แยกไฟล์ออกจาก db.py เพื่อให้ดูแลง่าย — ใช้ตัวช่วย select/insert/update/delete
ชุดเดียวกับ db.py (คุย Supabase ผ่าน PostgREST ด้วย service key ฝั่งเซิร์ฟเวอร์)

โครงข้อมูล
    quizzes                 1 ชุดแบบฝึกหัด
      quiz_questions        คำถามในชุด
        quiz_options        ตัวเลือก (เลือกตอบ / ถูกผิด / จับคู่)
        quiz_accepted_answers  คำตอบที่ยอมรับได้ (เติมคำ)
    quiz_attempts           การเข้าทำแต่ละรอบของนักเรียน
      quiz_attempt_answers  คำตอบรายข้อในรอบนั้น
"""

from __future__ import annotations

import random
import re
import unicodedata
from datetime import datetime, timezone

from . import config, shapes
from .db import (SupabaseError, delete, gather, insert, select,
                 select_one, update)

# รูปแบบคำถามที่ระบบรองรับ
KINDS = {
    "choice":    "เลือกตอบ",
    "truefalse": "ถูก / ผิด",
    "fill":      "เติมคำตอบ",
    "match":     "จับคู่",
    "count":     "นับจำนวน",
    "model3d":   "รูปทรง 3 มิติ / AR",
    "compare":   "เทียบเลข มากกว่า/น้อยกว่า (จระเข้กินเลข)",
    "mathrun":   "คิดเลขเร็ว บนก้อนเมฆ (จับเวลา)",
    "findshape": "นับรูปทรงในภาพรวม (เชาวน์ปัญญา)",
}

# รูปแบบที่ตรวจคำตอบเหมือนกัน คือเลือกตัวเลือกที่ถูก 1 ตัว
PICK_KINDS = ("choice", "truefalse", "count", "model3d", "compare",
              "mathrun", "findshape")

# อีโมจิยอดนิยมสำหรับโจทย์นับจำนวน — ครูกดเลือกได้เลยไม่ต้องพิมพ์
ICON_SETS = {
    "เครื่องมือช่าง": ["🔧", "🔨", "🪛", "🪚", "📏", "🧰", "🔩", "⚙️"],
    "ผลไม้":        ["🍎", "🍌", "🍇", "🍓", "🍉", "🍊", "🥭", "🍍"],
    "สัตว์":         ["🐶", "🐱", "🐰", "🐦", "🐟", "🦋", "🐘", "🐢"],
    "ของใช้":       ["✏️", "📕", "🎒", "✂️", "🖍️", "📐", "🧴", "🪁"],
    "รูปทรง/ดาว":    ["⭐", "❤️", "🔵", "🔺", "🟩", "🌸", "🎈", "🍬"],
}

# ── รูปทรง 3 มิติสำหรับโจทย์แบบ AR ──────────────────────────
# ไฟล์ .glb ใช้กับ Android และการหมุนดูบนจอ, .usdz ใช้กับ iPhone/iPad
# สร้างขึ้นเองทั้งหมด ไม่ติดลิขสิทธิ์ใคร
MODELS = {
    # ── รูปทรงเรขาคณิต (ป.1 ขึ้นไป) ──
    "cube":      {"g": "รูปทรงเรขาคณิต", "name": "ลูกบาศก์",
                  "facts": "6 หน้า · 12 ขอบ · 8 มุม"},
    "box":       {"g": "รูปทรงเรขาคณิต", "name": "ทรงสี่เหลี่ยมมุมฉาก",
                  "facts": "6 หน้า · 12 ขอบ · 8 มุม"},
    "sphere":    {"g": "รูปทรงเรขาคณิต", "name": "ทรงกลม",
                  "facts": "ไม่มีหน้าเหลี่ยม ไม่มีขอบ ไม่มีมุม"},
    "cylinder":  {"g": "รูปทรงเรขาคณิต", "name": "ทรงกระบอก",
                  "facts": "2 หน้าวงกลม · ผิวโค้ง 1 ผิว"},
    "cone":      {"g": "รูปทรงเรขาคณิต", "name": "กรวย",
                  "facts": "1 หน้าวงกลม · ยอดแหลม 1 จุด"},
    "pyramid":   {"g": "รูปทรงเรขาคณิต", "name": "พีระมิดฐานสี่เหลี่ยม",
                  "facts": "5 หน้า · 8 ขอบ · 5 มุม"},
    "tri_prism": {"g": "รูปทรงเรขาคณิต", "name": "ปริซึมสามเหลี่ยม",
                  "facts": "5 หน้า · 9 ขอบ · 6 มุม"},

    # ── ลูกบอลสี (อนุบาล — ฝึกเรียกชื่อสี) ──
    "ball_red":    {"g": "ลูกบอลสี", "name": "ลูกบอลสีแดง",    "facts": "ฝึกเรียกชื่อสี"},
    "ball_blue":   {"g": "ลูกบอลสี", "name": "ลูกบอลสีน้ำเงิน", "facts": "ฝึกเรียกชื่อสี"},
    "ball_yellow": {"g": "ลูกบอลสี", "name": "ลูกบอลสีเหลือง",  "facts": "ฝึกเรียกชื่อสี"},
    "ball_green":  {"g": "ลูกบอลสี", "name": "ลูกบอลสีเขียว",   "facts": "ฝึกเรียกชื่อสี"},

    # ── กลุ่มลูกบอลไว้ให้นับ (อนุบาล) ──
    # วางเป็นวงกลม เด็กต้องหมุนดูรอบ ๆ ถึงจะนับครบ ไม่ใช่แค่มองผ่าน ๆ
    "count1": {"g": "นับจำนวน", "name": "ลูกบอล 1 ลูก", "facts": "คำตอบคือ 1"},
    "count2": {"g": "นับจำนวน", "name": "ลูกบอล 2 ลูก", "facts": "คำตอบคือ 2"},
    "count3": {"g": "นับจำนวน", "name": "ลูกบอล 3 ลูก", "facts": "คำตอบคือ 3"},
    "count4": {"g": "นับจำนวน", "name": "ลูกบอล 4 ลูก", "facts": "คำตอบคือ 4"},
    "count5": {"g": "นับจำนวน", "name": "ลูกบอล 5 ลูก", "facts": "คำตอบคือ 5"},

    # ── ของรอบตัว (อนุบาล — เรียกชื่อสิ่งของ) ──
    "icecream": {"g": "ของรอบตัว", "name": "ไอศกรีมโคน", "facts": "รูปทรงกรวย + ทรงกลม"},
    "pencil":   {"g": "ของรอบตัว", "name": "ดินสอ",      "facts": "รูปทรงกระบอก + กรวย"},
    "balloon":  {"g": "ของรอบตัว", "name": "ลูกโป่ง",    "facts": "รูปทรงกลม"},
    "star":     {"g": "ของรอบตัว", "name": "ดาว",        "facts": "ดาว 5 แฉก"},
}

MODEL_GROUPS = ["รูปทรงเรขาคณิต", "ลูกบอลสี", "นับจำนวน", "ของรอบตัว"]


def model_url(slug: str, ios: bool = False) -> str:
    return "/static/models/%s.%s" % (slug, "usdz" if ios else "glb")


STATUSES = {
    "draft":     "ฉบับร่าง",
    "published": "เผยแพร่แล้ว",
    "closed":    "ปิดแล้ว",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _txt(value, limit: int) -> str:
    return (value or "").strip()[:limit]


def _int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


# ════════════════════════════════════════════════════════
#  ชุดแบบฝึกหัด
# ════════════════════════════════════════════════════════

def list_quizzes(limit: int = 60) -> list[dict]:
    """ทุกชุด ใหม่สุดอยู่บน พร้อมจำนวนข้อและสถิติการเข้าทำ"""
    rows = select("quizzes", order="created_at.desc", limit=limit)
    if not rows:
        return []

    got = gather(
        questions=lambda: select("quiz_questions", "id,quiz_id", limit=5000),
        attempts=lambda: select("quiz_attempts",
                                "quiz_id,student_id,score,full_score,finished",
                                limit=5000),
        # ระดับชั้นของเด็กที่ยังเรียนอยู่ — ไว้บอกครูว่าชุดนี้มีใครเห็นบ้าง
        kids=lambda: select("students", "level", active="eq.true", limit=2000),
    )
    questions, attempts = got["questions"], got["attempts"]
    kid_levels = [(k.get("level") or "").strip() for k in got["kids"]]

    for q in rows:
        qid = str(q["id"])
        q["question_count"] = sum(1 for x in questions if str(x["quiz_id"]) == qid)

        mine = [a for a in attempts if str(a["quiz_id"]) == qid and a.get("finished")]
        q["attempt_count"] = len(mine)
        q["student_count"] = len({a["student_id"] for a in mine})
        pcts = [float(a["score"]) / float(a["full_score"]) * 100
                for a in mine if float(a.get("full_score") or 0) > 0]
        q["average_percent"] = round(sum(pcts) / len(pcts)) if pcts else None
        q["status_label"] = STATUSES.get(q.get("status"), q.get("status"))
        # เด็กกี่คนที่ระดับชั้นตรงกับชุดนี้ — ถ้าเป็น 0 แปลว่าเผยแพร่ไปก็ไม่มีใครเห็น
        q["audience"] = sum(1 for lv in kid_levels if level_matches(q.get("level"), lv))
    return rows


def get_quiz(quiz_id: str | int) -> dict | None:
    return select_one("quizzes", id=f"eq.{quiz_id}")


def save_quiz(data: dict, quiz_id: str | int | None = None) -> dict:
    """สร้างหรือแก้ไขชุดแบบฝึกหัด"""
    title = _txt(data.get("title"), 150)
    if not title:
        raise SupabaseError("กรุณากรอกชื่อแบบฝึกหัด")

    minutes = _int(data.get("time_limit_min"), 0)
    pass_percent = max(0, min(_int(data.get("pass_percent"), 60), 100))

    fields = {
        "title": title,
        "subject": _txt(data.get("subject"), 60),
        "level": _txt(data.get("level"), 60),
        "description": _txt(data.get("description"), 500),
        # เวลา 0 = ไม่จำกัด (เก็บเป็น null)
        "time_limit_sec": minutes * 60 if minutes > 0 else None,
        "pass_percent": pass_percent,
        "shuffle_questions": bool(data.get("shuffle_questions")),
        "shuffle_options": bool(data.get("shuffle_options")),
        "show_answer_on_wrong": bool(data.get("show_answer_on_wrong")),
        "read_aloud": bool(data.get("read_aloud")),
    }
    if data.get("cover_url"):
        fields["cover_url"] = _txt(data.get("cover_url"), 500)
    if data.get("source_file_url"):
        fields["source_file_url"] = _txt(data.get("source_file_url"), 500)

    if quiz_id:
        update("quizzes", fields, id=f"eq.{quiz_id}")
        return get_quiz(quiz_id)
    return insert("quizzes", fields)[0]


def set_quiz_status(quiz_id: str | int, status: str) -> None:
    """เปลี่ยนสถานะ — เผยแพร่ได้เมื่อมีอย่างน้อย 1 ข้อเท่านั้น"""
    if status not in STATUSES:
        raise SupabaseError("สถานะไม่ถูกต้อง")

    values: dict = {"status": status}
    if status == "published":
        if not select("quiz_questions", "id", quiz_id=f"eq.{quiz_id}", limit=1):
            raise SupabaseError("ยังไม่มีคำถามในชุดนี้ กรุณาเพิ่มอย่างน้อย 1 ข้อก่อนเผยแพร่")
        values["published_at"] = _now()
    update("quizzes", values, id=f"eq.{quiz_id}")


def delete_quiz(quiz_id: str | int) -> None:
    """ลบทั้งชุด — ถ้ามีเด็กเคยทำแล้วจะปิดชุดแทน เพื่อไม่ให้ประวัติคะแนนหาย"""
    if select("quiz_attempts", "id", quiz_id=f"eq.{quiz_id}", limit=1):
        update("quizzes", {"status": "closed"}, id=f"eq.{quiz_id}")
        raise SupabaseError(
            "แบบฝึกหัดชุดนี้มีนักเรียนทำไปแล้ว ระบบจึงปิดชุดให้แทนการลบ "
            "(ประวัติคะแนนของเด็กจะได้ไม่หาย)"
        )
    delete("quizzes", id=f"eq.{quiz_id}")


# ════════════════════════════════════════════════════════
#  คำถาม + ตัวเลือก
# ════════════════════════════════════════════════════════

def list_questions(quiz_id: str | int, with_answers: bool = True) -> list[dict]:
    """คำถามทั้งหมดในชุด เรียงตามลำดับ พร้อมตัวเลือกของแต่ละข้อ"""
    questions = select("quiz_questions", quiz_id=f"eq.{quiz_id}",
                       order="sort_order.asc,id.asc", limit=300)
    if not questions:
        return []

    ids = [str(q["id"]) for q in questions]
    in_list = f"in.({','.join(ids)})"
    options = select("quiz_options", question_id=in_list,
                     order="sort_order.asc,id.asc", limit=2000)
    accepted = select("quiz_accepted_answers", question_id=in_list, limit=1000)

    for q in questions:
        qid = str(q["id"])
        q["options"] = [o for o in options if str(o["question_id"]) == qid]
        q["accepted"] = [a["value"] for a in accepted if str(a["question_id"]) == qid]
        q["kind_label"] = KINDS.get(q.get("kind"), q.get("kind"))
        # ภาพรูปทรงสร้างสด ๆ จาก seed — ทั้งหน้าครูและหน้าเด็กใช้ตัวสร้างเดียวกัน
        if q.get("kind") == "findshape":
            q["find"] = shapes.scene_of(q.get("icon"))
        if not with_answers:
            for o in q["options"]:
                o.pop("is_correct", None)
                o.pop("match_value", None)
            q.pop("accepted", None)
            q.pop("explanation", None)
    return questions


def get_question(question_id: str | int) -> dict | None:
    q = select_one("quiz_questions", id=f"eq.{question_id}")
    if not q:
        return None
    q["options"] = select("quiz_options", question_id=f"eq.{question_id}",
                          order="sort_order.asc,id.asc", limit=50)
    q["accepted"] = [a["value"] for a in
                     select("quiz_accepted_answers", question_id=f"eq.{question_id}", limit=50)]
    return q


def _next_sort_order(quiz_id: str | int) -> int:
    rows = select("quiz_questions", "sort_order", quiz_id=f"eq.{quiz_id}",
                  order="sort_order.desc", limit=1)
    return (_int(rows[0]["sort_order"], 0) + 1) if rows else 1


def save_question(quiz_id: str | int, data: dict,
                  question_id: str | int | None = None) -> dict:
    """
    เพิ่มหรือแก้ไขคำถาม 1 ข้อ พร้อมตัวเลือก/เฉลย

    data ที่รับ
        kind         choice | truefalse | fill | match
        prompt       โจทย์
        image_url    รูปประกอบ (ถ้ามี)
        explanation  คำอธิบายเฉลย
        points       คะแนนของข้อนี้
        options      [{label, image_url, is_correct, match_value}]  (choice/truefalse/match)
        accepted     ["คำตอบ1", "คำตอบ2"]                            (fill)
    """
    kind = data.get("kind") if data.get("kind") in KINDS else "choice"
    prompt = _txt(data.get("prompt"), 1000)
    image_url = _txt(data.get("image_url"), 500)

    # โจทย์ที่เป็นรูปล้วน (เช่น ถ่ายจากหนังสือ) ไม่ต้องมีข้อความก็ได้
    if not prompt and not image_url:
        raise SupabaseError("กรุณากรอกโจทย์ หรือแนบรูปโจทย์อย่างน้อยหนึ่งอย่าง")

    try:
        points = max(0.5, min(float(data.get("points") or 1), 100.0))
    except (TypeError, ValueError):
        points = 1.0

    icon = _txt(data.get("icon"), 200)
    icon_count = _int(data.get("icon_count"), 0)

    fields = {
        "kind": kind,
        "prompt": prompt,
        "image_url": image_url or None,
        "hint": _txt(data.get("hint"), 300) or None,
        "explanation": _txt(data.get("explanation"), 500) or None,
        "points": points,
        "icon": icon or None,
        "icon_count": icon_count if kind in ("count", "compare") else None,
    }

    if kind == "mathrun":
        # โจทย์คิดเลขเร็ว — ระบบสร้างตัวเลือกตัวเลขให้เอง ครูแค่กรอกโจทย์
        spec = mathrun_spec(icon)
        if not spec:
            raise SupabaseError(
                'โจทย์คิดเลขเร็วต้องอยู่ในรูปแบบ "4+5" หรือ "9-3" '
                "(ใช้ได้เฉพาะ + และ - และผลลัพธ์ต้องไม่ติดลบ)"
            )
        options = _math_choices(spec["answer"])
        accepted = []
        if not prompt:
            fields["prompt"] = "%d %s %d = ?" % (
                spec["a"], "+" if spec["op"] == "+" else "−", spec["b"])
    elif kind == "findshape":
        # โจทย์นับรูปทรง — ภาพสร้างจาก seed เซิร์ฟเวอร์จึงนับคำตอบเองได้
        sp = shapes.spec(icon)
        if not sp:
            raise SupabaseError(
                'โจทย์นับรูปทรงต้องอยู่ในรูปแบบ "เลขภาพ|ชนิด|สี|ความยาก" '
                "เช่น 3140|triangle|red|easy"
            )
        answer = shapes.answer_of(icon)
        options = _count_choices(answer, 4)
        accepted = []
        if not prompt:
            fields["prompt"] = "ในภาพนี้มี%sกี่รูป?" % shapes.label(sp["shape"], sp["color"])
        if not fields.get("hint"):
            fields["hint"] = "แตะรูปทีละรูปเพื่อทำเครื่องหมาย จะได้ไม่นับซ้ำนะ"
    elif kind == "count":
        # โจทย์นับจำนวน — ระบบสร้างตัวเลือกตัวเลขให้เอง ครูแค่บอกรูปกับจำนวน
        if not icon:
            raise SupabaseError("กรุณาเลือกรูปหรืออีโมจิที่จะให้เด็กนับ")
        if not 1 <= icon_count <= 20:
            raise SupabaseError("จำนวนที่ให้นับต้องอยู่ระหว่าง 1 ถึง 20")
        options = _number_choices(icon_count)
        accepted = []
        if not prompt:
            fields["prompt"] = f"นับดูสิว่ามีทั้งหมดกี่ชิ้น แล้วเลือกตัวเลขที่ถูก"
    else:
        options = _clean_options(kind, data.get("options") or [])
        accepted = [_txt(v, 200) for v in (data.get("accepted") or []) if _txt(v, 200)]

    if kind == "fill" and not accepted:
        raise SupabaseError("ข้อเติมคำต้องมีคำตอบที่ถูกต้องอย่างน้อย 1 คำตอบ")
    if kind == "compare":
        pair = compare_pair(icon)
        if not pair:
            raise SupabaseError('กรุณากรอกคู่ตัวเลขในรูปแบบ "12|10"')
        if not all(0 <= n <= 99 for n in pair):
            raise SupabaseError("ตัวเลขที่เทียบต้องอยู่ระหว่าง 0 ถึง 99")
        if len(options) < 2:
            raise SupabaseError("ต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก")
    if kind == "model3d":
        if icon not in MODELS:
            raise SupabaseError("กรุณาเลือกรูปทรง 3 มิติที่จะให้เด็กดู")
        if len(options) < 2:
            raise SupabaseError("ต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก")
    if kind in ("choice", "truefalse"):
        if len(options) < 2:
            raise SupabaseError("ต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก")
        if not any(o["is_correct"] for o in options):
            raise SupabaseError("กรุณาเลือกว่าข้อไหนคือคำตอบที่ถูกต้อง")
    if kind == "match" and len(options) < 2:
        raise SupabaseError("ข้อจับคู่ต้องมีอย่างน้อย 2 คู่")

    if question_id:
        update("quiz_questions", fields, id=f"eq.{question_id}")
        qid = question_id
        # เขียนตัวเลือกทับใหม่ทั้งชุด ง่ายและไม่มีของค้าง
        delete("quiz_options", question_id=f"eq.{qid}")
        delete("quiz_accepted_answers", question_id=f"eq.{qid}")
    else:
        fields["quiz_id"] = int(quiz_id)
        fields["sort_order"] = _next_sort_order(quiz_id)
        qid = insert("quiz_questions", fields)[0]["id"]

    if options:
        insert("quiz_options", [{**o, "question_id": int(qid)} for o in options])
    if accepted:
        insert("quiz_accepted_answers",
               [{"question_id": int(qid), "value": v} for v in accepted])

    return get_question(qid)


def _number_choices(answer: int) -> list[dict]:
    """
    สร้างตัวเลือกตัวเลข 3 ตัวรอบ ๆ คำตอบ แบบเดียวกับใบงาน Count and Match
    เช่น คำตอบ 5 จะได้ 4 5 6 · คำตอบ 1 จะได้ 1 2 3
    """
    start = max(1, answer - 1)
    if answer <= 1:
        start = 1
    numbers = [start, start + 1, start + 2]
    if answer not in numbers:              # กันกรณีขอบ
        numbers = [answer, answer + 1, answer + 2]
    return [
        {"sort_order": i + 1, "label": str(n), "image_url": None,
         "is_correct": n == answer, "match_value": None}
        for i, n in enumerate(numbers)
    ]


# ── คิดเลขเร็ว บนก้อนเมฆ ────────────────────────────────
# เก็บทุกอย่างไว้ในช่อง icon ช่องเดียว คั่นด้วย | เหมือนโจทย์เทียบเลข
# จะได้ไม่ต้องเพิ่มคอลัมน์ในฐานข้อมูล
#
#     "4+5|20|1"   =  โจทย์ 4+5 · ให้เวลาคิดเร็ว 20 วินาที · โชว์จุดช่วยนับ
#     "9-3|12|0"   =  โจทย์ 9-3 · 12 วินาที · ไม่โชว์จุด
#
# หมายเหตุสำคัญ: "วินาที" ที่ว่านี้ไม่ใช่การบังคับ เด็กตอบช้ากว่านั้นก็ยังตอบได้
# และยังได้คะแนนเต็มเหมือนเดิม — เป็นแค่โบนัสดาวความเร็วเท่านั้น

MATH_DEFAULT_SEC = 15


def mathrun_spec(raw: str) -> dict | None:
    """อ่านโจทย์คิดเลขเร็วจากช่อง icon — คืน None ถ้ารูปแบบไม่ถูก"""
    parts = (raw or "").split("|")
    expr = (parts[0] if parts else "").replace(" ", "")
    m = re.fullmatch(r"(\d{1,2})([+\-])(\d{1,2})", expr)
    if not m:
        return None

    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    answer = a + b if op == "+" else a - b
    if answer < 0:
        return None

    seconds = _int(parts[1], MATH_DEFAULT_SEC) if len(parts) > 1 else MATH_DEFAULT_SEC
    seconds = max(5, min(seconds, 90))
    dots = bool(_int(parts[2], 0)) if len(parts) > 2 else False
    return {"a": a, "op": op, "b": b, "answer": answer,
            "seconds": seconds, "dots": dots, "expr": f"{a}{op}{b}"}


def _math_choices(answer: int) -> list[dict]:
    """
    ตัวเลือกตัวเลข 3 ตัว — คำตอบที่ถูก + ตัวลวงใกล้ ๆ อีก 2 ตัว

    ตั้งใจไม่ใช้เลขเรียงติดกันทุกข้อ (8 9 10 ซ้ำ ๆ) เพราะเด็กจะจำรูปแบบแทนการคิด
    """
    pool = [answer - 2, answer - 1, answer + 1, answer + 2]
    pool = [n for n in pool if 0 <= n <= 20]
    random.shuffle(pool)
    numbers = sorted([answer] + pool[:2])
    return [
        {"sort_order": i + 1, "label": str(n), "image_url": None,
         "is_correct": n == answer, "match_value": None}
        for i, n in enumerate(numbers)
    ]


def _count_choices(answer: int, how_many: int = 4) -> list[dict]:
    """
    ตัวเลือกตัวเลขรอบ ๆ คำตอบ สำหรับโจทย์นับ — คำตอบที่ถูก 1 ตัว + ตัวลวงใกล้ ๆ

    ใช้ 4 ตัวเลือกกับโจทย์นับรูปทรง เพราะถ้ามีแค่ 3 ตัว เดาสุ่มก็ถูก 1 ใน 3
    ซึ่งง่ายเกินไปสำหรับโจทย์ที่จริง ๆ แล้วต้องกวาดตาหาให้ครบ
    """
    # เอาตัวลวงที่ห่างแค่ 1-2 ก่อน ถ้าไม่พอค่อยใช้ห่าง 3 — ตัวลวงที่ห่างมาก
    # เด็กตัดทิ้งได้ตั้งแต่ยังไม่นับ ข้อก็เลยง่ายเกินจริง และไม่ใช้เลข 0
    near = [n for n in (answer - 1, answer + 1, answer - 2, answer + 2) if n >= 1]
    far = [n for n in (answer - 3, answer + 3) if n >= 1]
    random.shuffle(near)
    random.shuffle(far)
    pool = near + far
    numbers = sorted([answer] + pool[:max(1, how_many - 1)])
    return [
        {"sort_order": i + 1, "label": str(n), "image_url": None,
         "is_correct": n == answer, "match_value": None}
        for i, n in enumerate(numbers)
    ]


def _clean_options(kind: str, raw: list[dict]) -> list[dict]:
    """ทำความสะอาดตัวเลือกจากฟอร์ม — ตัดแถวว่างทิ้ง"""
    out: list[dict] = []
    for i, o in enumerate(raw, start=1):
        label = _txt(o.get("label"), 300)
        image = _txt(o.get("image_url"), 500)
        match_value = _txt(o.get("match_value"), 300)
        if not label and not image:
            continue
        if kind == "match" and not match_value:
            continue
        out.append({
            "sort_order": i,
            "label": label or f"ตัวเลือก {i}",
            "image_url": image or None,
            "is_correct": bool(o.get("is_correct")) if kind != "match" else True,
            "match_value": match_value or None,
        })
    return out


def delete_question(question_id: str | int) -> None:
    delete("quiz_options", question_id=f"eq.{question_id}")
    delete("quiz_accepted_answers", question_id=f"eq.{question_id}")
    delete("quiz_attempt_answers", question_id=f"eq.{question_id}")
    delete("quiz_questions", id=f"eq.{question_id}")


def move_question(question_id: str | int, direction: str) -> None:
    """เลื่อนข้อขึ้น/ลง — สลับ sort_order กับข้อที่อยู่ติดกัน"""
    me = select_one("quiz_questions", "id,quiz_id,sort_order", id=f"eq.{question_id}")
    if not me:
        return
    order = "sort_order.desc" if direction == "up" else "sort_order.asc"
    cmp_ = "lt" if direction == "up" else "gt"
    neighbours = select("quiz_questions", "id,sort_order",
                        quiz_id=f"eq.{me['quiz_id']}",
                        sort_order=f"{cmp_}.{me['sort_order']}",
                        order=order, limit=1)
    if not neighbours:
        return
    other = neighbours[0]
    update("quiz_questions", {"sort_order": other["sort_order"]}, id=f"eq.{me['id']}")
    update("quiz_questions", {"sort_order": me["sort_order"]}, id=f"eq.{other['id']}")


def renumber(quiz_id: str | int) -> None:
    """จัดลำดับข้อใหม่ให้เป็น 1,2,3... หลังลบข้อกลาง ๆ ออก"""
    for i, q in enumerate(select("quiz_questions", "id", quiz_id=f"eq.{quiz_id}",
                                 order="sort_order.asc,id.asc", limit=300), start=1):
        update("quiz_questions", {"sort_order": i}, id=f"eq.{q['id']}")


# ════════════════════════════════════════════════════════
#  ตรวจคำตอบ
# ════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """
    ทำให้คำตอบเทียบกันได้อย่างใจกว้าง — เด็กพิมพ์ไม่เป๊ะก็ควรได้คะแนน

    ตัดช่องว่างซ้ำ ตัดวรรคตอน แปลงเป็นตัวพิมพ์เล็ก และรวมรูปยูนิโค้ดให้เหมือนกัน
    """
    text = unicodedata.normalize("NFC", (text or "")).strip().lower()
    text = re.sub(r"[\s​]+", " ", text)
    text = re.sub(r"[.,!?;:\"'()\[\]{}·]", "", text)
    return text.strip()


def check_answer(question: dict, given) -> bool:
    """ตรวจคำตอบ 1 ข้อ — คืน True ถ้าถูก

    given เป็น id ของตัวเลือก (choice/truefalse), ข้อความ (fill)
    หรือ dict {option_id: คำตอบที่จับคู่} (match)
    """
    kind = question.get("kind") or "choice"
    options = question.get("options") or []

    if kind in PICK_KINDS:
        correct = {str(o["id"]) for o in options if o.get("is_correct")}
        return str(given) in correct

    if kind == "fill":
        want = {_normalize(v) for v in (question.get("accepted") or [])}
        return _normalize(str(given)) in want if want else False

    if kind == "match":
        if not isinstance(given, dict):
            return False
        for o in options:
            if _normalize(str(given.get(str(o["id"]), ""))) != _normalize(o.get("match_value") or ""):
                return False
        return True

    return False


def correct_answer_text(question: dict) -> str:
    """ข้อความเฉลย ใช้บอกเด็กเมื่อตอบผิด"""
    kind = question.get("kind") or "choice"
    options = question.get("options") or []

    if kind in PICK_KINDS:
        right = [o["label"] for o in options if o.get("is_correct")]
        return " หรือ ".join(right)
    if kind == "fill":
        return " หรือ ".join(question.get("accepted") or [])
    if kind == "match":
        return " · ".join(f"{o['label']} คู่กับ {o.get('match_value') or ''}"
                          for o in options)
    return ""


# ════════════════════════════════════════════════════════
#  ฝั่งนักเรียน — ชุดที่ทำได้ และการทำแต่ละรอบ
# ════════════════════════════════════════════════════════

def level_matches(quiz_level: str, student_level: str) -> bool:
    """
    ชุดนี้ตรงกับระดับชั้นของเด็กคนนี้ไหม

    เดิมเทียบข้อความตรง ๆ ทำให้ชุดที่ตั้งระดับเป็นช่วง เช่น "อนุบาล 3 - ป.1"
    ไม่ขึ้นให้เด็กคนไหนเลย เพราะไม่มีเด็กคนไหนมีระดับชั้นชื่อนั้น
    ตอนนี้จึงรองรับ 3 แบบ

        ""                  ว่าง = ทุกระดับชั้น
        "ป.1, ป.2"          หลายชั้นคั่นด้วย , / ;
        "อนุบาล 3 - ป.1"     ช่วงชั้น — ตรงทุกชั้นที่อยู่ระหว่างกลางด้วย
    """
    want = (student_level or "").strip()
    text = (quiz_level or "").strip()
    if not text:
        return True                       # ไม่ระบุ = เปิดให้ทุกชั้น
    if not want:
        return False

    order = list(config.LEVELS)

    def rank(name: str) -> int:
        name = name.strip()
        return order.index(name) if name in order else -1

    for part in re.split(r"[,;/]|\bหรือ\b", text):
        part = part.strip()
        if not part:
            continue
        if part == want:
            return True

        # ช่วงชั้น เช่น "อนุบาล 2 - ป.6" (รับทั้งขีดสั้น ขีดยาว และ ถึง)
        ends = re.split(r"\s*(?:-|–|—|ถึง)\s*", part)
        if len(ends) == 2:
            lo, hi = rank(ends[0]), rank(ends[1])
            me = rank(want)
            if lo >= 0 and hi >= 0 and me >= 0:
                if min(lo, hi) <= me <= max(lo, hi):
                    return True
    return False


def compare_pair(raw: str) -> tuple[int, int] | None:
    """อ่านคู่ตัวเลขของโจทย์เทียบเลข เก็บในช่อง icon เป็น "12|10" """
    parts = (raw or "").split("|")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def subject_key(raw: str) -> str:
    """ชื่อวิชาที่พิมพ์มาแบบไหนก็ตาม ให้กลายเป็นชื่อมาตรฐานชื่อเดียว"""
    name = (raw or "").strip()
    if not name:
        return ""
    for s in config.SUBJECTS:
        if name == s["name"]:
            return name
    return config.SUBJECT_ALIASES.get(name.lower(), name)


def by_subject(rows: list[dict]) -> list[dict]:
    """
    จัดแบบฝึกหัดเป็นกล่องตามรายวิชา เรียงตามลำดับใน config.SUBJECTS

    คืน [{name, icon, color, quizzes}] เฉพาะวิชาที่มีชุดจริง —
    วิชาที่ยังไม่มีแบบฝึกหัดจะไม่โผล่เป็นกล่องว่างให้ผู้ปกครองงง
    ชุดที่ชื่อวิชาไม่ตรงวิชาไหนเลยจะไปรวมอยู่กล่อง "อื่น ๆ" ท้ายสุด
    """
    buckets: dict[str, list] = {}
    for q in rows:
        buckets.setdefault(subject_key(q.get("subject")), []).append(q)

    known = [s["name"] for s in config.SUBJECTS]
    out = []
    for s in config.SUBJECTS:
        got = buckets.pop(s["name"], [])
        if got:
            out.append({**s, "quizzes": got})

    leftovers = [q for name, group in buckets.items()
                 if name not in known for q in group]
    if leftovers:
        out.append({**config.OTHER_SUBJECT, "quizzes": leftovers})
    return out


def quizzes_for_student(student: dict, limit: int = 40) -> list[dict]:
    """แบบฝึกหัดที่เผยแพร่แล้วและตรงระดับชั้นของเด็ก พร้อมผลที่เคยทำ"""
    level = (student.get("level") or "").strip()
    rows = select("quizzes", status="eq.published",
                  order="published_at.desc,id.desc", limit=limit)
    rows = [q for q in rows if level_matches(q.get("level"), level)]
    if not rows:
        return []

    got = gather(
        counts=lambda: select("quiz_questions", "id,quiz_id", limit=5000),
        mine=lambda: select("quiz_attempts", student_id=f"eq.{student['id']}",
                            finished="eq.true", order="finished_at.desc", limit=500),
    )
    counts, mine = got["counts"], got["mine"]

    for q in rows:
        qid = str(q["id"])
        q["question_count"] = sum(1 for x in counts if str(x["quiz_id"]) == qid)
        tries = [a for a in mine if str(a["quiz_id"]) == qid]
        q["times_done"] = len(tries)
        q["best_percent"] = max(
            (round(float(a["score"]) / float(a["full_score"]) * 100)
             for a in tries if float(a.get("full_score") or 0) > 0),
            default=None,
        )
        q["last_done_at"] = tries[0].get("finished_at") if tries else None
    return rows


def start_attempt(quiz_id: str | int, student_id: str,
                  only_wrong: bool = False) -> dict:
    """
    เริ่มทำรอบใหม่ — คืนชุดคำถามที่สลับลำดับแล้ว (ยังไม่มีเฉลยติดไปด้วย)

    only_wrong = True คือโหมดทบทวนเฉพาะข้อที่เคยตอบผิดในรอบล่าสุด
    """
    quiz = get_quiz(quiz_id)
    if not quiz:
        raise SupabaseError("ไม่พบแบบฝึกหัดชุดนี้")
    if quiz.get("status") != "published":
        raise SupabaseError("แบบฝึกหัดชุดนี้ยังไม่เปิดให้ทำ")

    questions = list_questions(quiz_id, with_answers=True)
    if not questions:
        raise SupabaseError("แบบฝึกหัดชุดนี้ยังไม่มีคำถาม")

    if only_wrong:
        wrong_ids = last_wrong_question_ids(quiz_id, student_id)
        subset = [q for q in questions if str(q["id"]) in wrong_ids]
        if subset:
            questions = subset

    if quiz.get("shuffle_questions"):
        random.shuffle(questions)
    if quiz.get("shuffle_options"):
        for q in questions:
            if q.get("kind") != "match":
                random.shuffle(q["options"])

    done = select("quiz_attempts", "attempt_no", quiz_id=f"eq.{quiz_id}",
                  student_id=f"eq.{student_id}", order="attempt_no.desc", limit=1)
    attempt_no = (_int(done[0]["attempt_no"], 0) + 1) if done else 1

    attempt = insert("quiz_attempts", {
        "quiz_id": int(quiz_id),
        "student_id": student_id,
        "attempt_no": attempt_no,
        "total_count": len(questions),
        "full_score": sum(float(q.get("points") or 1) for q in questions),
        # เก็บลำดับที่สลับแล้ว เพื่อให้เซิร์ฟเวอร์รู้ว่ารอบนี้มีข้อไหนบ้าง
        "question_ids": [int(q["id"]) for q in questions],
    })[0]

    return {"quiz": quiz, "attempt": attempt, "questions": questions}


def public_questions(questions: list[dict]) -> list[dict]:
    """
    ตัดเฉลยออกก่อนส่งให้เบราว์เซอร์

    สำคัญมาก — ถ้าส่งเฉลยไปด้วย เด็ก (หรือผู้ปกครอง) กด View Source ก็เห็นคำตอบหมด
    การตรวจคำตอบจึงทำที่เซิร์ฟเวอร์ทีละข้อแทน
    """
    out = []
    for q in questions:
        out.append({
            "id": q["id"],
            "kind": q.get("kind") or "choice",
            "prompt": q.get("prompt") or "",
            "image_url": q.get("image_url"),
            "hint": q.get("hint"),
            "points": float(q.get("points") or 1),
            # โจทย์นับจำนวน — ส่งรูปกับจำนวนไปให้หน้าเว็บวาดแถวรูปเอง
            "icon": q.get("icon") if q.get("kind") in ("count", "model3d") else None,
            # โจทย์เทียบเลข — ส่งคู่ตัวเลขกับจำนวนจุดช่วยนับไปให้หน้าเด็กวาด
            "pair": compare_pair(q.get("icon")) if q.get("kind") == "compare" else None,
            # โจทย์คิดเลขเร็ว — ส่งตัวเลข เครื่องหมาย และเวลาคิด ไปให้หน้าเด็ก
            # ระวัง: ต้องตัด answer ทิ้ง ไม่งั้นเด็กกด View Source แล้วเห็นเฉลย
            "math": _math_public(q.get("icon")) if q.get("kind") == "mathrun" else None,
            # โจทย์นับรูปทรง — ส่งภาพ SVG กับชื่อเป้าหมายไป ไม่ได้ส่งจำนวนที่ถูก
            "find": shapes.scene_of(q.get("icon")) if q.get("kind") == "findshape" else None,
            "dots": bool(q.get("icon_count")) if q.get("kind") == "compare" else False,
            "model": (MODELS.get(q.get("icon") or "") or None)
                     if q.get("kind") == "model3d" else None,
            "model_url": model_url(q["icon"]) if q.get("kind") == "model3d"
                         and q.get("icon") in MODELS else None,
            "model_ios": model_url(q["icon"], True) if q.get("kind") == "model3d"
                         and q.get("icon") in MODELS else None,
            "icon_count": q.get("icon_count") if q.get("kind") == "count" else None,
            "options": [
                {"id": o["id"], "label": o["label"], "image_url": o.get("image_url")}
                for o in (q.get("options") or [])
            ],
            # ข้อจับคู่ต้องส่งตัวเลือกฝั่งขวาไปให้เลือก (สลับลำดับแล้ว)
            "match_choices": (
                random.sample([o.get("match_value") or "" for o in (q.get("options") or [])],
                              len(q.get("options") or []))
                if (q.get("kind") == "match") else []
            ),
        })
    return out


def _math_public(raw: str) -> dict | None:
    """โจทย์คิดเลขเร็วฉบับที่ส่งให้เบราว์เซอร์ได้ — ตัดเฉลยออกแล้ว"""
    spec = mathrun_spec(raw)
    if not spec:
        return None
    return {"a": spec["a"], "op": spec["op"], "b": spec["b"],
            "seconds": spec["seconds"], "dots": spec["dots"]}


def get_attempt(attempt_id: str | int) -> dict | None:
    return select_one("quiz_attempts", id=f"eq.{attempt_id}")


def attempt_questions(attempt: dict) -> list[dict]:
    """คำถามของรอบนี้ เรียงตามลำดับที่สลับไว้ตอนเริ่ม (มีเฉลยติดมาด้วย)"""
    ids = [str(i) for i in (attempt.get("question_ids") or [])]
    if not ids:
        return []
    all_q = list_questions(attempt["quiz_id"], with_answers=True)
    by_id = {str(q["id"]): q for q in all_q}
    return [by_id[i] for i in ids if i in by_id]


def question_in_attempt(attempt: dict, question_id: str | int) -> dict | None:
    """หาคำถาม 1 ข้อของรอบนี้ — กันไม่ให้ส่งคำตอบของข้อที่ไม่ได้อยู่ในรอบ"""
    if int(question_id) not in [int(i) for i in (attempt.get("question_ids") or [])]:
        return None
    return get_question(question_id)


def last_wrong_question_ids(quiz_id: str | int, student_id: str) -> set[str]:
    """id ของข้อที่ตอบผิดในรอบล่าสุด — ใช้ทำโหมดทบทวน"""
    last = select("quiz_attempts", "id", quiz_id=f"eq.{quiz_id}",
                  student_id=f"eq.{student_id}", finished="eq.true",
                  order="finished_at.desc", limit=1)
    if not last:
        return set()
    rows = select("quiz_attempt_answers", "question_id,is_correct",
                  attempt_id=f"eq.{last[0]['id']}", is_correct="eq.false", limit=300)
    return {str(r["question_id"]) for r in rows}


def record_answer(attempt_id: str | int, question_id: str | int,
                  given, is_correct: bool) -> None:
    """บันทึกคำตอบรายข้อ — เขียนทับถ้าเด็กย้อนกลับมาตอบข้อเดิมในรอบเดียวกัน"""
    delete("quiz_attempt_answers",
           attempt_id=f"eq.{attempt_id}", question_id=f"eq.{question_id}")
    insert("quiz_attempt_answers", {
        "attempt_id": int(attempt_id),
        "question_id": int(question_id),
        "given": str(given)[:500] if given is not None else None,
        "is_correct": bool(is_correct),
    })


def finish_attempt(attempt_id: str | int, seconds_used: int | None = None) -> dict:
    """ปิดรอบ — รวมคะแนนจากคำตอบที่บันทึกไว้"""
    attempt = select_one("quiz_attempts", id=f"eq.{attempt_id}")
    if not attempt:
        raise SupabaseError("ไม่พบรอบการทำนี้")

    answers = select("quiz_attempt_answers", "question_id,is_correct",
                     attempt_id=f"eq.{attempt_id}", limit=300)
    right_ids = [str(a["question_id"]) for a in answers if a.get("is_correct")]

    points = {str(q["id"]): float(q.get("points") or 1)
              for q in select("quiz_questions", "id,points",
                              quiz_id=f"eq.{attempt['quiz_id']}", limit=300)}
    score = sum(points.get(qid, 1) for qid in right_ids)

    values = {
        "score": score,
        "correct_count": len(right_ids),
        "finished": True,
        "finished_at": _now(),
    }
    if seconds_used is not None:
        values["seconds_used"] = max(0, _int(seconds_used, 0))

    update("quiz_attempts", values, id=f"eq.{attempt_id}")
    return {**attempt, **values}


def attempt_history(student_id: str, quiz_id: str | int | None = None,
                    limit: int = 60) -> list[dict]:
    """ประวัติการทำของนักเรียน 1 คน — ทุกรอบ ได้กี่คะแนน"""
    filters = {"student_id": f"eq.{student_id}", "finished": "eq.true"}
    if quiz_id:
        filters["quiz_id"] = f"eq.{quiz_id}"
    rows = select("quiz_attempts", order="finished_at.desc", limit=limit, **filters)
    if not rows:
        return []
    titles = {str(q["id"]): q for q in select("quizzes", "id,title,subject", limit=500)}
    for r in rows:
        q = titles.get(str(r["quiz_id"])) or {}
        r["quiz_title"] = q.get("title", "")
        r["quiz_subject"] = q.get("subject", "")
        full = float(r.get("full_score") or 0)
        r["percent"] = round(float(r["score"]) / full * 100) if full else 0
        r["stars"] = stars_for(r["percent"])
    return rows


def stars_for(percent: float) -> int:
    """แปลงเปอร์เซ็นต์เป็นดาว 1-5 ดวง — เด็กเล็กเข้าใจง่ายกว่าเปอร์เซ็นต์"""
    if percent >= 95:
        return 5
    if percent >= 80:
        return 4
    if percent >= 60:
        return 3
    if percent >= 40:
        return 2
    return 1


# ════════════════════════════════════════════════════════
#  แจ้งเตือนผู้ปกครอง
# ════════════════════════════════════════════════════════

def parents_to_notify(level: str = "") -> list[dict]:
    """
    ผู้ปกครองที่ควรได้รับแจ้งเตือนของแบบฝึกหัดชุดนี้

    ระดับชั้นว่าง = ส่งหาทุกคนที่อนุมัติแล้ว
    ระบุระดับชั้น = ส่งเฉพาะคนที่มีลูกเรียนอยู่ระดับนั้นและยัง active
    """
    parents = [p for p in select("parents", limit=1000)
               if p.get("status") == "active" and p.get("line_user_id")]
    level = (level or "").strip()
    if not level:
        return parents

    students = select("students", "parent_id,level,active", limit=2000)
    wanted = {s["parent_id"] for s in students
              if s.get("active") and (s.get("level") or "").strip() == level}
    return [p for p in parents if p["id"] in wanted]


def mark_notified(quiz_id: str | int) -> None:
    update("quizzes", {"notified_at": _now()}, id=f"eq.{quiz_id}")


# ════════════════════════════════════════════════════════
#  รายงานสำหรับครูอ้อย
# ════════════════════════════════════════════════════════

def quiz_report(quiz_id: str | int) -> dict:
    """สรุปผลของแบบฝึกหัด 1 ชุด — ใครทำแล้ว กี่รอบ และข้อไหนผิดเยอะ"""
    quiz = get_quiz(quiz_id)
    if not quiz:
        return {}

    attempts = select("quiz_attempts", quiz_id=f"eq.{quiz_id}", finished="eq.true",
                      order="finished_at.desc", limit=1000)
    students = {s["id"]: s for s in select("students", "id,nickname,level,code")}

    by_student: dict[str, dict] = {}
    for a in attempts:
        sid = a["student_id"]
        stu = students.get(sid) or {}
        full = float(a.get("full_score") or 0)
        pct = round(float(a["score"]) / full * 100) if full else 0
        row = by_student.setdefault(sid, {
            "student_id": sid,
            "nickname": stu.get("nickname", "-"),
            "level": stu.get("level", ""),
            "code": stu.get("code", ""),
            "times": 0, "best": 0, "last_percent": None, "last_at": None,
        })
        row["times"] += 1
        row["best"] = max(row["best"], pct)
        if row["last_at"] is None:
            row["last_percent"] = pct
            row["last_at"] = a.get("finished_at")

    for row in by_student.values():
        row["stars"] = stars_for(row["best"])

    # ข้อไหนเด็กผิดเยอะ — ครูจะได้รู้ว่าต้องสอนซ้ำตรงไหน
    hard: list[dict] = []
    if attempts:
        ids = ",".join(str(a["id"]) for a in attempts[:500])
        answers = select("quiz_attempt_answers", "question_id,is_correct",
                         attempt_id=f"in.({ids})", limit=5000)
        questions = {str(q["id"]): q for q in
                     select("quiz_questions", "id,prompt,sort_order",
                            quiz_id=f"eq.{quiz_id}", limit=300)}
        for qid, q in questions.items():
            mine = [a for a in answers if str(a["question_id"]) == qid]
            if not mine:
                continue
            wrong = sum(1 for a in mine if not a.get("is_correct"))
            hard.append({
                "sort_order": q.get("sort_order"),
                "prompt": q.get("prompt", "")[:80],
                "answered": len(mine),
                "wrong": wrong,
                "wrong_percent": round(wrong / len(mine) * 100),
            })
        hard.sort(key=lambda h: h["wrong_percent"], reverse=True)

    return {
        "quiz": quiz,
        "students": sorted(by_student.values(),
                           key=lambda r: (r["level"], r["nickname"])),
        "hard_questions": hard[:10],
        "attempt_total": len(attempts),
    }
