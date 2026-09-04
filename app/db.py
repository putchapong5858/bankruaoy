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
