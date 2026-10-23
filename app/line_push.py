"""
ส่งข้อความแจ้งเตือนหาผู้ปกครองผ่าน LINE Messaging API

คนละแช็นเนลกับ LINE Login นะคะ —
    LINE Login    ใช้ยืนยันตัวตนตอนเข้าเว็บ (มีอยู่แล้ว)
    Messaging API ใช้ส่งข้อความเข้าไลน์ผู้ปกครอง (ต้องตั้ง LINE_MESSAGING_TOKEN เพิ่ม)

ส่งได้เฉพาะคนที่กดเพิ่มเพื่อนบัญชีทางการของบ้านครูอ้อยไว้แล้วเท่านั้น
ซึ่งขั้นตอนสมัครสมาชิกบังคับให้เพิ่มเพื่อนอยู่แล้ว จึงครอบคลุมทุกคน
"""

from __future__ import annotations

import httpx

from . import config

API = "https://api.line.me/v2/bot"
MULTICAST_LIMIT = 500        # LINE ให้ส่งได้ครั้งละไม่เกิน 500 คน


class LinePushError(RuntimeError):
    pass


def is_ready() -> bool:
    """ตั้งค่า token ครบหรือยัง"""
    return bool(config.LINE_MESSAGING_TOKEN)


def _headers() -> dict[str, str]:
    if not is_ready():
        raise LinePushError(
            "ยังไม่ได้ตั้งค่า LINE_MESSAGING_TOKEN — "
            "ต้องเปิด Messaging API ให้บัญชีทางการก่อน แล้วนำ Channel access token "
            "ไปใส่ที่ Vercel → Settings → Environment Variables"
        )
    return {
        "Authorization": f"Bearer {config.LINE_MESSAGING_TOKEN}",
        "Content-Type": "application/json",
    }


def multicast(user_ids: list[str], messages: list[dict]) -> int:
    """
    ส่งข้อความเดียวกันหาหลายคน คืนจำนวนคนที่ส่งสำเร็จ

    LINE จะไม่แจ้ง error รายคน ถ้าใครบล็อกบัญชีไว้ก็แค่ไม่ได้รับ
    """
    ids = [u for u in dict.fromkeys(user_ids) if u]      # ตัดซ้ำ ตัดค่าว่าง
    if not ids:
        return 0

    sent = 0
    with httpx.Client(timeout=20) as client:
        for start in range(0, len(ids), MULTICAST_LIMIT):
            batch = ids[start:start + MULTICAST_LIMIT]
            res = client.post(f"{API}/message/multicast", headers=_headers(),
                              json={"to": batch, "messages": messages})
            if res.status_code == 401:
                raise LinePushError("Channel access token ไม่ถูกต้องหรือหมดอายุ กรุณาสร้างใหม่")
            if res.status_code == 403:
                raise LinePushError(
                    "แช็นเนลนี้ยังส่งข้อความไม่ได้ — ตรวจว่าเปิด Messaging API "
                    "และปิด 'Allow bot to join group chats' ไม่เกี่ยว แต่ต้องไม่อยู่ในโหมดจำกัด"
                )
            if res.status_code >= 400:
                raise LinePushError(f"LINE ตอบกลับ {res.status_code}: {res.text[:200]}")
            sent += len(batch)
    return sent


def status(probe: bool = False) -> dict:
    """สถานะระบบแจ้งเตือนผู้ปกครอง — ไม่เคยส่งค่า token ออกมา

    probe=True จะยิงถาม LINE จริงว่า token ยังใช้ได้ไหม
    ใช้เฉพาะคำสั่งอ่านข้อมูล (bot info กับโควตา)
    ไม่ส่งข้อความหาผู้ปกครองสักคนเดียว และไม่เสียโควตา
    """
    info: dict = {
        "ready": is_ready(),
        "oa_id": config.LINE_OA_ID,
        "note": "แช็นเนล Messaging API ใช้เฉพาะ Channel access token "
                "ไม่ได้ใช้ Channel secret",
    }
    if not info["ready"]:
        info["problem"] = ("ยังไม่ได้ตั้ง LINE_MESSAGING_TOKEN ที่ Vercel → "
                           "Settings → Environment Variables")
        return info
    if not probe:
        info["hint"] = "ต่อท้าย ?probe=1 เพื่อให้ตรวจกับ LINE จริง ๆ"
        return info

    try:
        with httpx.Client(timeout=15) as client:
            res = client.get(f"{API}/info", headers=_headers())
    except Exception as exc:                       # ต่อเน็ตไม่ได้
        info["token_valid"] = None
        info["problem"] = f"ติดต่อ LINE ไม่ได้: {type(exc).__name__}"
        return info

    if res.status_code == 401:
        info["token_valid"] = False
        info["problem"] = ("Channel access token ใช้ไม่ได้แล้ว "
                           "ต้องออก token ใหม่ที่ LINE Developers "
                           "แล้วนำไปแก้ที่ Vercel")
        return info
    if res.status_code >= 400:
        info["token_valid"] = False
        info["problem"] = f"LINE ตอบกลับ {res.status_code}"
        return info

    bot = res.json()
    info["token_valid"] = True
    info["bot_name"] = bot.get("displayName")
    info["basic_id"] = bot.get("basicId")
    info["chat_mode"] = bot.get("chatMode")
    left = quota_left()
    info["quota_left"] = left
    info["quota_note"] = ("แพ็กเกจไม่จำกัด หรือดูโควตาไม่ได้"
                          if left is None else "ข้อความฟรีที่เหลือเดือนนี้")
    return info


def quota_left() -> int | None:
    """ข้อความฟรีที่เหลือของเดือนนี้ — คืน None ถ้าดูไม่ได้"""
    if not is_ready():
        return None
    try:
        with httpx.Client(timeout=15) as client:
            quota = client.get(f"{API}/message/quota", headers=_headers()).json()
            used = client.get(f"{API}/message/quota/consumption",
                              headers=_headers()).json()
        if quota.get("type") == "none":      # แพ็กเกจไม่จำกัด
            return None
        return int(quota.get("value", 0)) - int(used.get("totalUsage", 0))
    except Exception:
        return None


# ────────────────────────────────────────────────
#  ข้อความสำเร็จรูป
# ────────────────────────────────────────────────

def new_quiz_message(quiz: dict, question_count: int) -> list[dict]:
    """ข้อความแจ้งว่ามีแบบฝึกหัดใหม่ — เขียนให้ผู้ปกครองอ่านแล้วรู้เรื่องทันที"""
    level = (quiz.get("level") or "").strip() or "ทุกระดับชั้น"
    subject = (quiz.get("subject") or "").strip()

    lines = [
        "📚 มีแบบฝึกหัดใหม่จากบ้านครูอ้อยค่ะ",
        "",
        f"ชุด: {quiz.get('title', '')}",
    ]
    if subject:
        lines.append(f"วิชา: {subject}")
    lines.append(f"ระดับชั้น: {level}")
    lines.append(f"จำนวน: {question_count} ข้อ")
    if quiz.get("description"):
        lines.append(f"\n{quiz['description']}")
    lines += [
        "",
        "เปิดให้น้องทำได้เลย ทำซ้ำได้ไม่จำกัดรอบนะคะ",
        f"{config.SITE_URL}/portal",
    ]

    return [{"type": "text", "text": "\n".join(lines)}]
