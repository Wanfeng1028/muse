from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ledger.database import get_session_factory

# 创建健康检查路由，统一带有 health 标签
router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict:
    """健康检查接口：返回服务状态和版本号。"""
    return {"status": "ok", "version": "2.1.0"}


@router.get("/api/ready")
async def ready():
    """就绪探针：探测数据库连通性。"""
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"ready": False, "error": type(exc).__name__})
    return {"ready": True}
