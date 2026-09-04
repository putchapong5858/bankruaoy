# เว็บไซต์เรียนพิเศษบ้านครูอ้อย

เว็บไซต์ + ระบบสมาชิกผู้ปกครอง ของ **เรียนพิเศษบ้านครูอ้อย** จ.หนองบัวลำภู
เว็บจริง: https://bankruaoy.com

## เทคโนโลยีที่ใช้

| ส่วน | ใช้อะไร |
|---|---|
| ภาษา | Python 3.12 (FastAPI + Jinja2) |
| ฐานข้อมูล | Supabase (PostgreSQL) |
| ยืนยันตัวตน | LINE Login (OAuth 2.0 ฝั่งเซิร์ฟเวอร์) |
| โฮสต์ | Vercel — push ขึ้น GitHub แล้วเว็บอัปเดตอัตโนมัติ |

## โครงสร้างไฟล์

```
api/index.py          จุดเริ่มต้นสำหรับ Vercel
app/config.py         ค่าตั้งต้นทั้งหมด อ่านจาก environment variables
app/db.py             คุยกับ Supabase
app/line_auth.py      LINE Login
app/main.py           เส้นทาง (routes) ทั้งหมดของเว็บ
templates/            หน้าเว็บ (Jinja2)
static/               รูปภาพและ CSS
```

## หน้าเว็บ

| URL | คืออะไร |
|---|---|
| `/` | หน้าแรก |
| `/register` | สมัครสมาชิก (เพิ่มเพื่อน LINE → ยืนยันตัวตน → กรอกข้อมูล) |
| `/login` | เข้าสู่ระบบด้วย LINE |
| `/portal` | ข้อมูลการเรียนของลูก (เลือกดูได้ทีละคน) |
| `/healthz` | ตรวจสุขภาพระบบ + บอกว่าตั้งค่าอะไรยังไม่ครบ |

## ตั้งค่า environment variables

ดูรายการทั้งหมดในไฟล์ `.env.example`
ใส่ค่าจริงที่ **Vercel → Settings → Environment Variables** (ห้าม commit ค่าจริงลง git)

## วิธีอัปเว็บ

ดับเบิลคลิก `push.bat` — หรือสั่งเอง:

```bash
git add -A
git commit -m "update"
git push
```

Vercel จะ build และอัปเดตเว็บให้เองภายใน 1–2 นาที
