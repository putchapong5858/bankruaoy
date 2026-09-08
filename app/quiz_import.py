"""
นำเข้าข้อสอบจากไฟล์ — PDF / Word / PowerPoint / ข้อความ

ตั้งใจให้ "เบา" ที่สุด เพราะ Vercel มีเพดานขนาดแพ็กเกจ
    .docx / .pptx   แกะเองด้วย zipfile + xml  (ไม่ต้องลง python-docx / python-pptx)
    .pdf            ใช้ pypdf ซึ่งเป็น pure-python ตัวเล็ก
    .txt            อ่านตรง ๆ

แล้วแยกข้อความเป็นข้อ ๆ ด้วยกฎ (ไม่ใช้ AI ไม่มีค่าใช้จ่าย)
ผลที่ได้เป็นแค่ "ฉบับร่าง" — ครูอ้อยต้องตรวจและเลือกเฉลยก่อนบันทึกเสมอ
"""

from __future__ import annotations

import io
import re
import zipfile

MAX_QUESTIONS = 60          # กันไฟล์ยาวผิดปกติ

# ตัวอักษรที่ใช้เป็นข้อย่อยในข้อสอบไทยและอังกฤษ
THAI_LETTERS = "กขคงจฉช"
ROMAN_LETTERS = "abcdefgh"


class ImportError_(RuntimeError):
    """แยกชื่อไม่ให้ชนกับ ImportError ของ Python"""


# ════════════════════════════════════════════════════════
#  1) ดึงข้อความออกจากไฟล์
# ════════════════════════════════════════════════════════

def _xml_texts(raw: bytes, tag: str) -> list[str]:
    """ดึงข้อความในแท็กที่ระบุออกจาก XML แบบง่าย ๆ"""
    text = raw.decode("utf-8", "ignore")
    pattern = re.compile(rf"<(?:\w+:)?{tag}[^>]*>(.*?)</(?:\w+:)?{tag}>", re.S)
    out = []
    for chunk in pattern.findall(text):
        chunk = re.sub(r"<[^>]+>", "", chunk)
        chunk = (chunk.replace("&amp;", "&").replace("&lt;", "<")
                      .replace("&gt;", ">").replace("&quot;", '"')
                      .replace("&apos;", "'").replace("&#10;", "\n"))
        out.append(chunk)
    return out


def _from_docx(data: bytes) -> str:
    """Word — แต่ละย่อหน้า <w:p> คือหนึ่งบรรทัด"""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        raw = z.read("word/document.xml")
    body = raw.decode("utf-8", "ignore")
    lines = []
    for para in re.split(r"</(?:\w+:)?p>", body):
        text = "".join(_xml_texts(para.encode("utf-8"), "t")).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _from_pptx(data: bytes) -> str:
    """PowerPoint — ไล่ทีละสไลด์ตามลำดับเลขสไลด์"""
    lines = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        slides = sorted(
            (n for n in z.namelist()
             if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)),
        )
        for name in slides:
            for text in _xml_texts(z.read(name), "t"):
                text = text.strip()
                if text:
                    lines.append(text)
    return "\n".join(lines)


def _from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:                       # pragma: no cover
        raise ImportError_(
            "อ่านไฟล์ PDF ไม่ได้ เพราะยังไม่ได้ติดตั้งไลบรารี pypdf บนเซิร์ฟเวอร์"
        ) from exc

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages[:40]:                 # กันไฟล์หนาเกินไป
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages)


def extract_text(filename: str, data: bytes) -> str:
    """ดึงข้อความจากไฟล์ตามนามสกุล"""
    name = (filename or "").lower().strip()
    if not data:
        raise ImportError_("ไฟล์ว่าง กรุณาเลือกไฟล์ใหม่")

    try:
        if name.endswith(".docx"):
            text = _from_docx(data)
        elif name.endswith(".pptx"):
            text = _from_pptx(data)
        elif name.endswith(".pdf"):
            text = _from_pdf(data)
        elif name.endswith((".txt", ".md", ".csv")):
            text = data.decode("utf-8", "ignore")
        elif name.endswith((".doc", ".ppt")):
            raise ImportError_(
                "ไฟล์ .doc และ .ppt เป็นรูปแบบเก่าที่อ่านอัตโนมัติไม่ได้ค่ะ "
                "กรุณาเปิดใน Word/PowerPoint แล้ว Save As เป็น .docx หรือ .pptx ก่อน"
            )
        elif name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            raise ImportError_(
                "ไฟล์รูปภาพอ่านข้อความอัตโนมัติไม่ได้ค่ะ — "
                "ให้ใช้วิธีแนบรูปเป็นโจทย์แทน (เพิ่มข้อใหม่ แล้วแนบรูปในช่อง 'รูปประกอบโจทย์')"
            )
        else:
            raise ImportError_("รองรับเฉพาะไฟล์ .pdf .docx .pptx และ .txt เท่านั้นค่ะ")
    except ImportError_:
        raise
    except zipfile.BadZipFile as exc:
        raise ImportError_("ไฟล์เสียหรือไม่ใช่ไฟล์ตามนามสกุลที่ตั้งไว้") from exc
    except Exception as exc:
        raise ImportError_(f"อ่านไฟล์ไม่สำเร็จ ({str(exc)[:80]})") from exc

    text = text.replace("​", "").strip()
    if not text:
        raise ImportError_(
            "อ่านไฟล์แล้วไม่พบข้อความเลย — ถ้าเป็น PDF ที่มาจากการสแกน "
            "จะเป็นรูปภาพล้วนจึงดึงข้อความไม่ได้ค่ะ"
        )
    return text


# ════════════════════════════════════════════════════════
#  2) แยกข้อความเป็นข้อ ๆ
# ════════════════════════════════════════════════════════

RE_QNUM = re.compile(r"^\s*(?:ข้อ\s*)?(\d{1,3})\s*[\.\)]\s*(.*)$")
RE_OPT = re.compile(rf"^\s*([{THAI_LETTERS}{ROMAN_LETTERS.upper()}{ROMAN_LETTERS}])\s*[\.\)]\s*(.*)$")
RE_ANSWER = re.compile(r"^\s*(?:เฉลย|คำตอบ|ตอบ|answer|ans)\s*[:：\-]?\s*(.+)$", re.I)
# ตัวเลือกหลายอันในบรรทัดเดียว เช่น "ก. 12   ข. 13   ค. 14"
RE_INLINE = re.compile(rf"(?<![^\s])([{THAI_LETTERS}{ROMAN_LETTERS.upper()}{ROMAN_LETTERS}])\s*[\.\)]\s*")


def _letter_index(letter: str) -> int | None:
    letter = (letter or "").strip()
    if letter in THAI_LETTERS:
        return THAI_LETTERS.index(letter)
    low = letter.lower()
    if low in ROMAN_LETTERS:
        return ROMAN_LETTERS.index(low)
    return None


def _split_inline(line: str) -> list[tuple[str, str]]:
    """แยกบรรทัดที่มีหลายตัวเลือกติดกัน คืน [(ตัวอักษร, ข้อความ)]"""
    marks = list(RE_INLINE.finditer(line))
    if len(marks) < 2:
        return []
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(line)
        text = line[m.end():end].strip(" \t·-—")
        if text:
            out.append((m.group(1), text))
    return out if len(out) >= 2 else []


def parse_questions(text: str) -> list[dict]:
    """
    แปลงข้อความเป็นรายการคำถามฉบับร่าง

    คืน [{prompt, options:[str], correct_index:int|None, note:str}]
    correct_index = None แปลว่าหาเฉลยในไฟล์ไม่เจอ ครูต้องเลือกเอง
    """
    questions: list[dict] = []
    current: dict | None = None

    def close():
        nonlocal current
        if current and current["prompt"].strip():
            current["prompt"] = current["prompt"].strip()
            questions.append(current)
        current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if len(questions) >= MAX_QUESTIONS:
            break

        # ── บรรทัดเฉลย ──
        answer = RE_ANSWER.match(line)
        if answer and current:
            value = answer.group(1).strip()
            idx = _letter_index(value[:1]) if value else None
            if idx is not None and idx < max(1, len(current["options"])):
                current["correct_index"] = idx
            else:
                # เฉลยเขียนเป็นข้อความ — จับคู่กับตัวเลือกที่ตรงกัน
                for i, opt in enumerate(current["options"]):
                    if opt.strip().lower() == value.strip().lower():
                        current["correct_index"] = i
                        break
                else:
                    current["answer_text"] = value
            continue

        # ── ขึ้นข้อใหม่ ──
        qnum = RE_QNUM.match(line)
        if qnum and not RE_OPT.match(line):
            close()
            current = {"prompt": qnum.group(2).strip(), "options": [],
                       "correct_index": None, "answer_text": "", "note": ""}
            continue

        if current is None:
            continue        # ข้อความก่อนข้อแรก เช่น หัวกระดาษ — ข้ามไป

        # ── ตัวเลือกหลายอันในบรรทัดเดียว ──
        inline = _split_inline(line)
        if inline:
            for letter, value in inline:
                current["options"].append(value)
            continue

        # ── ตัวเลือกเดี่ยว ──
        opt = RE_OPT.match(line)
        if opt and opt.group(2).strip():
            current["options"].append(opt.group(2).strip())
            continue

        # ── บรรทัดต่อของโจทย์ ──
        if current["options"]:
            current["options"][-1] += " " + line
        else:
            current["prompt"] += " " + line

    close()

    # เก็บกวาดและติดหมายเหตุให้ครูเห็นว่าข้อไหนต้องดูเป็นพิเศษ
    cleaned = []
    for q in questions:
        q["options"] = [o.strip() for o in q["options"] if o.strip()][:6]
        if q.get("answer_text") and q["correct_index"] is None:
            for i, opt in enumerate(q["options"]):
                if q["answer_text"].lower() in opt.lower():
                    q["correct_index"] = i
                    break
        if len(q["options"]) < 2:
            q["note"] = "ไม่พบตัวเลือก — ต้องพิมพ์ตัวเลือกเอง"
        elif q["correct_index"] is None:
            q["note"] = "ไม่พบเฉลยในไฟล์ — กรุณาเลือกข้อที่ถูก"
        cleaned.append(q)
    return cleaned


def summarize(questions: list[dict]) -> dict:
    """สรุปผลการอ่านไฟล์ ไว้โชว์ให้ครูดูก่อนบันทึก"""
    ready = sum(1 for q in questions
                if len(q["options"]) >= 2 and q["correct_index"] is not None)
    return {
        "total": len(questions),
        "ready": ready,
        "need_answer": sum(1 for q in questions
                           if len(q["options"]) >= 2 and q["correct_index"] is None),
        "need_options": sum(1 for q in questions if len(q["options"]) < 2),
    }
