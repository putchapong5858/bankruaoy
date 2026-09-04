"""
คุยกับ Supabase ผ่าน PostgREST โดยตรงด้วย httpx
(ไม่ใช้ไลบรารี supabase-py เพื่อให้ deploy บน Vercel เบาและเร็ว)

ใช้ service role key จึงข้าม RLS ได้ — โค้ดนี้รันบนเซิร์ฟเวอร์เท่านั้น
ห้ามส่ง key นี้ออกไปฝั่งเบราว์เซอร์เด็ดขาด
"""

from __future__ import annotations

from typing import Any

import httpx

from . import config


class SupabaseError(RuntimeError):
    pass


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

    with httpx.Client(timeout=15) as client:
        return _check(client.get(_url(table), headers=_headers(), params=params)) or []


def select_one(table: str, columns: str = "*", **filters: str) -> dict | None:
    rows = select(table, columns, limit=1, **filters)
    return rows[0] if rows else None


def insert(table: str, rows: dict | list[dict]) -> list[dict]:
    headers = _headers() | {"Prefer": "return=representation"}
    with httpx.Client(timeout=15) as client:
        return _check(client.post(_url(table), headers=headers, json=rows)) or []


def update(table: str, values: dict, **filters: str) -> list[dict]:
    if not filters:
        raise SupabaseError("update ต้องระบุเงื่อนไขเสมอ กันการแก้ทั้งตาราง")
    headers = _headers() | {"Prefer": "return=representation"}
    with httpx.Client(timeout=15) as client:
        return _check(
            client.patch(_url(table), headers=headers, params=filters, json=values)
        ) or []


def delete(table: str, **filters: str) -> None:
    if not filters:
        raise SupabaseError("delete ต้องระบุเงื่อนไขเสมอ")
    with httpx.Client(timeout=15) as client:
        _check(client.delete(_url(table), headers=_headers(), params=filters))


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

    attendance = select("attendance", student_id=f"eq.{sid}",
                        order="date.desc", limit=40)
    scores = select("scores", student_id=f"eq.{sid}",
                    order="date.desc", limit=40)

    personal = select("homework", student_id=f"eq.{sid}", order="due_date.desc", limit=40)
    class_wide = select("homework", student_id="is.null",
                        level=f"eq.{level}", order="due_date.desc", limit=40)

    homework = sorted(
        personal + class_wide,
        key=lambda h: (h.get("due_date") or ""),
        reverse=True,
    )[:40]

    return {**student, "attendance": attendance, "scores": scores, "homework": homework}


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


def add_attendance(rows: list[dict]) -> None:
    """บันทึกเช็คชื่อหลายคนพร้อมกัน แล้วบวกชั่วโมงที่ใช้ไปให้อัตโนมัติ"""
    if not rows:
        return
    insert("attendance", rows)
    for r in rows:
        hours = float(r.get("hours") or 0)
        if hours <= 0:
            continue
        cur = select_one("students", "id,hours_used", id=f"eq.{r['student_id']}")
        if cur:
            update("students",
                   {"hours_used": float(cur.get("hours_used") or 0) + hours},
                   id=f"eq.{r['student_id']}")


def add_score(row: dict) -> None:
    insert("scores", row)


def add_homework(row: dict) -> None:
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
