"""
LINE Login (OAuth 2.0 / OpenID Connect) ฝั่งเซิร์ฟเวอร์
เอกสาร: https://developers.line.biz/en/docs/line-login/integrate-line-login/

ทำแบบ server-side เพราะปลอดภัยกว่า LIFF —
channel secret อยู่บนเซิร์ฟเวอร์เท่านั้น ไม่หลุดไปเบราว์เซอร์
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from . import config

AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
PROFILE_URL = "https://api.line.me/v2/profile"


class LineError(RuntimeError):
    pass


def redirect_uri() -> str:
    return config.SITE_URL + config.LINE_REDIRECT_PATH


def make_state() -> str:
    return secrets.token_urlsafe(24)


def login_url(state: str, add_friend: bool = True) -> str:
    """
    สร้างลิงก์พาไปหน้าล็อกอินของ LINE

    add_friend=True จะแสดงปุ่ม "เพิ่มเพื่อน" ของ LINE OA ให้ในตัว
    (ใช้ได้เมื่อผูก Linked LINE Official Account ไว้แล้ว)
    """
    if not config.LINE_CHANNEL_ID:
        raise LineError("ยังไม่ได้ตั้งค่า LINE_CHANNEL_ID")

    params = {
        "response_type": "code",
        "client_id": config.LINE_CHANNEL_ID,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": "profile openid",
    }
    if add_friend:
        params["bot_prompt"] = "aggressive"
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """แลก authorization code เป็นข้อมูลผู้ใช้"""
    if not config.LINE_CHANNEL_SECRET:
        raise LineError("ยังไม่ได้ตั้งค่า LINE_CHANNEL_SECRET")

    with httpx.Client(timeout=15) as client:
        res = client.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": config.LINE_CHANNEL_ID,
            "client_secret": config.LINE_CHANNEL_SECRET,
        })
        if res.status_code != 200:
            raise LineError(f"แลก token ไม่สำเร็จ: {res.text[:200]}")
        token = res.json()

        access_token = token.get("access_token")
        if not access_token:
            raise LineError("LINE ไม่ได้ส่ง access_token กลับมา")

        prof = client.get(PROFILE_URL,
                          headers={"Authorization": f"Bearer {access_token}"})
        if prof.status_code != 200:
            raise LineError(f"ดึงโปรไฟล์ไม่สำเร็จ: {prof.text[:200]}")
        p = prof.json()

    return {
        "user_id": p.get("userId", ""),
        "display_name": p.get("displayName", ""),
        "picture_url": p.get("pictureUrl", "") or "",
        "friend_flag": token.get("friendship_status_changed"),
    }


def oa_add_url() -> str:
    """ลิงก์เพิ่มเพื่อน LINE OA"""
    oa = (config.LINE_OA_ID or "").lstrip("@")
    return f"https://line.me/R/ti/p/@{oa}" if oa else "#"


def oa_qr_data_uri() -> str:
    """
    สร้าง QR เพิ่มเพื่อนเป็น SVG data URI ในตัวเอง
    (ไม่พึ่งบริการ QR ภายนอก จะได้ไม่ล่มตามคนอื่น และไม่รั่วข้อมูลผู้ใช้)
    """
    oa = (config.LINE_OA_ID or "").lstrip("@")
    if not oa:
        return ""
    import base64
    import io

    import segno

    buf = io.BytesIO()
    segno.make(f"https://line.me/R/ti/p/@{oa}", error="m").save(
        buf, kind="svg", scale=5, border=2, dark="#0E3B57", light="#ffffff",
        xmldecl=False, svgns=True
    )
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
