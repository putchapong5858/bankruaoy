"""
คุยกับ Supabase ผ่าน PostgREST โดยตรงด้วย httpx
(ไม่ใช้ไลบรารี supabase-py เพื่อให้ deploy บน Vercel เบาและเร็ว)

ใช้ service role key จึงข้าม RLS ได้ — โค้ดนี้รันบนเซิร์ฟเวอร์เท่านั้น
ห้ามส่ง key นี้ออกไปฝั่งเบราว์เซอร์เด็ดขาด
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from . import config


class SupabaseError(RuntimeError):
    pass


# ── การเชื่อมต่อที่ใช้ซ้ำ ───────────────────────────────────────
# เดิมเปิด httpx.Client ใหม่ทุก query จึงต้องจับมือ TLS ใหม่ทุกครั้ง
# (ประมาณ 3 รอบไป-กลับ) หน้าเดียวมีสิบกว่า query เลยช้ามาก
# เก็บ client ไว้ระดับโมดูล ต่อครั้งเดียวแล้วใช้ซ้ำทุก query
_client: httpx.Client | None = None


def _conn() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=8.0),
            limits=httpx.Limits(max_keepalive_connections=10,
                                max_connections=20,
                                keepalive_expiry=60.0),
        )
    return _client


def _headers() -> dict[str, str]:
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        raise SupabaseError("ยังไม่ได้ตั้งค่า SUPABASE_URL หรือ SUPABASE_SERVICE_KEY")
    return {
        "apikey": config.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _url(table: str) -> str:
    return f"{config.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"


def _check(res: httpx.Response) -> Any:
    if res.status_code >= 400:
        raise SupabaseError(f"Supabase {res.status_code}: {res.text[:300]}")
    if not res.content:
        return None
    return res.json()


def select(
    table: str,
    columns: str = "*",
    order: str | None = None,
    limit: int | None = None,
    **filters: str,
) -> list[dict]:
    """
    อ่านข้อมูล — ตัวกรองใช้รูปแบบ PostgREST เช่น
        select("students", parent_id="eq.<uuid>", order="created_at.asc")
    """
    params: dict[str, str] = {"select": columns}
    params.update(filters)
    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)

    return _check(_conn().get(_url(table), headers=_headers(), params=params)) or []


def select_one(table: str, columns: str = "*", **filters: str) -> dict | None:
    rows = select(table, columns, limit=1, **filters)
    return rows[0] if rows else None


def insert(table: str, rows: dict | list[dict]) -> list[dict]:
    headers = _headers() | {"Prefer": "return=representation"}
    return _check(_conn().post(_url(table), headers=headers, json=rows)) or []


def update(table: str, values: dict, **filters: str) -> list[dict]:
    if not filters:
        raise SupabaseError("update ต้องระบุเงื่อนไขเสมอ กันการแก้ทั้งตาราง")
    headers = _headers() | {"Prefer": "return=representation"}
    return _check(
        _conn().patch(_url(table), headers=headers, params=filters, json=values)
    ) or []


def delete(table: str, **filters: str) -> None:
    if not filters:
        raise SupabaseError("delete ต้องระบุเงื่อนไขเสมอ")
    _check(_conn().delete(_url(table), headers=_headers(), params=filters))


def gather(**jobs):
    """
    ยิงหลาย query พร้อมกันแทนการรอทีละอัน

    ฐานข้อมูลอยู่คนละทวีปกับเซิร์ฟเวอร์ แต่ละ query จึงเสียเวลาเดินทาง
    ถ้ารอทีละอัน 10 query ก็ช้าเป็น 10 เท่า — ยิงพร้อมกันเสียเวลาเท่าอันที่ช้าสุด
    ใช้ได้เฉพาะ query ที่ไม่ต้องรอผลของกันและกัน

        rows = gather(schedule=db.get_schedule, news=db.get_announcements)
        rows["schedule"], rows["news"]
    """
    if not jobs:
        return {}
    with ThreadPoolExecutor(max_workers=min(10, len(jobs))) as pool:
        futures = {key: pool.submit(fn) for key, fn in jobs.items()}
        return {key: fut.result() for key, fut in futures.items()}


def health() -> bool:
    """เช็คว่าต่อฐานข้อมูลได้ไหม"""
    try:
        select("schedule", "id", limit=1)
        return True
    except Exception:
        return False


# ────────────────────────────────────────────────
#  ฟังก์ชันเฉพาะงานของบ้านครูอ้อย
# ────────────────────────────────────────────────

def get_parent_by_line(line_user_id: str) -> dict | None:
    return select_one("parents", line_user_id=f"eq.{line_user_id}")


def next_student_code() -> str:
    rows = select("students", "code", order="code.desc", limit=1)
    top = rows[0]["code"] if rows and rows[0].get("code") else None
    n = 1
    if top and top[1:].isdigit():
        n = int(top[1:]) + 1
    return f"S{n:03d}"


def create_parent_with_children(
    line_user_id: str,
    line_name: str,
    picture_url: str,
    full_name: str,
    phone: str,
    children: list[dict],
) -> dict:
    """สมัครสมาชิก — เขียนผู้ปกครอง 1 แถว และนักเรียนตามจำนวนลูก"""
    existing = get_parent_by_line(line_user_id)

    if existing:
        parent = update(
            "parents",
            {"full_name": full_name, "phone": phone,
             "line_name": line_name, "picture_url": picture_url},
            id=f"eq.{existing['id']}",
        )[0]
        delete("students", parent_id=f"eq.{parent['id']}")
    else:
        parent = insert("parents", {
            "line_user_id": line_user_id,
            "line_name": line_name,
            "picture_url": picture_url,
            "full_name": full_name,
            "phone": phone,
            "status": "pending",
        })[0]

    start = int(next_student_code()[1:])
    rows = [
        {
            "code": f"S{start + i:03d}",
            "parent_id": parent["id"],
            "nickname": child["nickname"],
            "level": child["level"],
        }
        for i, child in enumerate(children)
    ]
    students = insert("students", rows) if rows else []
    return {"parent": parent, "students": students}


def get_children(parent_id: str) -> list[dict]:
    return select(
        "students",
        parent_id=f"eq.{parent_id}",
        active="eq.true",
        order="created_at.asc",
    )


def get_student_detail(student: dict) -> dict:
    """ดึงเช็คชื่อ คะแนน และการบ้านของนักเรียนคนหนึ่ง"""
    sid = student["id"]
    level = student.get("level") or ""

    # ทุกอันนี้ไม่ต้องรอผลของกันและกัน — ยิงพร้อมกันทีเดียว
    got = gather(
        attendance=lambda: select("attendance", student_id=f"eq.{sid}",
                                  order="date.desc", limit=40),
        scores=lambda: select("scores", student_id=f"eq.{sid}",
                              order="date.desc", limit=40),
        personal=lambda: select("homework", student_id=f"eq.{sid}",
                                order="due_date.desc", limit=40),
        class_wide=lambda: select("homework", student_id="is.null",
                                  level=f"eq.{level}", order="due_date.desc", limit=40),
        subs_rows=lambda: select("homework_submissions",
                                 student_id=f"eq.{sid}", limit=200),
        avgs=exam_averages,
        attend_summary=lambda: attendance_summary(sid),
        materials=lambda: list_materials(level),
        sessions=lambda: upcoming_sessions(level),
    )
    attendance = got["attendance"]
    scores = got["scores"]
    personal = got["personal"]
    class_wide = got["class_wide"]

    homework = sorted(
        personal + class_wide,
        key=lambda h: (h.get("due_date") or ""),
        reverse=True,
    )[:40]

    # สถานะการส่งการบ้านของเด็กคนนี้ (ครูเป็นคนกด)
    subs = {str(s["homework_id"]): s for s in got["subs_rows"]}
    for h in homework:
        sub = subs.get(str(h["id"])) or {}
        h["sub_status"] = sub.get("status") or "ยังไม่ส่ง"
        h["sub_comment"] = sub.get("comment") or ""

    # คะแนนเทียบกับค่าเฉลี่ยของห้อง
    avgs = got["avgs"]
    for s in scores:
        s["class_average"] = avgs.get(str(s.get("exam_id"))) if s.get("exam_id") else None

    return {
        **student,
        "attendance": attendance,
        "attend_summary": got["attend_summary"],
        "scores": scores,
        "homework": homework,
        "materials": got["materials"],
        "sessions": got["sessions"],
    }


def get_schedule() -> list[dict]:
    return select("schedule", order="sort_order.asc")


def get_announcements() -> list[dict]:
    from datetime import date
    rows = select("announcements", active="eq.true", order="published_at.desc", limit=10)
    today = date.today().isoformat()
    return [r for r in rows if not r.get("show_until") or r["show_until"] >= today]


# ────────────────────────────────────────────────
#  สำหรับหน้าจัดการของครูอ้อย
# ────────────────────────────────────────────────

def list_parents(status: str | None = None) -> list[dict]:
    filters = {"status": f"eq.{status}"} if status else {}
    return select("parents", order="created_at.desc", **filters)


def list_students(active_only: bool = True) -> list[dict]:
    filters = {"active": "eq.true"} if active_only else {}
    rows = select("students", order="code.asc", **filters)
    parents = {p["id"]: p for p in select("parents")}
    for r in rows:
        p = parents.get(r.get("parent_id")) or {}
        r["parent_name"] = p.get("full_name", "")
        r["parent_phone"] = p.get("phone", "")
        r["parent_status"] = p.get("status", "")
    return rows


def set_parent_status(parent_id: str, status: str) -> None:
    values = {"status": status}
    if status == "active":
        from datetime import datetime, timezone
        values["approved_at"] = datetime.now(timezone.utc).isoformat()
    update("parents", values, id=f"eq.{parent_id}")


def update_student(student_id: str, values: dict) -> None:
    clean = {k: v for k, v in values.items() if v is not None and v != ""}
    if clean:
        update("students", clean, id=f"eq.{student_id}")


def recalc_hours_used(student_id: str) -> float:
    """คำนวณชั่วโมงที่ใช้ไปใหม่ทั้งหมด จากประวัติเข้าเรียนจริง

    วิธีนี้แทนการ "บวกเพิ่มทีละครั้ง" ที่ทำให้ชั่วโมงเพี้ยนเวลาครูเช็คชื่อซ้ำ
    หรือแก้ไขย้อนหลัง — รวมใหม่ทุกครั้งจึงตรงกับความจริงเสมอ
    """
    rows = select("attendance", "hours", student_id=f"eq.{student_id}", limit=1000)
    total = sum(float(r.get("hours") or 0) for r in rows)
    update("students", {"hours_used": total}, id=f"eq.{student_id}")
    return total


def add_attendance(rows: list[dict]) -> None:
    """บันทึกเช็คชื่อหลายคนพร้อมกัน แล้วคำนวณชั่วโมงคงเหลือให้ใหม่"""
    if not rows:
        return
    insert("attendance", rows)
    for sid in {r["student_id"] for r in rows}:
        recalc_hours_used(sid)


def add_score(row: dict) -> None:
    insert("scores", row)


def add_homework(row: dict) -> None:
    from datetime import date as _date
    row.setdefault("assigned_date", _date.today().isoformat())
    row.setdefault("active", True)
    insert("homework", row)


def add_announcement(row: dict) -> None:
    insert("announcements", row)


# ────────────────────────────────────────────────
#  คอร์สเรียน และคำขอลงคอร์ส
# ────────────────────────────────────────────────

def list_courses() -> list[dict]:
    return select("courses", active="eq.true", order="sort_order.asc")


def get_course(course_id: str | int) -> dict | None:
    return select_one("courses", id=f"eq.{course_id}")


def get_enrollments(student_id: str) -> list[dict]:
    rows = select("enrollments", student_id=f"eq.{student_id}",
                  order="requested_at.desc", limit=20)
    courses = {str(c["id"]): c for c in select("courses")}
    for r in rows:
        c = courses.get(str(r.get("course_id"))) or {}
        r["course_name"] = c.get("name", "")
        r["course_code"] = c.get("code", "")
    return rows


def request_enrollment(student_id: str, course_id: str | int, hours: float) -> dict:
    """ผู้ปกครองส่งคำขอลงคอร์ส — ยังไม่หักเงินหรือเพิ่มชั่วโมงจนกว่าครูจะยืนยัน"""
    course = get_course(course_id)
    if not course:
        raise SupabaseError("ไม่พบคอร์สที่เลือก")

    if course.get("is_hourly"):
        hours = max(1.0, min(float(hours or 1), 100.0))
        price = hours * float(course.get("price") or 0)
    else:
        hours = float(course.get("hours") or 0)
        price = float(course.get("price") or 0)

    pending = select("enrollments", student_id=f"eq.{student_id}",
                     course_id=f"eq.{course_id}", status="eq.requested", limit=1)
    if pending:
        raise SupabaseError("มีคำขอคอร์สนี้รอครูอ้อยยืนยันอยู่แล้ว")

    return insert("enrollments", {
        "student_id": student_id, "course_id": course["id"],
        "hours": hours, "price": price, "status": "requested",
    })[0]


def list_enrollment_requests() -> list[dict]:
    """คำขอที่รอครูอ้อยยืนยัน พร้อมชื่อนักเรียนและผู้ปกครอง"""
    rows = select("enrollments", status="eq.requested", order="requested_at.asc")
    if not rows:
        return []
    students = {s["id"]: s for s in select("students")}
    parents = {p["id"]: p for p in select("parents")}
    courses = {str(c["id"]): c for c in select("courses")}
    for r in rows:
        s = students.get(r.get("student_id")) or {}
        p = parents.get(s.get("parent_id")) or {}
        c = courses.get(str(r.get("course_id"))) or {}
        r["nickname"] = s.get("nickname", "")
        r["level"] = s.get("level", "")
        r["code"] = s.get("code", "")
        r["parent_name"] = p.get("full_name", "")
        r["parent_phone"] = p.get("phone", "")
        r["course_name"] = c.get("name", "")
    return rows


def confirm_enrollment(enrollment_id: str | int) -> None:
    """ครูอ้อยยืนยัน — บวกชั่วโมงเข้าให้นักเรียนอัตโนมัติ"""
    from datetime import datetime, timezone

    en = select_one("enrollments", id=f"eq.{enrollment_id}")
    if not en or en.get("status") != "requested":
        return

    stu = select_one("students", "id,hours_bought", id=f"eq.{en['student_id']}")
    if stu:
        update("students",
               {"hours_bought": float(stu.get("hours_bought") or 0) + float(en.get("hours") or 0)},
               id=f"eq.{stu['id']}")

    update("enrollments",
           {"status": "confirmed",
            "confirmed_at": datetime.now(timezone.utc).isoformat()},
           id=f"eq.{enrollment_id}")


def cancel_enrollment(enrollment_id: str | int) -> None:
    update("enrollments", {"status": "cancelled"}, id=f"eq.{enrollment_id}")


# ────────────────────────────────────────────────
#  จัดการคอร์ส (เฉพาะครูอ้อย)
# ────────────────────────────────────────────────

def list_all_courses() -> list[dict]:
    """ทุกคอร์ส รวมที่ปิดขายอยู่ — ใช้ในหน้าจัดการ"""
    return select("courses", order="sort_order.asc")


def _course_fields(data: dict) -> dict:
    """ทำความสะอาดข้อมูลคอร์สจากฟอร์ม ก่อนเขียนลงฐานข้อมูล"""
    name = (data.get("name") or "").strip()[:120]
    if not name:
        raise SupabaseError("กรุณากรอกชื่อคอร์ส")

    is_hourly = bool(data.get("is_hourly"))

    def num(key, default=0.0):
        try:
            return float(str(data.get(key) or default).strip() or default)
        except (TypeError, ValueError):
            return float(default)

    price = max(0.0, num("price"))
    hours = 1.0 if is_hourly else max(0.0, num("hours"))

    return {
        "name": name,
        "description": (data.get("description") or "").strip()[:300],
        "hours": hours,
        "price": price,
        "is_hourly": is_hourly,
        "highlight": bool(data.get("highlight")),
        "active": bool(data.get("active")),
        "sort_order": int(num("sort_order", 99)),
    }


def create_course(data: dict) -> dict:
    fields = _course_fields(data)
    code = (data.get("code") or "").strip().upper()[:20]
    if not code:
        # สร้างรหัสอัตโนมัติ ถ้าครูไม่ได้กรอกมา
        used = {str(c.get("code") or "").upper() for c in select("courses")}
        n = 1
        while f"COURSE{n}" in used:
            n += 1
        code = f"COURSE{n}"
    elif select("courses", code=f"eq.{code}", limit=1):
        raise SupabaseError(f"รหัสคอร์ส {code} ถูกใช้ไปแล้ว กรุณาใช้รหัสอื่น")
    fields["code"] = code
    return insert("courses", fields)[0]


def update_course(course_id: str | int, data: dict) -> None:
    update("courses", _course_fields(data), id=f"eq.{course_id}")


def set_course_active(course_id: str | int, active: bool) -> None:
    update("courses", {"active": bool(active)}, id=f"eq.{course_id}")


def delete_course(course_id: str | int) -> None:
    """ลบคอร์ส — ถ้ามีคนลงเรียนไปแล้วจะปิดขายแทน เพื่อไม่ให้ประวัติหาย"""
    used = select("enrollments", course_id=f"eq.{course_id}", limit=1)
    if used:
        set_course_active(course_id, False)
        raise SupabaseError(
            "คอร์สนี้มีผู้ปกครองลงเรียนไปแล้ว ระบบจึงปิดการขายให้แทนการลบ "
            "(ประวัติการเรียนของนักเรียนจะได้ไม่หาย)"
        )
    delete("courses", id=f"eq.{course_id}")


# ════════════════════════════════════════════════════════
#  1) คาบเรียน + เช็คชื่อ
# ════════════════════════════════════════════════════════

def list_sessions(limit: int = 40) -> list[dict]:
    """คาบเรียนทั้งหมด ใหม่สุดอยู่บน พร้อมจำนวนคนที่เช็คชื่อแล้ว"""
    rows = select("sessions", order="date.desc,time_range.asc", limit=limit)
    if not rows:
        return []
    marked = select("attendance", "session_id,status", limit=2000)
    for s in rows:
        mine = [a for a in marked if str(a.get("session_id")) == str(s["id"])]
        s["checked"] = len(mine)
        s["present"] = sum(1 for a in mine if a.get("status") == "มาเรียน")
    return rows


def upcoming_sessions(level: str = "", limit: int = 4) -> list[dict]:
    """คาบเรียนที่กำลังจะถึง — ใช้โชว์ในหน้าผู้ปกครอง"""
    from datetime import date as _date
    rows = select("sessions", date=f"gte.{_date.today().isoformat()}",
                  order="date.asc,time_range.asc", limit=40)
    return [r for r in rows if r.get("status") == "เปิดเรียน"][:limit]


def get_session(session_id: str | int) -> dict | None:
    return select_one("sessions", id=f"eq.{session_id}")


def save_session(data: dict, session_id: str | int | None = None) -> dict | None:
    """เพิ่มหรือแก้ไขคาบเรียน"""
    if not (data.get("date") or "").strip():
        raise SupabaseError("กรุณาเลือกวันที่ของคาบเรียน")
    try:
        hours = max(0.0, min(float(data.get("hours") or 0), 12.0))
    except (TypeError, ValueError):
        hours = 0.0
    fields = {
        "date": data["date"],
        "time_range": (data.get("time_range") or "").strip()[:60] or "09.00 - 12.00 น.",
        "level": (data.get("level") or "").strip()[:120],
        "subjects": (data.get("subjects") or "").strip()[:200],
        "hours": hours,
        "status": data.get("status") or "เปิดเรียน",
        "note": (data.get("note") or "").strip()[:300],
    }
    if session_id:
        update("sessions", fields, id=f"eq.{session_id}")
        # ถ้าแก้จำนวนชั่วโมง ต้องปรับแถวเช็คชื่อและชั่วโมงคงเหลือตามด้วย
        taken = select("attendance", "student_id,status", session_id=f"eq.{session_id}", limit=500)
        if taken:
            update("attendance", {"hours": hours},
                   session_id=f"eq.{session_id}", status="eq.มาเรียน")
            for sid in {t["student_id"] for t in taken}:
                recalc_hours_used(sid)
        return get_session(session_id)
    return insert("sessions", fields)[0]


def delete_session(session_id: str | int) -> None:
    """ลบคาบเรียน — ลบการเช็คชื่อของคาบนี้ด้วย แล้วคืนชั่วโมงให้นักเรียน"""
    taken = select("attendance", "student_id", session_id=f"eq.{session_id}", limit=500)
    delete("attendance", session_id=f"eq.{session_id}")   # ลบเองไม่พึ่ง cascade
    delete("sessions", id=f"eq.{session_id}")
    for sid in {t["student_id"] for t in taken}:
        recalc_hours_used(sid)


def session_attendance(session_id: str | int) -> dict[str, dict]:
    """เช็คชื่อของคาบนี้ คืนเป็น {student_id: แถว} เพื่อให้ฟอร์มติ๊กค้างไว้ได้"""
    rows = select("attendance", session_id=f"eq.{session_id}", limit=500)
    return {r["student_id"]: r for r in rows}


def save_attendance(session_id: str | int, present_ids: list[str],
                    statuses: dict | None = None) -> None:
    """บันทึกเช็คชื่อของคาบหนึ่ง — เขียนทับของเดิมได้ ชั่วโมงไม่เพี้ยน

    ติ๊กใหม่ = เพิ่มแถว, เอาติ๊กออก = ลบแถว, แล้วคำนวณชั่วโมงใหม่ทั้งหมด
    """
    ses = get_session(session_id)
    if not ses:
        raise SupabaseError("ไม่พบคาบเรียนนี้")

    hours = float(ses.get("hours") or 0)
    statuses = statuses or {}
    old = session_attendance(session_id)
    touched = set(old.keys()) | set(present_ids)

    delete("attendance", session_id=f"eq.{session_id}")
    rows = []
    for sid in present_ids:
        st = statuses.get(sid) or "มาเรียน"
        rows.append({
            "student_id": sid, "session_id": ses["id"], "date": ses["date"],
            "session": ses.get("time_range"), "status": st,
            # มาเรียนเท่านั้นที่หักชั่วโมง — ลา/ขาด ไม่หัก
            "hours": hours if st == "มาเรียน" else 0,
        })
    if rows:
        insert("attendance", rows)
    for sid in touched:
        recalc_hours_used(sid)


def attendance_summary(student_id: str) -> dict:
    """สรุปการเข้าเรียนของนักเรียนคนหนึ่ง"""
    rows = select("attendance", "status", student_id=f"eq.{student_id}", limit=500)
    total = len(rows)
    present = sum(1 for r in rows if r.get("status") == "มาเรียน")
    return {
        "total": total, "present": present, "absent": total - present,
        "percent": round(present / total * 100) if total else 0,
    }


# ════════════════════════════════════════════════════════
#  2) การบ้าน + การตรวจส่ง
# ════════════════════════════════════════════════════════

def list_homework(limit: int = 30) -> list[dict]:
    """การบ้านทั้งหมด พร้อมจำนวนคนที่ส่งแล้ว"""
    rows = select("homework", active="eq.true", order="assigned_date.desc,id.desc", limit=limit)
    if not rows:
        return []
    subs = select("homework_submissions", "homework_id,student_id,status", limit=2000)
    students = {s["id"]: s for s in select("students", "id,nickname,level,active")}
    for h in rows:
        mine = [s for s in subs if str(s["homework_id"]) == str(h["id"])]
        h["submitted"] = sum(1 for s in mine if s.get("status") != "ไม่ได้ส่ง")
        if h.get("student_id"):
            stu = students.get(h["student_id"]) or {}
            h["target"] = f"รายคน · {stu.get('nickname', '-')}"
            h["total"] = 1
        else:
            h["target"] = f"ทั้งชั้น · {h.get('level') or 'ทุกระดับ'}"
            h["total"] = sum(1 for s in students.values()
                             if s.get("active") and s.get("level") == h.get("level"))
    return rows


def homework_targets(homework_id: str | int) -> list[dict]:
    """รายชื่อนักเรียนที่ต้องส่งการบ้านชิ้นนี้ พร้อมสถานะการส่ง"""
    hw = select_one("homework", id=f"eq.{homework_id}")
    if not hw:
        return []
    if hw.get("student_id"):
        students = select("students", active="eq.true", id=f"eq.{hw['student_id']}")
    else:
        students = select("students", active="eq.true",
                          level=f"eq.{hw.get('level') or ''}", order="nickname.asc")
    subs = {s["student_id"]: s for s in
            select("homework_submissions", homework_id=f"eq.{homework_id}", limit=500)}
    for s in students:
        sub = subs.get(s["id"]) or {}
        s["sub_status"] = sub.get("status") or ""
        s["sub_comment"] = sub.get("comment") or ""
    return students


def save_homework_checks(homework_id: str | int, statuses: dict[str, str]) -> None:
    """ครูกดว่าใครส่งแล้ว — เขียนทับของเดิมทั้งชุด"""
    delete("homework_submissions", homework_id=f"eq.{homework_id}")
    rows = [{"homework_id": int(homework_id), "student_id": sid, "status": st}
            for sid, st in statuses.items() if st]
    if rows:
        insert("homework_submissions", rows)


def update_homework(homework_id: str | int, values: dict) -> None:
    update("homework", values, id=f"eq.{homework_id}")


def delete_homework(homework_id: str | int) -> None:
    """ลบการบ้าน พร้อมประวัติการตรวจส่งของการบ้านชิ้นนั้น"""
    delete("homework_submissions", homework_id=f"eq.{homework_id}")
    delete("homework", id=f"eq.{homework_id}")


# ════════════════════════════════════════════════════════
#  3) การสอบ + คะแนน
# ════════════════════════════════════════════════════════

def list_exams(limit: int = 30) -> list[dict]:
    """การสอบทั้งหมด พร้อมสถิติของแต่ละครั้ง"""
    rows = select("exams", order="date.desc,id.desc", limit=limit)
    if not rows:
        return []
    all_scores = select("scores", "exam_id,score", limit=2000)
    for e in rows:
        vals = [float(s["score"]) for s in all_scores
                if str(s.get("exam_id")) == str(e["id"]) and s.get("score") is not None]
        e["count"] = len(vals)
        e["average"] = round(sum(vals) / len(vals), 1) if vals else None
        e["max"] = max(vals) if vals else None
        e["min"] = min(vals) if vals else None
    return rows


def get_exam(exam_id: str | int) -> dict | None:
    return select_one("exams", id=f"eq.{exam_id}")


def save_exam(data: dict, exam_id: str | int | None = None) -> dict | None:
    name = (data.get("name") or "").strip()[:120]
    if not name:
        raise SupabaseError("กรุณากรอกชื่อการสอบ")
    try:
        full = max(1.0, float(data.get("full_score") or 20))
    except (TypeError, ValueError):
        full = 20.0
    fields = {
        "name": name,
        "date": data.get("date") or None,
        "subject": (data.get("subject") or "").strip()[:60],
        "level": (data.get("level") or "").strip()[:60],
        "full_score": full,
        "note": (data.get("note") or "").strip()[:300],
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    if exam_id:
        update("exams", fields, id=f"eq.{exam_id}")
        return get_exam(exam_id)
    return insert("exams", fields)[0]


def delete_exam(exam_id: str | int) -> None:
    """ลบการสอบ พร้อมคะแนนทั้งหมดของครั้งนั้น"""
    delete("scores", exam_id=f"eq.{exam_id}")
    delete("exams", id=f"eq.{exam_id}")


def exam_sheet(exam_id: str | int) -> list[dict]:
    """ใบกรอกคะแนน — รายชื่อนักเรียนตามระดับชั้นของการสอบ พร้อมคะแนนที่กรอกไว้"""
    exam = get_exam(exam_id)
    if not exam:
        return []
    lv = (exam.get("level") or "").strip()
    students = (select("students", active="eq.true", level=f"eq.{lv}", order="nickname.asc")
                if lv else select("students", active="eq.true", order="level.asc,nickname.asc"))
    got = {s["student_id"]: s for s in
           select("scores", exam_id=f"eq.{exam_id}", limit=500)}
    for s in students:
        row = got.get(s["id"]) or {}
        s["score"] = row.get("score")
        s["score_comment"] = row.get("comment") or ""
    return students


def save_exam_scores(exam_id: str | int, scores: dict[str, str],
                     comments: dict[str, str] | None = None) -> int:
    """กรอกคะแนนทั้งห้องในครั้งเดียว — เว้นว่างไว้ = ยังไม่ได้สอบ ไม่บันทึก"""
    exam = get_exam(exam_id)
    if not exam:
        raise SupabaseError("ไม่พบการสอบนี้")
    comments = comments or {}
    delete("scores", exam_id=f"eq.{exam_id}")

    rows = []
    for sid, raw in scores.items():
        raw = (raw or "").strip()
        if raw == "":
            continue
        try:
            val = max(0.0, min(float(raw), float(exam["full_score"])))
        except (TypeError, ValueError):
            continue
        rows.append({
            "student_id": sid, "exam_id": exam["id"], "date": exam["date"],
            "subject": exam.get("subject"), "exam_name": exam["name"],
            "score": val, "full_score": exam["full_score"],
            "comment": (comments.get(sid) or "").strip()[:200] or None,
        })
    if rows:
        insert("scores", rows)
    return len(rows)


def exam_averages() -> dict[str, float]:
    """ค่าเฉลี่ยของการสอบแต่ละครั้ง — ใช้ให้ผู้ปกครองเทียบกับคะแนนลูก"""
    rows = select("scores", "exam_id,score", limit=2000)
    buckets: dict[str, list[float]] = {}
    for r in rows:
        if r.get("exam_id") is None or r.get("score") is None:
            continue
        buckets.setdefault(str(r["exam_id"]), []).append(float(r["score"]))
    return {k: round(sum(v) / len(v), 1) for k, v in buckets.items() if v}


# ════════════════════════════════════════════════════════
#  4) เอกสารประกอบการเรียน
# ════════════════════════════════════════════════════════

def list_materials(level: str | None = None, limit: int = 60) -> list[dict]:
    rows = select("materials", active="eq.true", order="created_at.desc", limit=limit)
    if level is None:
        return rows
    # ผู้ปกครองเห็นเอกสารของระดับชั้นลูก + เอกสารที่ให้ทุกระดับ
    return [m for m in rows if not (m.get("level") or "").strip()
            or (m.get("level") or "").strip() == level]


def add_material(data: dict) -> dict:
    title = (data.get("title") or "").strip()[:150]
    url = (data.get("file_url") or "").strip()
    if not title:
        raise SupabaseError("กรุณากรอกชื่อเอกสาร")
    if not url:
        raise SupabaseError("กรุณาแนบไฟล์ หรือใส่ลิงก์เอกสาร")
    if not url.startswith(("http://", "https://")):
        raise SupabaseError("ลิงก์ต้องขึ้นต้นด้วย http:// หรือ https://")
    return insert("materials", {
        "title": title,
        "subject": (data.get("subject") or "").strip()[:60],
        "level": (data.get("level") or "").strip()[:60],
        "detail": (data.get("detail") or "").strip()[:300],
        "file_url": url,
        "file_name": (data.get("file_name") or "").strip()[:200],
        "kind": data.get("kind") or "link",
        "active": True,
    })[0]


def delete_material(material_id: str | int) -> None:
    delete("materials", id=f"eq.{material_id}")


# ════════════════════════════════════════════════════════
#  ประกาศ — เพิ่มการดูรายการและลบ
# ════════════════════════════════════════════════════════

def list_announcements(limit: int = 20) -> list[dict]:
    return select("announcements", order="published_at.desc,id.desc", limit=limit)


def delete_announcement(announcement_id: str | int) -> None:
    delete("announcements", id=f"eq.{announcement_id}")


# ════════════════════════════════════════════════════════
#  อัปโหลดไฟล์เข้า Supabase Storage
# ════════════════════════════════════════════════════════

STORAGE_BUCKET = "materials"
MAX_UPLOAD_BYTES = 4 * 1024 * 1024      # 4 MB — เพดานของ Vercel ต่อ 1 คำขอ
ALLOWED_TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/gif": ".gif", "application/pdf": ".pdf",
}


def upload_file(data: bytes, filename: str, content_type: str) -> str:
    """อัปโหลดไฟล์ขึ้น Supabase Storage แล้วคืนลิงก์สาธารณะ"""
    import re as _re
    import uuid as _uuid
    from datetime import date as _date

    if not data:
        raise SupabaseError("ไฟล์ว่าง กรุณาเลือกไฟล์ใหม่")
    if len(data) > MAX_UPLOAD_BYTES:
        raise SupabaseError(
            f"ไฟล์ใหญ่เกินไป ({len(data) / 1024 / 1024:.1f} MB) "
            "รองรับไม่เกิน 4 MB — ถ้าเป็นไฟล์ใหญ่ให้อัปขึ้น Google Drive แล้วใส่ลิงก์แทนค่ะ"
        )
    ext = ALLOWED_TYPES.get((content_type or "").split(";")[0].strip())
    if not ext:
        raise SupabaseError("รองรับเฉพาะรูปภาพ (JPG, PNG, WEBP, GIF) และไฟล์ PDF เท่านั้นค่ะ")

    stem = _re.sub(r"[^A-Za-z0-9ก-๙_-]+", "-", (filename or "file").rsplit(".", 1)[0])[:40]
    key = f"{_date.today():%Y/%m}/{_uuid.uuid4().hex[:10]}-{stem or 'file'}{ext}"

    url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{STORAGE_BUCKET}/{key}"
    headers = {
        "apikey": config.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "false",
    }
    with httpx.Client(timeout=60) as client:
        res = client.post(url, headers=headers, content=data)
    if res.status_code >= 400:
        raise SupabaseError(f"อัปโหลดไม่สำเร็จ ({res.status_code}) กรุณาลองใหม่อีกครั้ง")

    return f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{STORAGE_BUCKET}/{key}"
