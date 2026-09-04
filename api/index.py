"""จุดเริ่มต้นสำหรับ Vercel — ชี้ไปที่แอป FastAPI จริงในโฟลเดอร์ app/"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

__all__ = ["app"]
