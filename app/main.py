"""
เว็บไซต์เรียนพิเศษบ้านครูอ้อย — https://bankruaoy.com
FastAPI + Jinja2 + Supabase + LINE Login
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import (config, content, db, gemini, line_auth, line_push, quiz,
               quiz_import)

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Baan Kru Aoy", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="bka_session",
    https_only=False,
    max_age=60 * 60 * 24 * 30,      # จำการล็อกอินไว้ 30 วัน
    same_site="lax",
)
# บนเว็บจริง /static ถูก CDN ของ Vercel แจกไปก่อนถึงตรงนี้แล้ว (ดู vercel.json)
# ตัวนี้เหลือไว้ให้รันทดสอบในเครื่อง — check_dir=False กันพังถ้าไม่มีโฟลเดอร์ติดไปด้วย
app.mount("/static",
          StaticFiles(directory=BASE_DIR / "static", check_dir=False),
          name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals.update(
    site=config.INSTITUTE,
    site_url=config.SITE_URL,
    levels=config.LEVELS,
    # เนื้อหาเว็บทั้งหมดจาก content.py — ทุกหน้าเรียกใช้ได้เลย
    c=content,
    bot=content.BOT,
    bot_qa=content.BOT_QA,
)


def home_context() -> dict:
    """เนื้อหาหน้าแรกทั้งหมด — ดึงจาก app/content.py ไม่มีข้อความไหนเขียนตายตัวใน HTML"""
    return {
        "nav":            content.NAV,
        "hero":           content.HERO,
        "exam":           content.EXAM,
        "features_head":  content.FEATURES_HEAD,
        "features":       content.FEATURES,
        "about":          content.ABOUT,
        "subjects_head":  content.SUBJECTS_HEAD,
        "subjects":       content.SUBJECTS,
        "subjects_more":  content.SUBJECTS_MORE,
        "levels_head":    content.LEVELS_HEAD,
        "level_groups":   content.LEVEL_GROUPS,
        "gallery_head":   content.GALLERY_HEAD,
        "gallery":        content.GALLERY,
        "course_head":    content.COURSE_HEAD,
        "prices":         content.PRICES,
        "schedule_head":  content.SCHEDULE_HEAD,
        "schedule_rows":  content.SCHEDULE_ROWS,
        "schedule_note":  content.SCHEDULE_NOTE,
        "faq_head":       content.FAQ_HEAD,
        "faq":            content.FAQ,
        "contact_head":   content.CONTACT_HEAD,
        "contact_info":   content.CONTACT_INFO,
        "contact_card":   content.CONTACT_CARD,
        "cta":            content.CTA,
        "footer_about":   content.FOOTER_ABOUT,
        "footer_links":   content.FOOTER_LINKS,
        "footer_subjects": content.FOOTER_SUBJECTS,
        "footer_contact": content.FOOTER_CONTACT,
        "footer_copyright": content.FOOTER_COPYRIGHT,
    }


# ────────────────────────────────────────────────
#  ตัวช่วย
# ────────────────────────────────────────────────

def page(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx)


def current_line_user(request: Request) -> dict | None:
    u = request.session.get("line_user")
    return u if u and u.get("user_id") else None


def clean_phone(raw: str) -> str:
    return re.sub(r"[^0-9]", "", raw or "")


def enrolled_flag(request: Request) -> str:
    return request.query_params.get("enrolled", "")


def is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("user_id") in config.ADMIN_LINE_IDS


def destination_for(request: Request, user: dict) -> str:
    """ปุ่ม 'เข้าสู่ระบบ' ปุ่มเดียว — ระบบเลือกหน้าปลายทางให้เอง

    ครูอ้อย (LINE ID ที่ตั้งค่าไว้ใน ADMIN_LINE_IDS) → หน้าจัดการ
    ผู้ปกครองที่สมัครแล้ว → หน้าข้อมูลลูก
    คนที่ยังไม่เคยสมัคร → หน้ากรอกใบสมัคร
    """
    if is_admin(user):
        return "/admin"
    try:
        if db.get_parent_by_line(user["user_id"]):
            return "/portal"
    except Exception:
        return request.session.pop("after_login", "/portal")
    request.session.pop("after_login", None)
    return "/register/form"


# ────────────────────────────────────────────────
#  หน้าเว็บสาธารณะ
# ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return page(request, "index.html", **home_context())


@app.get("/healthz")
def healthz():
    return JSONResponse({
        "ok": True,
        "database": db.health(),
        "missing_config": config.missing_config(),
    })


@app.get("/healthz/ai")
def healthz_ai():
    """
    สถานะของผู้ช่วย AI — เปิดดูได้โดยไม่ต้องล็อกอิน เพื่อให้ตรวจปัญหาได้เร็ว

    บอกแค่ว่า "ตั้งกุญแจแล้วหรือยัง" และ "บัญชีมีรุ่นไหนให้ใช้"
    ไม่เคยส่งค่ากุญแจออกมา และไม่ได้สั่งให้ AI สร้างข้อความ จึงไม่มีค่าใช้จ่าย
    """
    return JSONResponse(gemini.status())


@app.get("/ping")
def ping():
    """
    ปลุกเครื่องให้ตื่นไว้ — เบาที่สุด ไม่แตะฐานข้อมูล ไม่เรนเดอร์หน้า

    Vercel แพ็กเกจฟรีจะพักเครื่องเมื่อไม่มีคนเข้าสักพัก คนถัดไปที่เข้า
    จึงต้องรอปลุกเครื่องราว 1 วินาที (cold start)
    ให้บริการ ping ภายนอกยิงมาที่นี่ทุก 5 นาที เครื่องจะตื่นอยู่ตลอด
    """
    return JSONResponse({"ok": True})


# ────────────────────────────────────────────────
#  สมัครสมาชิก
# ────────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse)
def register(request: Request):
    """ขั้นที่ 1 — เพิ่มเพื่อน LINE"""
    if current_line_user(request):
        return RedirectResponse("/register/form", status_code=303)
    return page(
        request, "register.html",
        step=1,
        oa_id=config.LINE_OA_ID,
        oa_add_url=line_auth.oa_add_url(),
        oa_qr_url=line_auth.oa_qr_data_uri(),
    )


@app.get("/register/login")
def register_login(request: Request):
    """ขั้นที่ 2 — ส่งไปหน้าล็อกอินของ LINE"""
    state = line_auth.make_state()
    request.session["oauth_state"] = state
    request.session["after_login"] = "/register/form"
    try:
        return RedirectResponse(line_auth.login_url(state), status_code=303)
    except line_auth.LineError as exc:
        return page(request, "error.html", message=str(exc))


@app.get("/auth/line/callback")
def line_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return page(request, "error.html",
                    message="คุณยกเลิกการเข้าสู่ระบบ หรือ LINE ปฏิเสธคำขอ")
    if not code or state != request.session.get("oauth_state"):
        return page(request, "error.html",
                    message="ลิงก์เข้าสู่ระบบไม่ถูกต้องหรือหมดอายุ กรุณาลองใหม่อีกครั้ง")

    try:
        user = line_auth.exchange_code(code)
    except line_auth.LineError as exc:
        return page(request, "error.html", message=str(exc))

    request.session.pop("oauth_state", None)
    request.session["line_user"] = user

    return RedirectResponse(destination_for(request, user), status_code=303)


@app.get("/register/form", response_class=HTMLResponse)
def register_form(request: Request):
    """ขั้นที่ 3 — กรอกข้อมูล"""
    user = current_line_user(request)
    if not user:
        return RedirectResponse("/register", status_code=303)

    parent = db.get_parent_by_line(user["user_id"])
    if parent:
        return RedirectResponse("/portal", status_code=303)

    return page(
        request, "register.html",
        step=3,
        line_name=user["display_name"],
        line_picture=user["picture_url"],
        error=None,
    )


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    full_name: str = Form(""),
    phone: str = Form(""),
    nickname: list[str] = Form([]),
    level: list[str] = Form([]),
):
    user = current_line_user(request)
    if not user:
        return RedirectResponse("/register", status_code=303)

    full_name = (full_name or "").strip()[:60]
    phone = clean_phone(phone)
    children = [
        {"nickname": n.strip()[:30], "level": lv.strip()}
        for n, lv in zip(nickname, level)
        if n.strip() and lv.strip()
    ]

    error = None
    if not full_name:
        error = "กรุณากรอกชื่อผู้ปกครอง"
    elif not re.fullmatch(r"0\d{8,9}", phone):
        error = "เบอร์โทรไม่ถูกต้อง กรุณากรอกให้ครบ เช่น 0812345678"
    elif not children:
        error = "กรุณากรอกชื่อเล่นและระดับชั้นของลูกอย่างน้อย 1 คน"

    if error:
        return page(request, "register.html", step=3, error=error,
                    line_name=user["display_name"], line_picture=user["picture_url"])

    try:
        result = db.create_parent_with_children(
            line_user_id=user["user_id"],
            line_name=user["display_name"],
            picture_url=user["picture_url"],
            full_name=full_name,
            phone=phone,
            children=children,
        )
    except Exception as exc:
        return page(request, "register.html", step=3,
                    error="บันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่ (" + str(exc)[:120] + ")",
                    line_name=user["display_name"], line_picture=user["picture_url"])

    return page(request, "register.html", step=4,
                parent=result["parent"], students=result["students"])


# ────────────────────────────────────────────────
#  พอร์ทัลผู้ปกครอง
# ────────────────────────────────────────────────

@app.get("/portal", response_class=HTMLResponse)
def portal(request: Request, child: int = 0):
    user = current_line_user(request)
    if not user:
        return page(request, "login.html")

    try:
        parent = db.get_parent_by_line(user["user_id"])
    except Exception as exc:
        return page(request, "error.html",
                    message="เชื่อมต่อฐานข้อมูลไม่สำเร็จ (" + str(exc)[:120] + ")")

    if not parent:
        return RedirectResponse("/register/form", status_code=303)

    children = db.get_children(parent["id"])

    if parent["status"] != "active":
        return page(request, "waiting.html",
                    parent=parent, students=children, user=user)

    if not children:
        return page(request, "waiting.html",
                    parent=parent, students=[], user=user,
                    note="ยังไม่มีข้อมูลนักเรียน กรุณาติดต่อครูอ้อย")

    index = max(0, min(child, len(children) - 1))
    student = children[index]
    enrolled = enrolled_flag(request)

    # ยิงทุก query พร้อมกัน ไม่ต้องรอทีละอัน — ฐานข้อมูลอยู่คนละที่กับเซิร์ฟเวอร์
    got = db.gather(
        detail=lambda: db.get_student_detail(student),
        schedule=db.get_schedule,
        news=db.get_announcements,
        courses=db.list_courses,
        enrollments=lambda: db.get_enrollments(student["id"]),
        quizzes=lambda: quiz.quizzes_for_student(student),
        quiz_history=lambda: quiz.attempt_history(student["id"], limit=8),
    )

    return page(
        request, "portal.html",
        user=user, parent=parent,
        children=children, index=index, s=got["detail"],
        schedule=got["schedule"],
        news=got["news"],
        courses=got["courses"],
        enrollments=got["enrollments"],
        enrolled=enrolled,
        quizzes=got["quizzes"],
        quiz_history=got["quiz_history"],
        quizerr=request.query_params.get("quizerr", ""),
    )


@app.post("/portal/enroll")
def portal_enroll(
    request: Request,
    student_id: str = Form(...),
    course_id: str = Form(...),
    hours: str = Form("1"),
    child: int = Form(0),
):
    """ผู้ปกครองเลือกคอร์สให้ลูก — ส่งเป็นคำขอ รอครูอ้อยยืนยัน"""
    user = current_line_user(request)
    if not user:
        return RedirectResponse("/portal", status_code=303)

    parent = db.get_parent_by_line(user["user_id"])
    if not parent or parent.get("status") != "active":
        return RedirectResponse("/portal", status_code=303)

    # กันไม่ให้เลือกคอร์สให้ลูกคนอื่นที่ไม่ใช่ของตัวเอง
    mine = {c["id"] for c in db.get_children(parent["id"])}
    if student_id not in mine:
        return RedirectResponse("/portal", status_code=303)

    try:
        db.request_enrollment(student_id, course_id, float(hours or 1))
        flag = "sent"
    except Exception as exc:
        flag = "dup" if "รอครูอ้อยยืนยัน" in str(exc) else "err"

    return RedirectResponse(f"/portal?child={child}&enrolled={flag}", status_code=303)


@app.get("/login")
def login(request: Request):
    # ล็อกอินค้างไว้อยู่แล้ว — พาไปหน้าที่ถูกต้องเลย ไม่ต้องผ่าน LINE ซ้ำ
    user = current_line_user(request)
    if user:
        return RedirectResponse(destination_for(request, user), status_code=303)

    state = line_auth.make_state()
    request.session["oauth_state"] = state
    request.session["after_login"] = "/portal"
    try:
        return RedirectResponse(line_auth.login_url(state, add_friend=False),
                                status_code=303)
    except line_auth.LineError as exc:
        return page(request, "error.html", message=str(exc))


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ────────────────────────────────────────────────
#  หน้าจัดการของครูอ้อย
# ────────────────────────────────────────────────

def require_admin(request: Request):
    """คืน (user, response) — ถ้า response ไม่ใช่ None ให้ส่งกลับทันที"""
    user = current_line_user(request)
    if not user:
        return None, page(request, "login.html")
    if user["user_id"] not in config.ADMIN_LINE_IDS:
        return None, page(request, "admin_denied.html", user=user)
    return user, None


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, saved: str = "", err: str = ""):
    user, blocked = require_admin(request)
    if blocked:
        return blocked

    # หน้าแอดมินดึงข้อมูลสิบกว่าชุด — ยิงพร้อมกันแทนการรอทีละชุด
    got = db.gather(
        students=db.list_students,
        all_students=lambda: db.list_students(active_only=False),
        parent_options=db.list_parents_simple,
        pending=lambda: db.list_parents("pending"),
        enroll_requests=db.list_enrollment_requests,
        all_courses=db.list_all_courses,
        sessions=db.list_sessions,
        homeworks=db.list_homework,
        exams=db.list_exams,
        quizzes=quiz.list_quizzes,
        materials=db.list_materials,
        announcements=db.list_announcements,
    )
    return page(
        request, "admin.html",
        user=user,
        pending=got["pending"],
        enroll_requests=got["enroll_requests"],
        all_courses=got["all_courses"],
        sessions=got["sessions"],
        homeworks=got["homeworks"],
        exams=got["exams"],
        quizzes=got["quizzes"],
        materials=got["materials"],
        announcements=got["announcements"],
        students=got["students"],
        # นักเรียนที่ถูกย้ายไป "ไม่ใช้งาน" — แสดงแยกไว้ให้กู้คืนได้
        archived_students=[s for s in got["all_students"] if not s.get("active")],
        parent_options=got["parent_options"],
        levels=config.LEVELS,
        payment_statuses=config.PAYMENT_STATUSES,
        attendance_statuses=config.ATTENDANCE_STATUSES,
        today=date.today().isoformat(),
        saved=saved,
        err=err,
    )


@app.post("/admin/parent/{parent_id}/{action}")
def admin_parent(request: Request, parent_id: str, action: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    if action in ("approve", "reject"):
        db.set_parent_status(parent_id, "active" if action == "approve" else "rejected")
    return RedirectResponse(f"/admin?saved={action}", status_code=303)


@app.post("/admin/enrollment/{enrollment_id}/{action}")
def admin_enrollment(request: Request, enrollment_id: str, action: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    if action == "confirm":
        db.confirm_enrollment(enrollment_id)
    elif action == "cancel":
        db.cancel_enrollment(enrollment_id)
    return RedirectResponse(f"/admin?saved={action}", status_code=303)


@app.post("/admin/course/new")
def admin_course_new(
    request: Request,
    name: str = Form(""),
    code: str = Form(""),
    description: str = Form(""),
    hours: str = Form("0"),
    price: str = Form("0"),
    is_hourly: str = Form(""),
    highlight: str = Form(""),
    sort_order: str = Form("99"),
):
    """ครูอ้อยเพิ่มคอร์สใหม่"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        db.create_course({
            "name": name, "code": code, "description": description,
            "hours": hours, "price": price,
            "is_hourly": bool(is_hourly), "highlight": bool(highlight),
            "active": True, "sort_order": sort_order,
        })
    except Exception as exc:
        return RedirectResponse(f"/admin?err={quote(str(exc)[:200])}#courses",
                                status_code=303)
    return RedirectResponse("/admin?saved=course#courses", status_code=303)


@app.post("/admin/course/{course_id}")
def admin_course_edit(
    request: Request,
    course_id: str,
    name: str = Form(""),
    description: str = Form(""),
    hours: str = Form("0"),
    price: str = Form("0"),
    is_hourly: str = Form(""),
    highlight: str = Form(""),
    active: str = Form(""),
    sort_order: str = Form("99"),
):
    """ครูอ้อยแก้ไขคอร์สที่มีอยู่"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        db.update_course(course_id, {
            "name": name, "description": description,
            "hours": hours, "price": price,
            "is_hourly": bool(is_hourly), "highlight": bool(highlight),
            "active": bool(active), "sort_order": sort_order,
        })
    except Exception as exc:
        return RedirectResponse(f"/admin?err={quote(str(exc)[:200])}#courses",
                                status_code=303)
    return RedirectResponse("/admin?saved=course#courses", status_code=303)


@app.post("/admin/course/{course_id}/delete")
def admin_course_delete(request: Request, course_id: str):
    """ลบคอร์ส — ถ้ามีคนลงเรียนแล้วระบบจะปิดการขายให้แทน"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        db.delete_course(course_id)
    except Exception as exc:
        return RedirectResponse(f"/admin?err={quote(str(exc)[:200])}#courses",
                                status_code=303)
    return RedirectResponse("/admin?saved=deleted#courses", status_code=303)


@app.post("/admin/student/{student_id}")
def admin_student(
    request: Request,
    student_id: str,
    full_name: str = Form(""),
    level: str = Form(""),
    hours_bought: str = Form(""),
    hours_used: str = Form(""),
    payment_status: str = Form(""),
    course_expiry: str = Form(""),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.update_student(student_id, {
        "full_name": full_name.strip(),
        "level": level,
        "hours_bought": hours_bought,
        "hours_used": hours_used,
        "payment_status": payment_status,
        "course_expiry": course_expiry or None,
    })
    return _back("students", "student")


@app.post("/admin/student")
def admin_student_new(
    request: Request,
    parent_id: str = Form(""),
    nickname: str = Form(""),
    full_name: str = Form(""),
    level: str = Form(""),
):
    """เพิ่มนักเรียนใหม่ใต้ผู้ปกครองที่มีอยู่แล้ว"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        db.add_student(parent_id, nickname, level, full_name)
    except db.SupabaseError as exc:
        return _back("students", err=str(exc))
    return _back("students", "student")


@app.post("/admin/student/{student_id}/delete")
def admin_student_delete(request: Request, student_id: str):
    """ลบนักเรียน — ถ้ามีประวัติผูกอยู่จะย้ายไปเป็น 'ไม่ใช้งาน' แทน"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        result = db.remove_student(student_id)
    except db.SupabaseError as exc:
        return _back("students", err=str(exc))
    if result == "archived":
        return _back("students", err="นักเรียนคนนี้มีประวัติเรียนอยู่แล้ว "
                                     "ระบบจึงย้ายไปเป็น “ไม่ใช้งาน” แทนการลบ "
                                     "เพื่อไม่ให้ประวัติหาย")
    return _back("students", "deleted")


@app.post("/admin/student/{student_id}/restore")
def admin_student_restore(request: Request, student_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.restore_student(student_id)
    return _back("students", "student")


@app.post("/admin/announcement")
def admin_announcement(
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    show_until: str = Form(""),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.add_announcement({
        "title": title.strip(), "body": body.strip(),
        "show_until": show_until or None,
    })
    return _back("news", "announcement")


@app.post("/admin/announcement/{announcement_id}/delete")
def admin_announcement_delete(request: Request, announcement_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.delete_announcement(announcement_id)
    return RedirectResponse("/admin?saved=deleted#news", status_code=303)


# ════════════════════════════════════════════════════════
#  1) คาบเรียน + เช็คชื่อ
# ════════════════════════════════════════════════════════

def _back(anchor: str, saved: str = "", err: str = "") -> RedirectResponse:
    """กลับไปหน้าจัดการ ตรงหัวข้อที่เพิ่งทำงานเสร็จ"""
    q = f"err={quote(err[:200])}" if err else f"saved={saved or 'ok'}"
    return RedirectResponse(f"/admin?{q}#{anchor}", status_code=303)


@app.post("/admin/session/new")
def admin_session_new(
    request: Request,
    date_: str = Form("", alias="date"),
    time_range: str = Form(""),
    level: str = Form(""),
    subjects: str = Form(""),
    hours: str = Form("3"),
    note: str = Form(""),
):
    """ครูอ้อยเปิดคาบเรียนใหม่"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        ses = db.save_session({"date": date_, "time_range": time_range, "level": level,
                               "subjects": subjects, "hours": hours, "note": note})
    except Exception as exc:
        return _back("sessions", err=str(exc))
    return RedirectResponse(f"/admin/session/{ses['id']}", status_code=303)


@app.post("/admin/session/{session_id}")
def admin_session_edit(
    request: Request,
    session_id: str,
    date_: str = Form("", alias="date"),
    time_range: str = Form(""),
    level: str = Form(""),
    subjects: str = Form(""),
    hours: str = Form("3"),
    status: str = Form("เปิดเรียน"),
    note: str = Form(""),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        db.save_session({"date": date_, "time_range": time_range, "level": level,
                         "subjects": subjects, "hours": hours,
                         "status": status, "note": note}, session_id)
    except Exception as exc:
        return _back("sessions", err=str(exc))
    return _back("sessions", "session")


@app.post("/admin/session/{session_id}/delete")
def admin_session_delete(request: Request, session_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.delete_session(session_id)
    return _back("sessions", "deleted")


@app.get("/admin/session/{session_id}", response_class=HTMLResponse)
def admin_session_sheet(request: Request, session_id: str, saved: str = ""):
    """หน้าเช็คชื่อของคาบเรียนหนึ่ง"""
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    ses = db.get_session(session_id)
    if not ses:
        return _back("sessions", err="ไม่พบคาบเรียนนี้")

    lv = (ses.get("level") or "").strip()
    students = db.list_students()
    # ถ้าคาบระบุระดับชั้นไว้ ให้โชว์เฉพาะเด็กที่ตรง — แต่ยังเลือกคนอื่นได้จากปุ่มด้านล่าง
    matching = [s for s in students if not lv or (s.get("level") or "") in lv]
    return page(request, "admin_session.html",
                user=user, session=ses,
                students=matching or students,
                others=[s for s in students if s not in (matching or students)],
                marked=db.session_attendance(session_id),
                statuses=config.ATTENDANCE_STATUSES,
                saved=saved)


@app.post("/admin/session/{session_id}/attendance")
async def admin_session_attendance(request: Request, session_id: str):
    """บันทึกเช็คชื่อ — ติ๊กใหม่/เอาออกได้ ชั่วโมงคำนวณใหม่ทุกครั้ง"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    form = await request.form()
    present = form.getlist("student_id")
    statuses = {sid: form.get(f"status_{sid}") or "มาเรียน" for sid in present}
    try:
        db.save_attendance(session_id, present, statuses)
    except Exception as exc:
        return _back("sessions", err=str(exc))
    return RedirectResponse(f"/admin/session/{session_id}?saved=1", status_code=303)


# ════════════════════════════════════════════════════════
#  2) การบ้าน + ตรวจการส่ง
# ════════════════════════════════════════════════════════

@app.post("/admin/homework")
async def admin_homework(
    request: Request,
    target: str = Form("level"),
    student_id: str = Form(""),
    level: str = Form(""),
    due_date: str = Form(""),
    subject: str = Form(""),
    title: str = Form(...),
    detail: str = Form(""),
    file_url: str = Form(""),
    file: UploadFile | None = File(None),
):
    """สั่งการบ้าน — แนบไฟล์อัปโหลด หรือใส่ลิงก์ก็ได้"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked

    url = (file_url or "").strip()
    if file is not None and file.filename:
        try:
            url = db.upload_file(await file.read(), file.filename, file.content_type or "")
        except Exception as exc:
            return _back("homework", err=str(exc))

    db.add_homework({
        "student_id": student_id if target == "student" and student_id else None,
        "level": level if target == "level" else None,
        "due_date": due_date or None,
        "subject": subject, "title": title.strip(),
        "detail": detail.strip() or None,
        "file_url": url or None,
    })
    return _back("homework", "homework")


@app.post("/admin/homework/{homework_id}/delete")
def admin_homework_delete(request: Request, homework_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.delete_homework(homework_id)
    return _back("homework", "deleted")


@app.get("/admin/homework/{homework_id}", response_class=HTMLResponse)
def admin_homework_sheet(request: Request, homework_id: str, saved: str = ""):
    """หน้าตรวจการส่งการบ้าน"""
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    hw = db.select_one("homework", id=f"eq.{homework_id}")
    if not hw:
        return _back("homework", err="ไม่พบการบ้านชิ้นนี้")
    return page(request, "admin_homework.html",
                user=user, hw=hw,
                students=db.homework_targets(homework_id),
                saved=saved)


@app.post("/admin/homework/{homework_id}/check")
async def admin_homework_check(request: Request, homework_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    form = await request.form()
    statuses = {k[len("st_"):]: v for k, v in form.items()
                if k.startswith("st_") and v}
    db.save_homework_checks(homework_id, statuses)
    return RedirectResponse(f"/admin/homework/{homework_id}?saved=1", status_code=303)


# ════════════════════════════════════════════════════════
#  3) การสอบ + คะแนน
# ════════════════════════════════════════════════════════

@app.post("/admin/exam/new")
def admin_exam_new(
    request: Request,
    name: str = Form(""),
    date_: str = Form("", alias="date"),
    subject: str = Form(""),
    level: str = Form(""),
    full_score: str = Form("20"),
    note: str = Form(""),
):
    """สร้างการสอบ 1 ครั้ง แล้วไปหน้ากรอกคะแนนทั้งห้องเลย"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        exam = db.save_exam({"name": name, "date": date_, "subject": subject,
                             "level": level, "full_score": full_score, "note": note})
    except Exception as exc:
        return _back("exams", err=str(exc))
    return RedirectResponse(f"/admin/exam/{exam['id']}", status_code=303)


@app.post("/admin/exam/{exam_id}/delete")
def admin_exam_delete(request: Request, exam_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.delete_exam(exam_id)
    return _back("exams", "deleted")


@app.get("/admin/exam/{exam_id}", response_class=HTMLResponse)
def admin_exam_sheet(request: Request, exam_id: str, saved: str = ""):
    """ใบกรอกคะแนน — กรอกทั้งห้องในหน้าเดียว"""
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    exam = db.get_exam(exam_id)
    if not exam:
        return _back("exams", err="ไม่พบการสอบนี้")
    rows = db.exam_sheet(exam_id)
    got = [float(r["score"]) for r in rows if r.get("score") is not None]
    return page(request, "admin_exam.html",
                user=user, exam=exam, students=rows,
                stat={"count": len(got),
                      "average": round(sum(got) / len(got), 1) if got else None,
                      "max": max(got) if got else None,
                      "min": min(got) if got else None},
                saved=saved)


@app.post("/admin/exam/{exam_id}/scores")
async def admin_exam_scores(request: Request, exam_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    form = await request.form()
    scores = {k[len("sc_"):]: v for k, v in form.items() if k.startswith("sc_")}
    comments = {k[len("cm_"):]: v for k, v in form.items() if k.startswith("cm_")}
    try:
        db.save_exam_scores(exam_id, scores, comments)
    except Exception as exc:
        return _back("exams", err=str(exc))
    return RedirectResponse(f"/admin/exam/{exam_id}?saved=1", status_code=303)


# ════════════════════════════════════════════════════════
#  4) เอกสารประกอบการเรียน
# ════════════════════════════════════════════════════════

@app.post("/admin/material")
async def admin_material_new(
    request: Request,
    title: str = Form(""),
    subject: str = Form(""),
    level: str = Form(""),
    detail: str = Form(""),
    file_url: str = Form(""),
    file: UploadFile | None = File(None),
):
    """เพิ่มเอกสาร — อัปโหลดไฟล์ หรือใส่ลิงก์ Google Drive ก็ได้"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked

    url, kind, fname = (file_url or "").strip(), "link", ""
    if file is not None and file.filename:
        try:
            url = db.upload_file(await file.read(), file.filename, file.content_type or "")
            kind, fname = "upload", file.filename
        except Exception as exc:
            return _back("materials", err=str(exc))
    try:
        db.add_material({"title": title, "subject": subject, "level": level,
                         "detail": detail, "file_url": url,
                         "file_name": fname, "kind": kind})
    except Exception as exc:
        return _back("materials", err=str(exc))
    return _back("materials", "material")


@app.post("/admin/material/{material_id}/delete")
def admin_material_delete(request: Request, material_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.delete_material(material_id)
    return _back("materials", "deleted")


# ════════════════════════════════════════════════════════
#  5) แบบฝึกหัด / ข้อสอบออนไลน์
# ════════════════════════════════════════════════════════

def _quiz_page(quiz_id: str | int, saved: str = "", err: str = "") -> RedirectResponse:
    """กลับไปหน้าจัดการข้อของชุดนั้น"""
    q = f"err={quote(err[:200])}" if err else (f"saved={saved}" if saved else "")
    return RedirectResponse(f"/admin/quiz/{quiz_id}?{q}", status_code=303)


async def _question_payload(request: Request, current_image: str = "") -> dict:
    """อ่านฟอร์มคำถาม 1 ข้อ — รองรับทั้ง 4 รูปแบบในฟอร์มเดียว"""
    form = await request.form()
    kind = form.get("kind") or "choice"

    data: dict = {
        "kind": kind,
        "prompt": form.get("prompt") or "",
        "points": form.get("points") or 1,
        "explanation": form.get("explanation") or "",
        # ไม่ได้แนบรูปใหม่ = ใช้รูปเดิม (ยกเว้นกดลบรูป)
        "image_url": "" if form.get("remove_image") else current_image,
        # ใช้เฉพาะโจทย์นับจำนวน
        "icon": form.get("icon") or "",
        "icon_count": form.get("icon_count") or 0,
    }

    upload = form.get("image")
    if upload is not None and getattr(upload, "filename", ""):
        data["image_url"] = db.upload_file(
            await upload.read(), upload.filename, upload.content_type or ""
        )

    if kind in ("choice", "truefalse", "model3d"):
        # โจทย์ 3 มิติใช้ตัวเลือกแบบเดียวกับข้อเลือกตอบ ต่างแค่มีรูปทรงให้ดู
        labels = form.getlist("opt_label")
        images = form.getlist("opt_image")
        try:
            correct = int(form.get("correct_index") or 0)
        except (TypeError, ValueError):
            correct = 0
        data["options"] = [
            {
                "label": label,
                "image_url": images[i] if i < len(images) else "",
                "is_correct": i == correct,
            }
            for i, label in enumerate(labels)
        ]
    elif kind == "fill":
        data["accepted"] = (form.get("accepted") or "").splitlines()
    elif kind == "match":
        lefts = form.getlist("match_left")
        rights = form.getlist("match_right")
        data["options"] = [
            {"label": label, "match_value": rights[i] if i < len(rights) else ""}
            for i, label in enumerate(lefts)
        ]
    return data


@app.post("/admin/quiz/new")
def admin_quiz_new(
    request: Request,
    title: str = Form(""),
    subject: str = Form(""),
    level: str = Form(""),
    time_limit_min: str = Form("0"),
):
    """สร้างชุดแบบฝึกหัดใหม่ แล้วเข้าหน้าใส่คำถามเลย"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        created = quiz.save_quiz({
            "title": title, "subject": subject, "level": level,
            "time_limit_min": time_limit_min,
            # ค่าเริ่มต้นที่เหมาะกับเด็กเล็ก — แก้ทีหลังได้ในหน้าจัดการข้อ
            "shuffle_questions": True, "shuffle_options": True,
            "show_answer_on_wrong": True, "read_aloud": True,
        })
    except Exception as exc:
        return _back("quizzes", err=str(exc))
    return RedirectResponse(f"/admin/quiz/{created['id']}", status_code=303)


@app.get("/admin/quiz/{quiz_id}", response_class=HTMLResponse)
def admin_quiz_edit(request: Request, quiz_id: str, saved: str = "", err: str = ""):
    """หน้าจัดการคำถามของชุดหนึ่ง"""
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    item = quiz.get_quiz(quiz_id)
    if not item:
        return _back("quizzes", err="ไม่พบแบบฝึกหัดชุดนี้")
    return page(request, "admin_quiz.html",
                user=user, quiz=item,
                questions=quiz.list_questions(quiz_id),
                levels=config.LEVELS,
                icon_sets=quiz.ICON_SETS,
                models=quiz.MODELS,
                model_groups=quiz.MODEL_GROUPS,
                ai_ready=gemini.is_ready(),
                saved=saved, err=err)


@app.post("/admin/quiz/{quiz_id}")
def admin_quiz_save(
    request: Request,
    quiz_id: str,
    title: str = Form(""),
    subject: str = Form(""),
    level: str = Form(""),
    description: str = Form(""),
    time_limit_min: str = Form("0"),
    pass_percent: str = Form("60"),
    shuffle_questions: str = Form(""),
    shuffle_options: str = Form(""),
    show_answer_on_wrong: str = Form(""),
    read_aloud: str = Form(""),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        quiz.save_quiz({
            "title": title, "subject": subject, "level": level,
            "description": description,
            "time_limit_min": time_limit_min, "pass_percent": pass_percent,
            "shuffle_questions": bool(shuffle_questions),
            "shuffle_options": bool(shuffle_options),
            "show_answer_on_wrong": bool(show_answer_on_wrong),
            "read_aloud": bool(read_aloud),
        }, quiz_id)
    except Exception as exc:
        return _quiz_page(quiz_id, err=str(exc))
    return _quiz_page(quiz_id, "1")


@app.post("/admin/quiz/{quiz_id}/status/{status}")
def admin_quiz_status(request: Request, quiz_id: str, status: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        quiz.set_quiz_status(quiz_id, status)
    except Exception as exc:
        return _quiz_page(quiz_id, err=str(exc))
    return _quiz_page(quiz_id, "1")


@app.post("/admin/quiz/{quiz_id}/delete")
def admin_quiz_delete(request: Request, quiz_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        quiz.delete_quiz(quiz_id)
    except Exception as exc:
        return _back("quizzes", err=str(exc))
    return _back("quizzes", "deleted")


@app.post("/admin/quiz/{quiz_id}/question")
async def admin_question_new(request: Request, quiz_id: str):
    """เพิ่มคำถามใหม่เข้าชุด"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        quiz.save_question(quiz_id, await _question_payload(request))
    except Exception as exc:
        return _quiz_page(quiz_id, err=str(exc))
    return _quiz_page(quiz_id, "1")


@app.post("/admin/question/{question_id}")
async def admin_question_save(request: Request, question_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    existing = quiz.get_question(question_id)
    if not existing:
        return _back("quizzes", err="ไม่พบคำถามข้อนี้")
    try:
        payload = await _question_payload(request, existing.get("image_url") or "")
        quiz.save_question(existing["quiz_id"], payload, question_id)
    except Exception as exc:
        return _quiz_page(existing["quiz_id"], err=str(exc))
    return _quiz_page(existing["quiz_id"], "1")


@app.post("/admin/question/{question_id}/delete")
def admin_question_delete(request: Request, question_id: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    existing = quiz.get_question(question_id)
    if not existing:
        return _back("quizzes", err="ไม่พบคำถามข้อนี้")
    quiz.delete_question(question_id)
    quiz.renumber(existing["quiz_id"])
    return _quiz_page(existing["quiz_id"], "1")


@app.post("/admin/question/{question_id}/move/{direction}")
def admin_question_move(request: Request, question_id: str, direction: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    existing = quiz.get_question(question_id)
    if not existing:
        return _back("quizzes", err="ไม่พบคำถามข้อนี้")
    if direction in ("up", "down"):
        quiz.move_question(question_id, direction)
    return _quiz_page(existing["quiz_id"], "1")


# ─── แจ้งเตือนผู้ปกครองทาง LINE ───

@app.post("/admin/quiz/{quiz_id}/notify")
def admin_quiz_notify(request: Request, quiz_id: str):
    """ส่งข้อความเข้าไลน์ผู้ปกครองว่ามีแบบฝึกหัดใหม่"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked

    item = quiz.get_quiz(quiz_id)
    if not item:
        return _back("quizzes", err="ไม่พบแบบฝึกหัดชุดนี้")
    if item.get("status") != "published":
        return _quiz_page(quiz_id, err="ต้องกดเผยแพร่ก่อนถึงจะแจ้งเตือนได้ค่ะ")

    questions = quiz.list_questions(quiz_id)
    parents = quiz.parents_to_notify(item.get("level") or "")
    if not parents:
        return _quiz_page(quiz_id, err="ยังไม่มีผู้ปกครองที่ตรงกับระดับชั้นของแบบฝึกหัดชุดนี้")

    try:
        sent = line_push.multicast(
            [p["line_user_id"] for p in parents],
            line_push.new_quiz_message(item, len(questions)),
        )
    except line_push.LinePushError as exc:
        return _quiz_page(quiz_id, err=str(exc))
    except Exception as exc:
        return _quiz_page(quiz_id, err=f"ส่งไม่สำเร็จ ({str(exc)[:120]})")

    quiz.mark_notified(quiz_id)
    return _quiz_page(quiz_id, f"notified-{sent}")


# ─── นำเข้าข้อสอบจากไฟล์ ───

@app.post("/admin/quiz/{quiz_id}/import", response_class=HTMLResponse)
async def admin_quiz_import(request: Request, quiz_id: str,
                            file: UploadFile | None = File(None)):
    """อ่านไฟล์ แล้วพาไปหน้าตรวจทานก่อนบันทึก — ยังไม่เขียนลงฐานข้อมูล"""
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    item = quiz.get_quiz(quiz_id)
    if not item:
        return _back("quizzes", err="ไม่พบแบบฝึกหัดชุดนี้")
    if file is None or not file.filename:
        return _quiz_page(quiz_id, err="กรุณาเลือกไฟล์ก่อนค่ะ")

    try:
        text = quiz_import.extract_text(file.filename, await file.read())
        parsed = quiz_import.parse_questions(text)
    except quiz_import.ImportError_ as exc:
        return _quiz_page(quiz_id, err=str(exc))
    except Exception as exc:
        return _quiz_page(quiz_id, err=f"อ่านไฟล์ไม่สำเร็จ ({str(exc)[:120]})")

    if not parsed:
        return _quiz_page(
            quiz_id,
            err="อ่านไฟล์ได้ แต่แยกเป็นข้อ ๆ ไม่ได้ — "
                "ไฟล์ควรขึ้นต้นแต่ละข้อด้วยเลขข้อ เช่น “1.” และตัวเลือกด้วย “ก.” “ข.”")

    return page(request, "admin_quiz_import.html",
                user=user, quiz=item, parsed=parsed,
                stat=quiz_import.summarize(parsed),
                source=f"ไฟล์ {file.filename}")


@app.post("/admin/quiz/{quiz_id}/import/save")
async def admin_quiz_import_save(request: Request, quiz_id: str):
    """บันทึกข้อที่ครูตรวจแล้วลงชุด"""
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    if not quiz.get_quiz(quiz_id):
        return _back("quizzes", err="ไม่พบแบบฝึกหัดชุดนี้")

    form = await request.form()
    added, skipped = 0, 0

    for index in form.getlist("qindex"):
        if not form.get(f"use_{index}"):
            skipped += 1
            continue

        labels = [v for v in form.getlist(f"opt_{index}") if (v or "").strip()]
        try:
            correct = int(form.get(f"correct_{index}") or -1)
        except (TypeError, ValueError):
            correct = -1

        payload = {
            "kind": "choice",
            "prompt": form.get(f"prompt_{index}") or "",
            "points": 1,
            "explanation": (form.get(f"expl_{index}") or "").strip(),
            "options": [
                {"label": label, "is_correct": (i == correct)}
                for i, label in enumerate(labels)
            ],
        }
        try:
            quiz.save_question(quiz_id, payload)
            added += 1
        except Exception:
            skipped += 1          # ข้อที่ยังไม่ครบ ข้ามไปก่อน ครูค่อยเพิ่มเอง

    if not added:
        return _quiz_page(quiz_id, err="ยังไม่มีข้อไหนบันทึกได้ — "
                                       "ตรวจว่าเลือกเฉลยและมีตัวเลือกอย่างน้อย 2 ตัวแล้วหรือยัง")
    return _quiz_page(quiz_id, f"imported-{added}-{skipped}")


# ─── ผู้ช่วย AI สร้างข้อสอบ ───

@app.post("/admin/quiz/{quiz_id}/ai", response_class=HTMLResponse)
async def admin_quiz_ai(
    request: Request,
    quiz_id: str,
    mode: str = Form("topic"),
    topic: str = Form(""),
    raw: str = Form(""),
    note: str = Form(""),
    count: str = Form("10"),
    files: list[UploadFile] = File(default=[]),
):
    """
    ให้ Gemini ร่างข้อสอบให้ แล้วพาไปหน้าตรวจทานหน้าเดียวกับการนำเข้าไฟล์

    ยังไม่เขียนลงฐานข้อมูล — ครูอ้อยต้องตรวจและกดบันทึกเองเสมอ
    """
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    item = quiz.get_quiz(quiz_id)
    if not item:
        return _back("quizzes", err="ไม่พบแบบฝึกหัดชุดนี้")

    try:
        if mode == "photo":
            blobs = [(f.filename, await f.read())
                     for f in (files or []) if f and f.filename]
            parsed = gemini.from_files(blobs, count, note)
            source = "AI อ่านจากรูป %d ไฟล์" % len(blobs)
        elif mode == "text":
            parsed = gemini.from_text(raw, count, note)
            source = "AI จัดจากข้อความที่วางมา"
        elif mode == "polish":
            parsed = gemini.polish(quiz.list_questions(quiz_id))
            source = "AI เกลาข้อเดิมให้อ่านง่ายขึ้น"
        else:
            parsed = gemini.from_topic(topic, item.get("level") or "",
                                       item.get("subject") or "", count, note)
            source = "AI แต่งจากหัวข้อ “%s”" % topic.strip()
    except gemini.GeminiError as exc:
        return _quiz_page(quiz_id, err=str(exc))
    except Exception as exc:
        return _quiz_page(quiz_id, err="ผู้ช่วย AI ทำงานไม่สำเร็จ (%s)"
                                       % str(exc)[:120])

    if not parsed:
        return _quiz_page(quiz_id, err="AI ยังร่างข้อสอบไม่ได้ — "
                                       "ลองพิมพ์หัวข้อให้ละเอียดขึ้นอีกนิดค่ะ")

    return page(request, "admin_quiz_import.html",
                user=user, quiz=item, parsed=parsed,
                stat=quiz_import.summarize(parsed),
                source=source, by_ai=True)


# ─── รายงานผลของแบบฝึกหัด ───

@app.get("/admin/quiz/{quiz_id}/report", response_class=HTMLResponse)
def admin_quiz_report(request: Request, quiz_id: str):
    """ใครทำแล้ว กี่รอบ ได้กี่คะแนน และข้อไหนเด็กผิดเยอะ"""
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    report = quiz.quiz_report(quiz_id)
    if not report:
        return _back("quizzes", err="ไม่พบแบบฝึกหัดชุดนี้")
    return page(request, "admin_quiz_report.html", user=user, **report)


# ════════════════════════════════════════════════════════
#  6) เด็กทำแบบฝึกหัด — ฝั่งผู้ปกครอง
# ════════════════════════════════════════════════════════

def _parent_scope(request: Request):
    """คืน (parent, children, response) — ถ้า response ไม่ใช่ None ให้ส่งกลับทันที"""
    user = current_line_user(request)
    if not user:
        return None, [], page(request, "login.html")
    try:
        parent = db.get_parent_by_line(user["user_id"])
    except Exception:
        return None, [], RedirectResponse("/portal", status_code=303)
    if not parent or parent.get("status") != "active":
        return None, [], RedirectResponse("/portal", status_code=303)
    return parent, db.get_children(parent["id"]), None


def _attempt_scope(request: Request, attempt_id: str):
    """ดึงรอบการทำ พร้อมตรวจว่าเป็นของลูกตัวเองจริง"""
    parent, children, blocked = _parent_scope(request)
    if blocked:
        return None, None, blocked
    attempt = quiz.get_attempt(attempt_id)
    if not attempt or attempt["student_id"] not in {c["id"] for c in children}:
        return None, None, RedirectResponse("/portal", status_code=303)
    student = next(c for c in children if c["id"] == attempt["student_id"])
    return attempt, student, None


@app.post("/portal/quiz/{quiz_id}/start")
def quiz_start(
    request: Request,
    quiz_id: str,
    student_id: str = Form(...),
    child: int = Form(0),
    mode: str = Form("all"),
):
    """เริ่มทำแบบฝึกหัดรอบใหม่ — mode=wrong คือทบทวนเฉพาะข้อที่เคยผิด"""
    _, children, blocked = _parent_scope(request)
    if blocked:
        return blocked
    if student_id not in {c["id"] for c in children}:
        return RedirectResponse("/portal", status_code=303)
    try:
        started = quiz.start_attempt(quiz_id, student_id, only_wrong=(mode == "wrong"))
    except Exception as exc:
        return RedirectResponse(
            f"/portal?child={child}&quizerr={quote(str(exc)[:150])}#quizzes",
            status_code=303)
    return RedirectResponse(f"/quiz/{started['attempt']['id']}?child={child}",
                            status_code=303)


@app.get("/quiz/{attempt_id}", response_class=HTMLResponse)
def quiz_play(request: Request, attempt_id: str, child: int = 0):
    """หน้าทำแบบฝึกหัด — ทีละข้อ ไม่มีเฉลยฝังอยู่ในหน้า"""
    attempt, student, blocked = _attempt_scope(request, attempt_id)
    if blocked:
        return blocked
    if attempt.get("finished"):
        return RedirectResponse(f"/quiz/{attempt_id}/result?child={child}",
                                status_code=303)

    item = quiz.get_quiz(attempt["quiz_id"])
    questions = quiz.attempt_questions(attempt)
    if not item or not questions:
        return RedirectResponse(f"/portal?child={child}", status_code=303)

    return page(request, "quiz_play.html",
                quiz=item, attempt=attempt, student=student, child=child,
                questions=quiz.public_questions(questions))


@app.post("/quiz/{attempt_id}/answer")
async def quiz_answer(request: Request, attempt_id: str):
    """ตรวจคำตอบ 1 ข้อที่เซิร์ฟเวอร์ แล้วบันทึกผล — เฉลยไม่เคยถูกส่งไปล่วงหน้า"""
    attempt, _, blocked = _attempt_scope(request, attempt_id)
    if blocked:
        return JSONResponse({"error": "no-access"}, status_code=403)
    if attempt.get("finished"):
        return JSONResponse({"error": "finished"}, status_code=409)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad-json"}, status_code=400)

    question = quiz.question_in_attempt(attempt, body.get("question_id"))
    if not question:
        return JSONResponse({"error": "no-question"}, status_code=404)

    given = body.get("given")
    correct = quiz.check_answer(question, given)
    quiz.record_answer(attempt["id"], question["id"],
                       given if not isinstance(given, dict) else str(given), correct)

    item = quiz.get_quiz(attempt["quiz_id"]) or {}
    reveal = bool(item.get("show_answer_on_wrong")) and not correct
    return JSONResponse({
        "correct": correct,
        "answer": quiz.correct_answer_text(question) if reveal else "",
        "explanation": (question.get("explanation") or "") if reveal else "",
    })


@app.post("/quiz/{attempt_id}/finish")
async def quiz_finish(request: Request, attempt_id: str):
    """ปิดรอบ แล้วคืนสรุปคะแนน"""
    attempt, _, blocked = _attempt_scope(request, attempt_id)
    if blocked:
        return JSONResponse({"error": "no-access"}, status_code=403)

    seconds = None
    try:
        seconds = int((await request.json()).get("seconds") or 0)
    except Exception:
        seconds = None

    if attempt.get("finished"):
        done = attempt
    else:
        try:
            done = quiz.finish_attempt(attempt_id, seconds)
        except Exception as exc:
            return JSONResponse({"error": str(exc)[:150]}, status_code=400)

    full = float(done.get("full_score") or 0)
    percent = round(float(done["score"]) / full * 100) if full else 0
    return JSONResponse({
        "score": float(done["score"]),
        "full_score": full,
        "correct_count": done.get("correct_count", 0),
        "total_count": done.get("total_count", 0),
        "percent": percent,
        "stars": quiz.stars_for(percent),
    })


@app.get("/quiz/{attempt_id}/result", response_class=HTMLResponse)
def quiz_result(request: Request, attempt_id: str, child: int = 0):
    """หน้าสรุปผลหลังทำเสร็จ"""
    attempt, student, blocked = _attempt_scope(request, attempt_id)
    if blocked:
        return blocked
    if not attempt.get("finished"):
        return RedirectResponse(f"/quiz/{attempt_id}?child={child}", status_code=303)

    item = quiz.get_quiz(attempt["quiz_id"]) or {}
    full = float(attempt.get("full_score") or 0)
    percent = round(float(attempt["score"]) / full * 100) if full else 0
    wrong = quiz.last_wrong_question_ids(attempt["quiz_id"], attempt["student_id"])

    return page(request, "quiz_result.html",
                quiz=item, attempt=attempt, student=student, child=child,
                percent=percent, stars=quiz.stars_for(percent),
                wrong_count=len(wrong),
                history=quiz.attempt_history(attempt["student_id"],
                                             attempt["quiz_id"], limit=12))
