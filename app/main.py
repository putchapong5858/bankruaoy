"""
เว็บไซต์เรียนพิเศษบ้านครูอ้อย — https://bankruaoy.com
FastAPI + Jinja2 + Supabase + LINE Login
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import config, db, line_auth

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
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals.update(
    site=config.INSTITUTE,
    site_url=config.SITE_URL,
    levels=config.LEVELS,
)


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


# ────────────────────────────────────────────────
#  หน้าเว็บสาธารณะ
# ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return page(request, "index.html")


@app.get("/healthz")
def healthz():
    return JSONResponse({
        "ok": True,
        "database": db.health(),
        "missing_config": config.missing_config(),
    })


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

    dest = request.session.pop("after_login", "/portal")
    # ถ้าเคยสมัครแล้ว ให้ไปหน้าข้อมูลลูกเลย
    try:
        if db.get_parent_by_line(user["user_id"]):
            dest = "/portal"
    except Exception:
        pass
    return RedirectResponse(dest, status_code=303)


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
    detail = db.get_student_detail(children[index])

    return page(
        request, "portal.html",
        user=user, parent=parent,
        children=children, index=index, s=detail,
        schedule=db.get_schedule(),
        news=db.get_announcements(),
    )


@app.get("/login")
def login(request: Request):
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
def admin(request: Request, saved: str = ""):
    user, blocked = require_admin(request)
    if blocked:
        return blocked

    students = db.list_students()
    return page(
        request, "admin.html",
        user=user,
        pending=db.list_parents("pending"),
        students=students,
        levels=config.LEVELS,
        payment_statuses=config.PAYMENT_STATUSES,
        attendance_statuses=config.ATTENDANCE_STATUSES,
        today=date.today().isoformat(),
        saved=saved,
    )


@app.post("/admin/parent/{parent_id}/{action}")
def admin_parent(request: Request, parent_id: str, action: str):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    if action in ("approve", "reject"):
        db.set_parent_status(parent_id, "active" if action == "approve" else "rejected")
    return RedirectResponse(f"/admin?saved={action}", status_code=303)


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
    return RedirectResponse("/admin?saved=student", status_code=303)


@app.post("/admin/attendance")
def admin_attendance(
    request: Request,
    date_: str = Form(..., alias="date"),
    session: str = Form(""),
    hours: str = Form("3"),
    status: str = Form("มาเรียน"),
    student_id: list[str] = Form([]),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    rows = [{
        "student_id": sid, "date": date_, "session": session,
        "status": status, "hours": float(hours or 0),
    } for sid in student_id]
    db.add_attendance(rows)
    return RedirectResponse("/admin?saved=attendance", status_code=303)


@app.post("/admin/score")
def admin_score(
    request: Request,
    student_id: str = Form(...),
    date_: str = Form(..., alias="date"),
    subject: str = Form(""),
    exam_name: str = Form(""),
    score: str = Form("0"),
    full_score: str = Form("0"),
    comment: str = Form(""),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.add_score({
        "student_id": student_id, "date": date_, "subject": subject,
        "exam_name": exam_name, "score": float(score or 0),
        "full_score": float(full_score or 0), "comment": comment.strip(),
    })
    return RedirectResponse("/admin?saved=score", status_code=303)


@app.post("/admin/homework")
def admin_homework(
    request: Request,
    target: str = Form("level"),
    student_id: str = Form(""),
    level: str = Form(""),
    due_date: str = Form(""),
    subject: str = Form(""),
    title: str = Form(...),
    file_url: str = Form(""),
):
    _, blocked = require_admin(request)
    if blocked:
        return blocked
    db.add_homework({
        "student_id": student_id if target == "student" and student_id else None,
        "level": level if target == "level" else None,
        "due_date": due_date or None,
        "subject": subject, "title": title.strip(),
        "file_url": file_url.strip() or None,
    })
    return RedirectResponse("/admin?saved=homework", status_code=303)


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
    return RedirectResponse("/admin?saved=announcement", status_code=303)
