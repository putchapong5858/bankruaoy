"""
เสียงอ่านแบบฝึกหัดด้วย Gemini TTS

ทำไมต้องเปลี่ยนจากเสียงเดิม
---------------------------
เดิมใช้ Web Speech API คือ "เสียงที่ติดมากับเครื่องของเด็ก" ปัญหาคือ
  • มือถือหลายเครื่องไม่มีเสียงภาษาไทยติดมา → กดปุ่ม 🔊 แล้วเงียบสนิท
  • เสียงคนละยี่ห้อคนละรุ่นไม่เหมือนกันเลย คุมคุณภาพไม่ได้
  • เสียงสังเคราะห์รุ่นเก่าฟังแข็ง เด็กเล็กฟังแล้วจับคำยาก

เปลี่ยนมาสร้างเสียงที่เซิร์ฟเวอร์ด้วย Gemini แทน เด็กทุกคนจะได้ยิน
เสียงเดียวกัน คุณภาพเดียวกัน ไม่ว่าจะใช้เครื่องอะไร และอ่านได้ทั้ง
ไทยและอังกฤษในไฟล์เดียวกัน (Gemini รู้เองว่าคำไหนภาษาอะไร)

เรื่องค่าใช้จ่าย — สำคัญ
------------------------
ทุกไฟล์ที่สร้างแล้วจะถูกเก็บไว้ใน Supabase Storage ถาวร ข้อความเดิม +
เสียงเดิม = ไฟล์เดิม ไม่ต้องสร้างซ้ำอีกเลย เด็ก 30 คนทำชุดเดียวกัน
ก็เสียค่าสร้างแค่ครั้งแรกครั้งเดียว

กุญแจ GEMINI_API_KEY ตั้งที่ Vercel เท่านั้น ห้ามส่งออกฝั่งเบราว์เซอร์
"""

from __future__ import annotations

import base64
import hashlib
import re
import struct
import time

import httpx

from . import config

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# เรียงรุ่นที่จะลอง — เอารุ่นที่ใช้วิธีเรียกแบบเดียวกับที่เราเขียนไว้ขึ้นก่อน
# รุ่น 3.1 ของ Google เปลี่ยนไปใช้วิธีเรียกแบบใหม่ จึงวางไว้ท้ายสุดเป็นตัวเผื่อ
# (ถ้าเรียกไม่ได้ทุกตัว จะไปถาม Google ว่าบัญชีนี้มีรุ่นไหนให้ใช้บ้าง)
MODEL_CANDIDATES = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview",
]

BUCKET = "tts"
MAX_CHARS = 400          # โจทย์ยาวกว่านี้ไม่มีในแบบฝึกหัดเด็กเล็ก
SAMPLE_RATE = 24000      # Gemini ส่ง PCM 24kHz 16bit mono มาเสมอ

# ── เสียงที่คัดมาให้ครูอ้อยเลือก 5 แบบ ──────────────────────────
# คัดจากเสียงทั้งหมดของ Gemini เอาเฉพาะโทนนุ่มนวล ชัดเจน ไม่ดุ
# เหมาะกับเด็กอนุบาล–ประถม และอ่านภาษาไทยได้เป็นธรรมชาติ
VOICES = [
    {"id": "Achernar",     "name": "นุ่มนวล",   "note": "เสียงผู้หญิง นุ่ม เบา อ่อนโยน เหมาะกับเด็กเล็กที่สุด"},
    {"id": "Vindemiatrix", "name": "อ่อนโยน",   "note": "เสียงผู้หญิง สุภาพ ใจเย็น เหมือนครูค่อย ๆ อธิบาย"},
    {"id": "Sulafat",      "name": "อบอุ่น",    "note": "เสียงผู้หญิง อบอุ่น มีน้ำเสียงเหมือนคุณแม่เล่านิทาน"},
    {"id": "Leda",         "name": "สดใส",      "note": "เสียงผู้หญิงสาว สดใส กระฉับกระเฉง ปลุกให้เด็กตื่นตัว"},
    {"id": "Achird",       "name": "เป็นกันเอง", "note": "เสียงผู้ชาย เป็นกันเอง ไม่ดุ สลับให้เด็กไม่เบื่อเสียงเดิม"},
]

VOICE_IDS = [v["id"] for v in VOICES]
DEFAULT_VOICE = VOICE_IDS[0]

# ประโยคตัวอย่างให้ครูกดฟังก่อนเลือก — มีทั้งไทยและอังกฤษปนกันในประโยคเดียว
# เพราะแบบฝึกหัดจริงก็ปนแบบนี้ จะได้ยินว่าเสียงนี้สลับภาษาได้ไหลลื่นแค่ไหน
SAMPLES = [
    "สวัสดีค่ะหนู ๆ วันนี้เรามาทำแบบฝึกหัดกันนะคะ",
    "รูปนี้คือสัตว์อะไรเอ่ย ภาษาอังกฤษเขียนว่า Elephant ค่ะ",
    "เก่งมากค่ะ ตอบถูกแล้ว ลองข้อต่อไปกันเลย",
]

# คำสั่งกำกับน้ำเสียง — Gemini อ่าน "คำสั่ง: ข้อความ" แล้วจะไม่อ่านคำสั่งออกมา
STYLE = ("อ่านข้อความต่อไปนี้ให้เด็กอนุบาลฟัง ด้วยน้ำเสียงนุ่มนวลอบอุ่นแบบคุณครู "
         "ออกเสียงชัดเจนทุกคำ ความเร็วปกติเป็นธรรมชาติ ไม่ช้าจนน่าเบื่อ "
         "คำภาษาอังกฤษให้ออกเสียงแบบเจ้าของภาษา")


class TtsError(RuntimeError):
    pass


# ══ ค่าตั้งว่าตอนนี้ใช้เสียงไหน ═══════════════════════════════════
# เก็บใน site_settings เพื่อให้ครูเปลี่ยนเสียงได้เองโดยไม่ต้อง deploy ใหม่
# แต่ถามฐานข้อมูลทุกครั้งที่เปิดหน้าก็ช้า จึงจำไว้ในหน่วยความจำสักพัก
_cached_voice = ""
_cached_at = 0.0
_CACHE_SEC = 120


def is_ready() -> bool:
    return bool(getattr(config, "GEMINI_API_KEY", ""))


def current_voice(fresh: bool = False) -> str:
    """เสียงที่เลือกใช้อยู่ทั้งเว็บ — พังเมื่อไหร่ก็ถอยไปใช้ค่าเริ่มต้น"""
    global _cached_voice, _cached_at
    now = time.time()
    if not fresh and _cached_voice and (now - _cached_at) < _CACHE_SEC:
        return _cached_voice
    voice = DEFAULT_VOICE
    try:
        from . import db
        saved = (db.get_setting("tts_voice") or "").strip()
        if saved in VOICE_IDS:
            voice = saved
    except Exception:
        pass                       # ฐานข้อมูลมีปัญหาก็ยังอ่านออกเสียงได้
    _cached_voice = voice
    _cached_at = now
    return voice


def set_voice(voice: str) -> str:
    """ครูเลือกเสียงใหม่ — บันทึกแล้วล้างที่จำไว้ทันที"""
    global _cached_voice, _cached_at
    if voice not in VOICE_IDS:
        raise TtsError("ไม่รู้จักเสียงนี้")
    from . import db
    db.upsert_setting("tts_voice", voice)
    _cached_voice, _cached_at = voice, time.time()
    return voice


# ══ ที่อยู่ไฟล์เสียง ══════════════════════════════════════════════
_LETTER_PAIR = re.compile(r"^([A-Za-z])\s+([A-Za-z])$")
_HAS_WORD = re.compile(r"[0-9A-Za-z฀-๿]")


def clean(text: str) -> str:
    """แปลงข้อความโจทย์ให้เป็น "สิ่งที่ควรอ่านออกเสียงจริง ๆ"

    ต้องทำเหมือนกันทุกครั้ง เพราะข้อความนี้คือกุญแจของชื่อไฟล์เสียง
    ข้อความเดียวกันต้องได้ชื่อไฟล์เดียวกันเสมอ ไม่งั้นจะสร้างซ้ำไม่รู้จบ

    1. บรรทัดแรกที่เป็นอีโมจิล้วน เป็นรูปประกอบให้เด็กดู ไม่ใช่คำให้อ่าน — ตัดทิ้ง
    2. ตัวคั่น | เดิมมีไว้บอกว่า "ท่อนนี้อังกฤษ ท่อนนี้ไทย" เพราะเสียงของเครื่อง
       อ่านสองภาษาในประโยคเดียวไม่ได้ — Gemini อ่านได้เอง จึงรวมเป็นประโยคเดียว
    3. "C c" (ตัวใหญ่-ตัวเล็กของอักษรเดียวกัน) ให้อ่านว่า "C" ครั้งเดียวพอ
    """
    t = str(text or "").replace("\r", "")
    head, sep, rest = t.partition("\n")
    if sep and head.strip() and not _HAS_WORD.search(head):
        t = rest                                   # บรรทัดอีโมจิล้วน — ไม่ต้องอ่าน
    t = " ".join(t.replace("|", " ").split())
    pair = _LETTER_PAIR.match(t)
    if pair and pair.group(1).lower() == pair.group(2).lower():
        t = pair.group(1).upper()
    return t[:MAX_CHARS]


def speakable(text: str) -> bool:
    """สั้นเกินไปหรือเป็นสัญลักษณ์ล้วน ก็ไม่ต้องเปลืองโควตาสร้างเสียง"""
    t = clean(text)
    return bool(t) and bool(_HAS_WORD.search(t))


def path_for(text: str, voice: str = "") -> str:
    voice = voice if voice in VOICE_IDS else current_voice()
    digest = hashlib.sha256(f"{voice}\n{clean(text)}".encode("utf-8")).hexdigest()
    return f"{voice}/{digest}.wav"


def public_url(text: str, voice: str = "") -> str:
    """ที่อยู่ไฟล์เสียงบน CDN — คำนวณได้เลยโดยไม่ต้องต่อเน็ต

    หน้าแบบฝึกหัดฝังที่อยู่นี้ไว้ตรง ๆ เด็กจึงโหลดเสียงจาก CDN ได้ทันที
    ไม่ต้องผ่านเซิร์ฟเวอร์ของเราเลย ถ้าไฟล์ยังไม่มี (404) หน้าเว็บค่อย
    ถอยไปเรียก /tts ให้สร้างให้
    """
    base = (getattr(config, "SUPABASE_URL", "") or "").rstrip("/")
    if not base or not is_ready() or not speakable(text):
        return ""
    return f"{base}/storage/v1/object/public/{BUCKET}/{path_for(text, voice)}"


# ══ คุยกับ Supabase Storage ═══════════════════════════════════════
def _storage_headers() -> dict[str, str]:
    key = getattr(config, "SUPABASE_SERVICE_KEY", "")
    if not key:
        raise TtsError("ยังไม่ได้ตั้งค่า SUPABASE_SERVICE_KEY")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _conn() -> httpx.Client:
    from .db import _conn as shared      # ใช้การเชื่อมต่อร่วมกับ db จะได้ไม่ช้า
    return shared()


def exists(path: str) -> bool:
    base = (getattr(config, "SUPABASE_URL", "") or "").rstrip("/")
    try:
        res = _conn().head(
            f"{base}/storage/v1/object/public/{BUCKET}/{path}", timeout=8.0)
        return res.status_code == 200
    except httpx.HTTPError:
        return False


def stored(voice: str = "") -> set[str]:
    """ชื่อไฟล์เสียงทั้งหมดที่มีอยู่แล้วของเสียงนี้

    ใช้ตอนสร้างเสียงล่วงหน้าทั้งชุด — ถามทีละไฟล์ 100 กว่ารอบจะช้ามาก
    ขอรายชื่อทั้งโฟลเดอร์ทีเดียวแล้วเทียบในหน่วยความจำเร็วกว่าเยอะ
    """
    voice = voice if voice in VOICE_IDS else current_voice()
    base = (getattr(config, "SUPABASE_URL", "") or "").rstrip("/")
    headers = _storage_headers() | {"Content-Type": "application/json"}
    names: set[str] = set()
    offset, page = 0, 1000
    try:
        while True:
            res = _conn().post(
                f"{base}/storage/v1/object/list/{BUCKET}",
                headers=headers, timeout=20.0,
                json={"prefix": f"{voice}/", "limit": page, "offset": offset},
            )
            if res.status_code >= 400:
                break
            rows = res.json() or []
            names.update(r.get("name") or "" for r in rows)
            if len(rows) < page:
                break
            offset += page
    except (httpx.HTTPError, ValueError):
        pass
    return names


def _upload(path: str, data: bytes) -> None:
    base = (getattr(config, "SUPABASE_URL", "") or "").rstrip("/")
    headers = _storage_headers()
    headers["Content-Type"] = "audio/wav"
    headers["x-upsert"] = "true"
    headers["Cache-Control"] = "public, max-age=31536000, immutable"
    res = _conn().post(f"{base}/storage/v1/object/{BUCKET}/{path}",
                       content=data, headers=headers, timeout=30.0)
    if res.status_code >= 400:
        raise TtsError(f"เก็บไฟล์เสียงไม่สำเร็จ ({res.status_code})")


# ══ สร้างเสียงจาก Gemini ══════════════════════════════════════════
def _wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    """ห่อ PCM ดิบให้เป็นไฟล์ WAV ที่เบราว์เซอร์เล่นได้

    Gemini ส่ง PCM 16 บิต mono มาเปล่า ๆ ไม่มีหัวไฟล์ ถ้าส่งให้เบราว์เซอร์
    ตรง ๆ จะเล่นไม่ออก ต้องเติมหัว RIFF 44 ไบต์ให้ก่อน
    """
    ch, bits = 1, 16
    block = ch * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, ch, rate, rate * block, block, bits)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def _models_to_try() -> list[str]:
    picked = (getattr(config, "GEMINI_TTS_MODEL", "") or "").strip()
    if picked:
        return [picked] + [m for m in MODEL_CANDIDATES if m != picked]
    return list(MODEL_CANDIDATES)


def available_models() -> list[str]:
    """ถาม Google ว่ากุญแจนี้ใช้รุ่น TTS ไหนได้บ้าง — ใช้ตอนตรวจสุขภาพระบบ"""
    key = getattr(config, "GEMINI_API_KEY", "")
    if not key:
        return []
    try:
        res = _conn().get(f"{API_ROOT}/models",
                          params={"key": key, "pageSize": 200}, timeout=20.0)
        if res.status_code >= 400:
            return []
        names = []
        for m in (res.json().get("models") or []):
            name = (m.get("name") or "").split("/")[-1]
            if "tts" in name.lower():
                names.append(name)
        return names
    except (httpx.HTTPError, ValueError):
        return []


def generate(text: str, voice: str = "") -> bytes:
    """เรียก Gemini ให้อ่านข้อความ แล้วคืนไฟล์ WAV"""
    key = getattr(config, "GEMINI_API_KEY", "")
    if not key:
        raise TtsError("ยังไม่ได้ตั้งค่า GEMINI_API_KEY ที่ Vercel")

    said = clean(text)
    if not said:
        raise TtsError("ไม่มีข้อความให้อ่าน")

    voice = voice if voice in VOICE_IDS else current_voice()
    body = {
        "contents": [{"parts": [{"text": f"{STYLE}:\n{said}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }

    tried = _models_to_try()
    last = ""
    while tried:
        model = tried.pop(0)
        try:
            res = _conn().post(f"{API_ROOT}/models/{model}:generateContent",
                               params={"key": key}, json=body, timeout=60.0)
        except httpx.HTTPError as exc:
            last = f"ต่อกับ Gemini ไม่ได้ ({str(exc)[:100]})"
            continue

        if res.status_code == 404:
            last = f"บัญชีนี้ยังไม่มีรุ่น {model}"
            if not tried:                       # หมดรายการที่เดาไว้แล้ว
                extra = [m for m in available_models() if m not in MODEL_CANDIDATES]
                tried = extra                   # ลองรุ่นที่บัญชีนี้มีจริง
            continue
        if res.status_code in (401, 403):
            raise TtsError("กุญแจ Gemini ไม่ถูกต้องหรือยังไม่เปิดสิทธิ์ใช้เสียง")
        if res.status_code == 429:
            raise TtsError("ใช้เกินโควตาของ Gemini ในช่วงนี้ รอสักครู่แล้วลองใหม่")
        if res.status_code >= 400:
            last = f"Gemini ตอบ {res.status_code}: {res.text[:160]}"
            continue

        pcm, rate = _read_audio(res.json())
        return _wav(pcm, rate)

    raise TtsError(last or "สร้างเสียงไม่สำเร็จ")


def _rate_of(mime: str) -> int:
    for chunk in (mime or "").split(";"):      # เช่น audio/L16;codec=pcm;rate=24000
        chunk = chunk.strip()
        if chunk.startswith("rate="):
            try:
                return int(chunk[5:])
            except ValueError:
                pass
    return SAMPLE_RATE


def _read_audio(data: dict) -> tuple[bytes, int]:
    # วิธีเรียกแบบใหม่ของ Google คืนเสียงไว้อีกที่หนึ่ง — รองรับไว้ด้วยเผื่อสลับรุ่น
    out = data.get("output_audio") or data.get("outputAudio") or {}
    if out.get("data"):
        return base64.b64decode(out["data"]), _rate_of(out.get("mimeType") or "")

    for cand in (data.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            blob = part.get("inlineData") or part.get("inline_data") or {}
            raw = blob.get("data")
            if not raw:
                continue
            mime = blob.get("mimeType") or blob.get("mime_type") or ""
            return base64.b64decode(raw), _rate_of(mime)
    raise TtsError("Gemini ไม่ได้ส่งไฟล์เสียงกลับมา")


def ensure(text: str, voice: str = "") -> str:
    """มีไฟล์แล้วคืนที่อยู่เลย ยังไม่มีก็สร้างแล้วเก็บก่อน"""
    voice = voice if voice in VOICE_IDS else current_voice()
    path = path_for(text, voice)
    if not exists(path):
        _upload(path, generate(text, voice))
    base = (getattr(config, "SUPABASE_URL", "") or "").rstrip("/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


# ประโยคที่หน้าแบบฝึกหัดใช้ซ้ำทุกข้อ — เตรียมที่อยู่ไฟล์ไว้ให้ตั้งแต่ตอนเปิดหน้า
PHRASES = ["เก่งมาก ตอบถูกค่ะ", "คำตอบที่ถูกคือ", "ยังไม่ถูกนะคะ"]


def phrase_urls(voice: str = "") -> dict[str, str]:
    voice = voice if voice in VOICE_IDS else current_voice()
    return {p: public_url(p, voice) for p in PHRASES}


def status() -> dict:
    """ตรวจสุขภาพ — บอกแค่ว่าพร้อมไหม ห้ามบอกค่ากุญแจเด็ดขาด"""
    return {
        "ready": is_ready(),
        "voice": current_voice(),
        "voices": VOICE_IDS,
        "models": available_models() if is_ready() else [],
    }
