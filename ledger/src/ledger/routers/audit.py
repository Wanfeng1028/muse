"""账本审计路由：GET /api/audit。"""

from fastapi import APIRouter

from ledger import services
from ledger.database import get_session_factory

router = APIRouter(tags=["audit"])


@router.get("/api/audit")
async def audit() -> dict:
    """账本平衡审计：复式记账恒等式 + 引用完整性检查。"""
    async with get_session_factory()() as s:
        return await services.audit_ledger(s)
