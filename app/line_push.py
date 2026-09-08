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
