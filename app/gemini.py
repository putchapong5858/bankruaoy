"""
ผู้ช่วยสร้างแบบฝึกหัดด้วย Gemini

ใช้ REST ตรง ๆ ผ่าน httpx (ไม่ลงไลบรารีเพิ่ม แพ็กเกจบน Vercel จะได้ไม่บวม)
ทุกฟังก์ชันคืนค่าหน้าตาเดียวกับ quiz_import.parse_questions() คือ

    [{prompt, options: [str], correct_index: int|None, explanation: str, note: str}]

จะได้ใช้หน้าตรวจทานเดิมร่วมกันได้ — ครูอ้อยตรวจและแก้ก่อนบันทึกเสมอ
ไม่มีข้อไหนเข้าฐานข้อมูลโดยที่ครูยังไม่เห็น

ต้องตั้ง env var GEMINI_API_KEY ที่ Vercel ก่อนใช้งาน
"""

from __future__ import annotations

import base64
import json
import mimetypes

import httpx

from . import config

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# ลองรุ่นแรกก่อน ถ้าบัญชียังไม่มีสิทธิ์ค่อยไล่ลงมา
MODEL_CANDIDATES = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

MAX_QUESTIONS = 40
MAX_FILE_MB = 8

# รูปแบบผลลัพธ์ที่บังคับให้ Gemini ตอบกลับมา
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "prompt": {"type": "STRING"},
                    "options": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "correct_index": {"type": "INTEGER"},
                    "explanation": {"type": "STRING"},
                },
                "required": ["prompt", "options", "correct_index"],
            },
        }
    },
    "required": ["questions"],
}

RULES = """คุณคือครูสอนพิเศษเด็กเล็กของ "บ้านครูอ้อย" ที่ประเทศไทย
สร้างข้อสอบปรนัยสำหรับเด็กไทย โดยยึดกติกาต่อไปนี้อย่างเคร่งครัด

1. ภาษาไทยง่าย ๆ สั้น ๆ ประโยคเดียวจบ เด็กอ่านออกเอง
2. ทุกข้อมีตัวเลือก 3 ตัว มีคำตอบที่ถูกเพียง 1 ตัว ระบุด้วย correct_index (เริ่มนับ 0)
3. ตัวเลือกที่ผิดต้องดูสมเหตุสมผล ไม่ใช่ผิดจนเดาได้ทันที และต้องไม่ถูกด้วย
4. ห้ามใช้คำว่า "ข้อใดต่อไปนี้ถูกต้อง" "ข้อใดไม่ถูกต้อง" หรือตัวเลือก
   "ถูกทุกข้อ" / "ไม่มีข้อถูก" เพราะเด็กเล็กสับสน
5. explanation คือคำอธิบายสั้น ๆ ที่เด็กเข้าใจ ไม่เกิน 1 บรรทัด
   ใช้น้ำเสียงให้กำลังใจ ไม่ดุ
6. ใส่อีโมจิได้ 1 ตัวต่อข้อเพื่อให้น่ารัก แต่ห้ามใส่จนรก และห้ามใส่ในตัวเลือก
7. ห้ามออกข้อซ้ำกัน และห้ามให้คำตอบที่ถูกอยู่ตำแหน่งเดิมทุกข้อ
   ให้กระจายตำแหน่งเฉลย
8. เนื้อหาต้องเหมาะกับเด็ก ไม่มีความรุนแรง ความน่ากลัว หรือเรื่องผู้ใหญ่"""


class GeminiError(RuntimeError):
    pass


def is_ready() -> bool:
    return bool(getattr(config, "GEMINI_API_KEY", ""))


def _need_key() -> str:
    key = getattr(config, "GEMINI_API_KEY", "")
    if not key:
        raise GeminiError(
            "ยังไม่ได้ตั้งค่ากุญแจของ Gemini — ไปที่ Vercel → Settings → "
            "Environment Variables แล้วเพิ่ม GEMINI_API_KEY ก่อนใช้งานค่ะ")
    return key


def _models_to_try() -> list[str]:
    picked = (getattr(config, "GEMINI_MODEL", "") or "").strip()
    if picked:
        return [picked] + [m for m in MODEL_CANDIDATES if m != picked]
    return list(MODEL_CANDIDATES)


def _post(model: str, body: dict) -> httpx.Response:
    from .db import _conn          # ใช้การเชื่อมต่อร่วมกัน จะได้ไม่จับมือ TLS ใหม่
    return _conn().post(
        f"{API_ROOT}/models/{model}:generateContent",
        params={"key": _need_key()},
        json=body,
        timeout=90.0,
    )


def _generate(parts: list[dict], want: int) -> list[dict]:
    """ยิงไปหา Gemini แล้วแปลงคำตอบเป็นรายการคำถามฉบับร่าง"""
    body = {
        "systemInstruction": {"parts": [{"text": RULES}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        },
        # กันเนื้อหาไม่เหมาะกับเด็ก ให้เข้มกว่าค่าเริ่มต้น
        "safetySettings": [
            {"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            for c in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                      "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                      "HARM_CATEGORY_DANGEROUS_CONTENT")
        ],
    }

    last = ""
    for model in _models_to_try():
        try:
            res = _post(model, body)
        except httpx.HTTPError as exc:
            last = f"ต่อกับ Gemini ไม่ได้ ({str(exc)[:120]})"
            continue

        if res.status_code == 404:          # บัญชีนี้ไม่มีรุ่นนี้ ลองรุ่นถัดไป
            last = f"ไม่มีรุ่น {model} ในบัญชีนี้"
            continue
        if res.status_code in (401, 403):
            raise GeminiError("กุญแจ Gemini ไม่ถูกต้องหรือหมดสิทธิ์ — "
                              "ลองสร้างกุญแจใหม่ที่ aistudio.google.com/apikey")
        if res.status_code == 429:
            raise GeminiError("ใช้เกินโควตาฟรีของ Gemini ในช่วงนี้ "
                              "รอสักครู่แล้วลองใหม่อีกครั้งค่ะ")
        if res.status_code >= 400:
            last = f"Gemini ตอบ {res.status_code}: {res.text[:200]}"
            continue

        return _read(res.json(), want)

    raise GeminiError(last or "เรียก Gemini ไม่สำเร็จ")


def _read(data: dict, want: int) -> list[dict]:
    candidates = data.get("candidates") or []
    if not candidates:
        reason = ((data.get("promptFeedback") or {}).get("blockReason") or "")
        if reason:
            raise GeminiError("Gemini ไม่ยอมตอบเพราะเนื้อหาสุ่มเสี่ยง "
                              "ลองเปลี่ยนหัวข้อหรือใช้คำอื่นดูค่ะ")
        raise GeminiError("Gemini ไม่ได้ส่งคำตอบกลับมา ลองใหม่อีกครั้งค่ะ")

    text = "".join(
        p.get("text", "")
        for p in (candidates[0].get("content") or {}).get("parts", [])
    ).strip()
    if not text:
        raise GeminiError("Gemini ส่งคำตอบว่างมา ลองใหม่อีกครั้งค่ะ")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise GeminiError("อ่านคำตอบของ Gemini ไม่ออก ลองกดสร้างใหม่อีกครั้งค่ะ")

    return _clean(payload.get("questions") or [], want)


def _clean(rows: list, want: int) -> list[dict]:
    """คัดกรองผลลัพธ์ก่อนส่งให้ครูตรวจ — กันข้อพัง ๆ ไม่ให้โผล่ในหน้าตรวจทาน"""
    out: list[dict] = []
    seen: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        prompt = str(row.get("prompt") or "").strip()
        if not prompt:
            continue

        key = prompt.lower().replace(" ", "")
        if key in seen:                 # ข้อซ้ำ ตัดทิ้ง
            continue

        options, dup = [], set()
        for opt in (row.get("options") or []):
            label = str(opt).strip()
            if label and label.lower() not in dup:
                dup.add(label.lower())
                options.append(label)
        options = options[:4]

        try:
            correct = int(row.get("correct_index"))
        except (TypeError, ValueError):
            correct = -1

        note = ""
        if len(options) < 2:
            note = "ตัวเลือกไม่ครบ ครูเติมเองก่อนบันทึกนะคะ"
        elif not 0 <= correct < len(options):
            correct, note = -1, "AI ไม่ได้ระบุเฉลย กรุณาเลือกเฉลยก่อนบันทึก"

        seen.add(key)
        out.append({
            "prompt": prompt,
            "options": options,
            "correct_index": correct if correct >= 0 else None,
            "explanation": str(row.get("explanation") or "").strip()[:200],
            "note": note,
        })
        if len(out) >= want:
            break
    return out


def _count(want) -> int:
    try:
        n = int(want)
    except (TypeError, ValueError):
        n = 10
    return max(1, min(n, MAX_QUESTIONS))


# ════════════════════════════════════════════════════════
#  4 วิธีสร้างข้อสอบ
# ════════════════════════════════════════════════════════

def from_topic(topic: str, level: str = "", subject: str = "",
               count: int = 10, extra: str = "") -> list[dict]:
    """พิมพ์หัวข้อ แล้วให้ Gemini ออกข้อสอบให้"""
    topic = (topic or "").strip()
    if not topic:
        raise GeminiError("กรุณาพิมพ์หัวข้อที่อยากให้ออกข้อสอบก่อนค่ะ")

    n = _count(count)
    ask = [f"ออกข้อสอบ {n} ข้อ เรื่อง “{topic}”"]
    if subject.strip():
        ask.append(f"วิชา {subject.strip()}")
    if level.strip():
        ask.append(f"สำหรับนักเรียนระดับ {level.strip()} "
                   f"ให้ความยากเหมาะกับวัยนี้จริง ๆ")
    if extra.strip():
        ask.append(f"ข้อกำหนดเพิ่มเติมจากคุณครู: {extra.strip()}")
    return _generate([{"text": "\n".join(ask)}], n)


def from_text(raw: str, count: int = 20, note: str = "") -> list[dict]:
    """วางข้อความดิบ แล้วให้ Gemini จัดเป็นข้อ ๆ พร้อมเฉลย"""
    raw = (raw or "").strip()
    if len(raw) < 20:
        raise GeminiError("ข้อความสั้นเกินไป กรุณาวางเนื้อหาที่ยาวกว่านี้ค่ะ")

    n = _count(count)
    ask = (
        f"ด้านล่างคือข้อสอบที่พิมพ์มาแบบไม่เป็นระเบียบ "
        f"ช่วยจัดให้เป็นข้อ ๆ ไม่เกิน {n} ข้อ\n"
        "ถ้าในข้อความมีเฉลยอยู่แล้วให้ใช้เฉลยนั้น ห้ามเดาเอง\n"
        "ถ้าตัวเลือกมีไม่ครบ 3 ตัว ให้แต่งตัวเลือกที่ผิดเพิ่มให้สมเหตุสมผล\n"
    )
    if note.strip():
        ask += f"หมายเหตุจากคุณครู: {note.strip()}\n"
    return _generate([{"text": ask + "\n---\n" + raw[:30000]}], n)


def from_files(files: list[tuple[str, bytes]], count: int = 20,
               note: str = "") -> list[dict]:
    """
    ถ่ายรูปใบงานหรืออัปโหลด PDF แล้วให้ Gemini อ่านออกมาเป็นข้อสอบ

    วิธีนี้อ่าน "รูปตัวหนังสือ" ได้ ต่างจากการนำเข้าไฟล์แบบเดิม
    ที่อ่านได้เฉพาะไฟล์ที่มีตัวอักษรจริง ๆ อยู่ข้างใน
    """
    parts: list[dict] = []
    for name, blob in files:
        if not blob:
            continue
        if len(blob) > MAX_FILE_MB * 1024 * 1024:
            raise GeminiError(f"ไฟล์ {name} ใหญ่เกิน {MAX_FILE_MB} MB "
                              "กรุณาถ่ายใหม่ให้เล็กลงหรือย่อไฟล์ก่อนค่ะ")
        mime = mimetypes.guess_type(name)[0] or "image/jpeg"
        if not (mime.startswith("image/") or mime == "application/pdf"):
            raise GeminiError(f"ไฟล์ {name} ไม่ใช่รูปภาพหรือ PDF ค่ะ")
        parts.append({"inline_data": {
            "mime_type": mime,
            "data": base64.b64encode(blob).decode("ascii"),
        }})

    if not parts:
        raise GeminiError("กรุณาเลือกรูปใบงานหรือไฟล์ PDF ก่อนค่ะ")

    n = _count(count)
    ask = (
        f"อ่านข้อสอบจากไฟล์ที่แนบมา แล้วพิมพ์ออกมาเป็นข้อ ๆ ไม่เกิน {n} ข้อ\n"
        "คัดลอกโจทย์และตัวเลือกตามที่เห็นในภาพให้ตรงที่สุด อย่าแต่งเพิ่มเอง\n"
        "ถ้าในภาพมีวงกลมหรือเครื่องหมายเฉลยไว้ ให้ใช้เป็นเฉลย\n"
        "ถ้าไม่มีเฉลยในภาพ ให้คิดคำตอบที่ถูกต้องเองตามหลักวิชา\n"
        "ถ้าโจทย์เป็นรูปภาพที่พิมพ์เป็นตัวอักษรไม่ได้ ให้บรรยายเป็นคำสั้น ๆ แทน\n"
    )
    if note.strip():
        ask += f"หมายเหตุจากคุณครู: {note.strip()}\n"
    return _generate([{"text": ask}] + parts, n)


def polish(questions: list[dict]) -> list[dict]:
    """เอาข้อที่มีอยู่แล้วมาให้ Gemini เกลาภาษาให้เด็กเข้าใจง่ายขึ้น"""
    rows = []
    for q in questions:
        if q.get("kind") not in (None, "choice", "truefalse"):
            continue
        opts = [o.get("label", "") for o in (q.get("options") or [])]
        if len(opts) < 2:
            continue
        correct = next((i for i, o in enumerate(q.get("options") or [])
                        if o.get("is_correct")), 0)
        rows.append({"prompt": q.get("prompt", ""), "options": opts,
                     "correct_index": correct})

    if not rows:
        raise GeminiError("ยังไม่มีข้อแบบเลือกตอบให้เกลา — "
                          "เพิ่มข้อก่อนแล้วค่อยกดปุ่มนี้ค่ะ")

    ask = (
        "ด้านล่างคือข้อสอบที่มีอยู่แล้ว ช่วยเกลาให้เด็กเล็กอ่านเข้าใจง่ายขึ้น\n"
        "ห้ามเปลี่ยนความหมายและห้ามเปลี่ยนคำตอบที่ถูก (correct_index ต้องชี้คำเดิม)\n"
        "ทำได้แค่: ใช้คำที่ง่ายขึ้น ตัดคำฟุ่มเฟือย เติมอีโมจิ 1 ตัวให้น่ารัก "
        "และเขียน explanation ให้กำลังใจ\n"
        "ส่งกลับมาให้ครบทุกข้อ เรียงลำดับเดิม\n\n"
        + json.dumps(rows, ensure_ascii=False)
    )
    out = _generate([{"text": ask}], len(rows))
    for q in out:
        q["note"] = q["note"] or "ฉบับเกลาใหม่ — เทียบกับของเดิมก่อนบันทึกนะคะ"
    return out

# ════════════════════════════════════════════════════════
#  ตรวจสถานะ — ใช้เช็คว่ากุญแจใช้ได้ไหมโดยไม่ต้องล็อกอิน
# ════════════════════════════════════════════════════════

_probe_cache: dict = {"at": 0.0, "data": None}
PROBE_COOLDOWN = 60          # วินาที — กันคนยิงรัว ๆ


def status() -> dict:
    """
    เช็คว่ากุญแจ Gemini ใช้ได้จริงไหม และบัญชีนี้มีรุ่นอะไรให้ใช้บ้าง

    เรียก GET /models ซึ่งเป็นการ "ดูรายการ" ไม่ใช่การสร้างข้อความ
    จึงไม่กินโควตาและไม่มีค่าใช้จ่าย และไม่เคยส่งค่ากุญแจกลับออกไป
    ผลถูกแคชไว้ 1 นาที กันคนกดรัว
    """
    import time

    if not is_ready():
        return {"key_set": False, "ok": False,
                "detail": "ยังไม่ได้ตั้ง GEMINI_API_KEY ที่ Vercel"}

    now = time.time()
    if _probe_cache["data"] and now - _probe_cache["at"] < PROBE_COOLDOWN:
        return dict(_probe_cache["data"], cached=True)

    out: dict = {"key_set": True}
    try:
        from .db import _conn
        res = _conn().get(f"{API_ROOT}/models",
                          params={"key": _need_key(), "pageSize": 200},
                          timeout=20.0)
        if res.status_code in (401, 403):
            out.update(ok=False, detail="กุญแจไม่ถูกต้องหรือถูกปิดสิทธิ์")
        elif res.status_code >= 400:
            out.update(ok=False,
                       detail=f"Gemini ตอบ {res.status_code}: {res.text[:160]}")
        else:
            usable = [
                m.get("name", "").split("/")[-1]
                for m in (res.json().get("models") or [])
                if "generateContent" in (m.get("supportedGenerationMethods") or [])
            ]
            picked = next((m for m in _models_to_try() if m in usable), "")
            out.update(ok=bool(picked), models=usable[:40],
                       will_use=picked,
                       detail="พร้อมใช้งาน" if picked else
                              "กุญแจใช้ได้ แต่ไม่พบรุ่นที่โค้ดรองรับ — "
                              "ตั้ง GEMINI_MODEL เป็นรุ่นในรายการ models")
    except Exception as exc:
        out.update(ok=False, detail=f"ต่อกับ Gemini ไม่ได้ ({str(exc)[:140]})")

    _probe_cache.update(at=now, data=out)
    return out
