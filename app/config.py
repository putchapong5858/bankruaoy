"""ค่าตั้งต้นทั้งหมดของเว็บบ้านครูอ้อย — อ่านจาก environment variables"""

import os

# ─── เว็บ ───
SITE_NAME = "เรียนพิเศษบ้านครูอ้อย"
SITE_URL = os.environ.get("SITE_URL", "https://bankruaoy.com").rstrip("/")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

# ─── LINE Login ───
LINE_CHANNEL_ID = os.environ.get("LINE_CHANNEL_ID", "2011431904")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_REDIRECT_PATH = "/auth/line/callback"

# ─── LINE Official Account (ให้ผู้ปกครองเพิ่มเพื่อน) ───
LINE_OA_ID = os.environ.get("LINE_OA_ID", "@178bogmt")   # บัญชีทางการบ้านครูอ้อย

# ─── LINE Messaging API (ใช้ส่งแจ้งเตือนหาผู้ปกครอง) ───
# เอา Channel access token (long-lived) จาก LINE Developers → แช็นเนล Messaging API
# ถ้ายังไม่ได้ตั้ง ปุ่มแจ้งเตือนจะบอกวิธีตั้งค่าแทนการส่ง
LINE_MESSAGING_TOKEN = os.environ.get("LINE_MESSAGING_TOKEN", "")

# ─── Supabase ───
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ncpretfileknkhpfvfif.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ─── หน้าแอดมินของครูอ้อย ───
ADMIN_LINE_IDS = [
    x.strip() for x in os.environ.get("ADMIN_LINE_IDS", "").split(",") if x.strip()
]

# ─── ข้อมูลสถาบัน (ใช้ทั่วทั้งเว็บ) ───
INSTITUTE = {
    "name": "เรียนพิเศษบ้านครูอ้อย",
    "teacher": "ครูอ้อย · มัลลิกา ปัญญาวชิรพงษ์",
    "teacher_credential": "ปริญญาตรี ครุศาสตร์ · ประสบการณ์สอน 32 ปี",
    "phone": "081-873-4996",
    "phone_raw": "0818734996",
    "line_id": "kruaoymallika",
    "facebook": "https://www.facebook.com/100082980602399",
    "address": "77/7 ถนนวิริโยธิน ต.ลำภู อ.เมือง จ.หนองบัวลำภู 39000",
    "hours_weekday": "จันทร์ – ศุกร์ 15.00 – 20.00 น.",
    "hours_weekend": "เสาร์ – อาทิตย์ 09.00 – 17.00 น.",
    "price_hour": "150 บาท / ชั่วโมง",
    "price_course": "คอร์สเหมาจ่าย 24 ชั่วโมง 2,200 บาท",
}

LEVELS = ["อนุบาล 2", "อนุบาล 3", "ป.1", "ป.2", "ป.3", "ป.4", "ป.5", "ป.6"]

PAYMENT_STATUSES = ["รอชำระ", "ชำระบางส่วน", "จ่ายครบแล้ว"]
ATTENDANCE_STATUSES = ["มาเรียน", "สาย", "ลา", "ขาด"]


def missing_config() -> list[str]:
    """คืนรายชื่อค่าที่ยังไม่ได้ตั้ง เพื่อแสดงเตือนตอน deploy"""
    required = {
        "LINE_CHANNEL_ID": LINE_CHANNEL_ID,
        "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    }
    return [k for k, v in required.items() if not v]
