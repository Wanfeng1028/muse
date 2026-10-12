from fastapi import APIRouter

# 创建健康检查路由，统一带有 health 标签
router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict:
    """健康检查接口：返回服务状态和版本号。"""
    return {"status": "ok", "version": "0.1.0"}
