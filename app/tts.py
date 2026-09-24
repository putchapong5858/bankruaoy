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

# Google ย้ายการสร้างเสียงไปที่ปลายทางใหม่ /v1beta/interactions แล้ว
# รุ่นเดิม (2.5 preview) ใช้ :generateContent ซึ่งยังเผื่อไว้ให้ลองต่อ
# เรียงจากที่ควรใช้ที่สุด — ตัวไหนใช้ได้จริงระบบจะจำไว้แล้วเรียกตัวนั้นก่อนในครั้งถัดไป
INTERACTIONS_URL = f"{API_ROOT}/interactions"

NEW, OLD = "interactions", "generateContent"

MODEL_CANDIDATES = [
    ("gemini-3.8-flash-tts", NEW),          # รุ่นจริง (GA) รองรับภาษาไทย
    ("gemini-2.5-flash-preview-tts", OLD),  # ของเดิม เผื่อบัญชียังเรียกได้
    ("gemini-2.5-pro-preview-tts", OLD),
    ("gemini-3.8-flash-lite-tts", NEW),     # ถูกกว่า แต่เอกสารยังไม่ระบุว่ารองรับไทย
]
MAX_TRIES = 6           # กันไม่ให้ไล่ลองจนเปลืองโควตาและเกินเวลาของ Vercel

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


class QuotaError(TtsError):
    """ใช้เกินโควตาของ Gemini — ต่างจากข้อผิดพลาดอื่นตรงที่ "รอแล้วลองใหม่ได้" """

    def __init__(self, message: str, retry_after: float = 30.0):
        super().__init__(message)
        self.retry_after = max(1.0, float(retry_after))


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
    # ปลายทางแบบใหม่ส่งไฟล์ WAV ที่มีหัว RIFF มาครบแล้ว หุ้มซ้ำจะทำให้ไฟล์เสีย
    if pcm[:4] == b"RIFF":
        return pcm
    ch, bits = 1, 16
    block = ch * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, ch, rate, rate * block, block, bits)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


# จำไว้ว่ารุ่นไหน + วิธีเรียกแบบไหนใช้ได้จริง จะได้ไม่ต้องไล่ลองใหม่ทุกครั้ง
# (แต่ละครั้งที่ลองผิดคือเสียเวลาและกินโควตาเปล่า ๆ)
_working: tuple[str, str] | None = None


def _headers() -> dict[str, str]:
    return {"x-goog-api-key": getattr(config, "GEMINI_API_KEY", ""),
            "Content-Type": "application/json"}


def _plan() -> list[tuple[str, str]]:
    """ลำดับที่จะลอง — ตัวที่เพิ่งใช้ได้ขึ้นก่อน ตามด้วยรุ่นที่ครูล็อกไว้เอง"""
    out: list[tuple[str, str]] = []
    if _working:
        out.append(_working)
    picked = (getattr(config, "GEMINI_TTS_MODEL", "") or "").strip()
    if picked:
        # ครูล็อกรุ่นไว้เอง — ลองทั้งสองวิธีเรียก เพราะไม่รู้ว่ารุ่นนั้นใช้แบบไหน
        style = OLD if "preview-tts" in picked else NEW
        out += [(picked, style), (picked, OLD if style == NEW else NEW)]
    out += list(MODEL_CANDIDATES)
    seen, uniq = set(), []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def available_models() -> list[str]:
    """ถาม Google ว่ากุญแจนี้ใช้รุ่น TTS ไหนได้บ้าง — ใช้ตอนตรวจสุขภาพระบบ"""
    if not getattr(config, "GEMINI_API_KEY", ""):
        return []
    try:
        res = _conn().get(f"{API_ROOT}/models", headers=_headers(),
                          params={"pageSize": 200}, timeout=20.0)
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


def _call_new(model: str, said: str, voice: str):
    """ปลายทางปัจจุบันของ Google — POST /v1beta/interactions"""
    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [{
            "type": "text",
            "text": said,
            "annotations": [{"type": "speech_metadata", "style": STYLE}],
        }]}],
        "response_format": {"type": "audio", "mime_type": "audio/wav",
                            "sample_rate": SAMPLE_RATE},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    return _conn().post(INTERACTIONS_URL, headers=_headers(), json=body, timeout=60.0)


def _call_old(model: str, said: str, voice: str):
    """ปลายทางแบบเดิม — POST /v1beta/models/<รุ่น>:generateContent"""
    body = {
        "contents": [{"parts": [{"text": f"{STYLE}:\n{said}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    return _conn().post(f"{API_ROOT}/models/{model}:generateContent",
                        headers=_headers(), json=body, timeout=60.0)


def _err_msg(res) -> str:
    """ข้อความสั้น ๆ จากคำตอบที่ผิดพลาด ใช้บอกครูว่าติดตรงไหนจริง ๆ"""
    try:
        msg = ((res.json().get("error") or {}).get("message") or "").strip()
        if msg:
            return msg[:180]
    except (ValueError, AttributeError):
        pass
    return (res.text or "")[:180]


def _retry_after(res) -> float:
    """Google บอกมาว่าให้รอกี่วินาที — อ่านทั้งจากหัวข้อความและในตัวคำตอบ"""
    head = res.headers.get("retry-after") or ""
    if head.strip().isdigit():
        return min(float(head.strip()), 120.0)
    try:
        for d in ((res.json().get("error") or {}).get("details") or []):
            delay = str(d.get("retryDelay") or "")
            if delay.endswith("s"):
                return min(float(delay[:-1] or 0), 120.0)
    except (ValueError, TypeError, AttributeError):
        pass
    return 0.0


def generate(text: str, voice: str = "") -> bytes:
    """เรียก Gemini ให้อ่านข้อความ แล้วคืนไฟล์ WAV"""
    global _working
    if not getattr(config, "GEMINI_API_KEY", ""):
        raise TtsError("ยังไม่ได้ตั้งค่า GEMINI_API_KEY ที่ Vercel")

    said = clean(text)
    if not said:
        raise TtsError("ไม่มีข้อความให้อ่าน")
    voice = voice if voice in VOICE_IDS else current_voice()

    plan = _plan()
    last = ""
    tries = 0
    slept = 0.0
    asked_google = False
    i = 0

    while i < len(plan) and tries < MAX_TRIES:
        model, style = plan[i]
        i += 1
        tries += 1
        try:
            res = (_call_new if style == NEW else _call_old)(model, said, voice)
        except httpx.HTTPError as exc:
            last = f"ต่อกับ Gemini ไม่ได้ ({str(exc)[:100]})"
            continue

        if res.status_code == 429:
            wait = _retry_after(res)
            # รอสั้น ๆ แล้วลองรุ่นเดิมซ้ำได้ครั้งเดียว — Vercel มีเวลาจำกัดต่อคำขอ
            if slept < 5.0 and wait <= 5.0:
                pause = min(max(wait, 1.5), 4.0)
                time.sleep(pause)
                slept += pause
                i -= 1
                tries -= 1 if tries > 0 else 0
                continue
            raise QuotaError(
                "ใช้เกินโควตาของ Gemini ในช่วงนี้"
                + (f" — Google บอกให้รออีกราว {int(wait)} วินาที" if wait
                   else " รอสักครู่แล้วลองใหม่"),
                retry_after=wait or 30.0)

        if res.status_code in (401, 403):
            raise TtsError("กุญแจ Gemini ไม่ถูกต้องหรือยังไม่เปิดสิทธิ์ใช้เสียง "
                           f"({res.status_code}: {_err_msg(res)})")

        if res.status_code in (400, 404):
            # รุ่นนี้ไม่มี หรือเรียกผิดแบบ — ลองตัวถัดไป
            last = f"รุ่น {model} แบบ {style} ใช้ไม่ได้ ({res.status_code}: {_err_msg(res)})"
            if i >= len(plan) and not asked_google:
                asked_google = True
                known = {m for m, _ in plan}
                for name in available_models():
                    if name not in known:
                        plan += [(name, NEW), (name, OLD)]
            continue

        if res.status_code >= 400:
            last = f"Gemini ตอบ {res.status_code}: {_err_msg(res)}"
            continue

        try:
            payload = res.json()
        except ValueError:
            last = f"รุ่น {model} ตอบกลับมาไม่ใช่ JSON"
            continue

        try:
            audio, rate = _read_audio(payload, model, style)
        except TtsError as exc:
            last = str(exc)
            continue

        _working = (model, style)
        return _wav(audio, rate)

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


def _audio_blob(node) -> dict:
    if isinstance(node, dict):
        return node.get("output_audio") or node.get("outputAudio") or {}
    return {}


def _no_audio_reason(data: dict, model: str, style: str) -> str:
    """บอกให้ชัดว่าทำไมไม่มีเสียงกลับมา ไม่ใช่แค่ "ไม่ได้ส่งไฟล์เสียงกลับมา" """
    bits = []
    fb = data.get("promptFeedback") or data.get("prompt_feedback") or {}
    if fb.get("blockReason") or fb.get("block_reason"):
        bits.append("ถูกบล็อก: %s" % (fb.get("blockReason") or fb.get("block_reason")))
    for cand in (data.get("candidates") or []):
        fin = cand.get("finishReason") or cand.get("finish_reason")
        if fin:
            bits.append(f"finishReason={fin}")
        for part in ((cand.get("content") or {}).get("parts") or []):
            if part.get("text"):
                bits.append("ตอบกลับเป็นข้อความ: " + part["text"].strip()[:90])
    if data.get("error"):
        bits.append(str((data.get("error") or {}).get("message") or "")[:120])
    if not bits:
        keys = ", ".join(sorted(k for k in data if not k.startswith("_"))[:6]) or "ว่างเปล่า"
        bits.append(f"ไม่พบช่องเสียงในคำตอบ (คีย์ที่ได้มา: {keys})")
    return f"รุ่น {model} แบบ {style} ไม่ได้ส่งไฟล์เสียงกลับมา — " + " · ".join(bits)


def _read_audio(data: dict, model: str = "", style: str = "") -> tuple[bytes, int]:
    # ปลายทางแบบใหม่ — เสียงอยู่ที่ output_audio (บางทีห่ออีกชั้นใน interaction)
    for node in (data, data.get("interaction"), data.get("response"),
                 data.get("output")):
        blob = _audio_blob(node)
        if blob.get("data"):
            mime = blob.get("mimeType") or blob.get("mime_type") or ""
            return base64.b64decode(blob["data"]), _rate_of(mime)

    # ปลายทางแบบเดิม — เสียงอยู่ใน candidates[].content.parts[].inlineData
    for cand in (data.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            blob = part.get("inlineData") or part.get("inline_data") or {}
            raw = blob.get("data")
            if not raw:
                continue
            mime = blob.get("mimeType") or blob.get("mime_type") or ""
            return base64.b64decode(raw), _rate_of(mime)

    raise TtsError(_no_audio_reason(data, model, style))


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


def status(probe: bool = False) -> dict:
    """ตรวจสุขภาพ — บอกแค่ว่าพร้อมไหม ห้ามบอกค่ากุญแจเด็ดขาด

    probe=True จะลองสร้างเสียงสั้น ๆ 1 ครั้งจริง ๆ แล้วรายงานว่าติดตรงไหน
    ใช้ตอนเสียงพังแล้วอยากรู้สาเหตุที่แท้จริง (เปลืองโควตา 1 ครั้งเท่านั้น)
    """
    out = {
        "ready": is_ready(),
        "voice": current_voice(),
        "voices": VOICE_IDS,
        "models": available_models() if is_ready() else [],
        "tried": [f"{m} ({st})" for m, st in MODEL_CANDIDATES],
        "working": f"{_working[0]} ({_working[1]})" if _working else None,
    }
    if not probe:
        return out
    if not is_ready():
        out["probe"] = {"ok": False, "error": "ยังไม่ได้ตั้งค่า GEMINI_API_KEY"}
        return out
    try:
        data = generate("ทดสอบเสียง")
        out["probe"] = {"ok": True, "bytes": len(data),
                        "wav": data[:4] == b"RIFF",
                        "model": f"{_working[0]} ({_working[1]})" if _working else "?"}
    except QuotaError as exc:
        out["probe"] = {"ok": False, "quota": True,
                        "retry_after": exc.retry_after, "error": str(exc)}
    except TtsError as exc:
        out["probe"] = {"ok": False, "error": str(exc)}
    return out
