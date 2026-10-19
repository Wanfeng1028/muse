"""FastAPI 应用入口：创建 app、挂载静态资源、注册路由与页面。"""

from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from ledger import charts
from ledger.config import get_settings
from ledger.database import get_session_factory, init_db
from ledger.logging import RequestIdMiddleware, get_logger, setup_logging
from ledger.models import Category, Currency, Recurring
from ledger.routers import (
    accounts,
    audit,
    bills,
    budgets,
    categories,
    currencies,
    health,
    import_export,
    metrics,
    recurring,
    statements,
    stats,
    transactions,
)
from ledger.seed import ensure_seed
from ledger.services import (
    budget_progress,
    by_category,
    list_accounts_with_balance,
    monthly_summary,
    trend,
    upcoming_recurring,
)


def fmt_money(cents) -> str:
    """分转元：千分位、去多余零。"""
    if cents is None:
        cents = 0
    d = (Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01"))
    s = f"{d:,.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _row_to_dict(row) -> dict:
    """把 ORM 行转成普通 dict。"""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库并确保种子数据存在。"""
    from pathlib import Path

    settings = get_settings()
    get_logger("app").info(
        "startup",
        extra={"extra_data": {"event": "startup", "db_file": Path(settings.db_path).name}},
    )
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await ensure_seed(session)
    yield
    from ledger.database import get_engine

    await get_engine().dispose()
    get_logger("app").info("shutdown", extra={"extra_data": {"event": "engine_disposed"}})


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="钱迹", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)

    # 静态资源
    import os

    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 模板
    templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))
    templates.env.globals["fmt_money"] = fmt_money
    templates.env.filters["fmt_money"] = fmt_money

    # 注册路由
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(bills.router)
    app.include_router(accounts.router)
    app.include_router(audit.router)
    app.include_router(categories.router)
    app.include_router(transactions.router)
    app.include_router(currencies.router)
    app.include_router(budgets.router)
    app.include_router(stats.router)
    app.include_router(import_export.router)
    app.include_router(recurring.router)
    app.include_router(statements.router)

    # ---------- 页面路由 ----------

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, month: str | None = None):
        """首页仪表盘。"""
        from datetime import datetime

        if not month:
            month = datetime.now().strftime("%Y-%m")
        factory = get_session_factory()
        async with factory() as session:
            summary = await monthly_summary(session, month)
            trend_svg = charts.trend_svg(await trend(session, 12))
            cat_svg = charts.hbars_svg(await by_category(session, summary["month"], "expense"))
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "month": month,
                "summary": summary,
                "trend_svg": trend_svg,
                "cat_svg": cat_svg,
                "base_currency": get_settings().base_currency,
            },
        )

    @app.get("/transactions", response_class=HTMLResponse)
    async def transactions_page(request: Request):
        """交易列表页。"""
        factory = get_session_factory()
        async with factory() as session:
            accounts_list = await list_accounts_with_balance(session)
            result = await session.execute(select(Category).order_by(Category.kind, Category.sort_order, Category.id))
            rows = result.scalars().all()
        grouped = {"expense": [], "income": []}
        for row in rows:
            d = {"id": row.id, "name": row.name, "icon": row.icon, "color": row.color}
            if row.kind in grouped:
                grouped[row.kind].append(d)
        return templates.TemplateResponse(
            request,
            "transactions.html",
            {
                "accounts": accounts_list,
                "categories_grouped": grouped,
            },
        )

    @app.get("/currencies", response_class=HTMLResponse)
    async def currencies_page(request: Request):
        """汇率设置页。"""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Currency).order_by(Currency.code))
            rows = [
                {
                    "code": c.code,
                    "rate_to_base": c.rate_to_base,
                    "updated_at": c.updated_at,
                }
                for c in result.scalars().all()
            ]
        return templates.TemplateResponse(
            request,
            "currencies.html",
            {"currencies": rows, "base_currency": get_settings().base_currency},
        )

    @app.get("/accounts", response_class=HTMLResponse)
    async def accounts_page(request: Request):
        """账户列表页。"""
        factory = get_session_factory()
        async with factory() as session:
            items = await list_accounts_with_balance(session)
        return templates.TemplateResponse(
            request,
            "accounts.html",
            {"accounts": items},
        )

    @app.get("/categories", response_class=HTMLResponse)
    async def categories_page(request: Request):
        """分类列表页。"""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Category).order_by(Category.kind, Category.sort_order, Category.id))
            rows = result.scalars().all()
        grouped = {"expense": [], "income": []}
        for row in rows:
            d = {"id": row.id, "name": row.name, "icon": row.icon, "color": row.color}
            if row.kind in grouped:
                grouped[row.kind].append(d)
        return templates.TemplateResponse(
            request,
            "categories.html",
            {"grouped": grouped},
        )

    @app.get("/budgets", response_class=HTMLResponse)
    async def budgets_page(request: Request, month: str | None = None):
        """预算进度页。"""
        from datetime import datetime

        if not month:
            month = datetime.now().strftime("%Y-%m")
        factory = get_session_factory()
        async with factory() as session:
            items = await budget_progress(session, month)
        return templates.TemplateResponse(
            request,
            "budgets.html",
            {"month": month, "items": items},
        )

    @app.get("/recurring", response_class=HTMLResponse)
    async def recurring_page(request: Request):
        """周期性账单页。"""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Recurring).order_by(Recurring.is_active.desc(), Recurring.id))
            rows = result.scalars().all()
            items = [_row_to_dict(r) for r in rows]
            upcoming = await upcoming_recurring(session, 30)
        return templates.TemplateResponse(
            request,
            "recurring.html",
            {"items": items, "upcoming": upcoming},
        )

    @app.get("/import", response_class=HTMLResponse)
    async def import_page(request: Request):
        """CSV 导入页。"""
        return templates.TemplateResponse(
            request,
            "import.html",
            {},
        )

    @app.get("/statement", response_class=HTMLResponse)
    async def statement_page(request: Request):
        """账单导入向导页。"""
        factory = get_session_factory()
        async with factory() as session:
            accounts_list = await list_accounts_with_balance(session)
        account_options = [{"id": a["id"], "name": a["name"]} for a in accounts_list]
        return templates.TemplateResponse(
            request,
            "statement.html",
            {"accounts": account_options},
        )

    @app.get("/bills", response_class=HTMLResponse)
    async def bills_page(request: Request):
        """拍照记账页。"""
        factory = get_session_factory()
        async with factory() as session:
            accounts_list = await list_accounts_with_balance(session)
        account_options = [{"id": a["id"], "name": a["name"]} for a in accounts_list]
        return templates.TemplateResponse(
            request,
            "bills.html",
            {"accounts": account_options},
        )


    @app.get("/bills/review", response_class=HTMLResponse)
    async def review_page(request: Request):
        """OCR 审核页。"""
        return templates.TemplateResponse(request, "review.html", {})

    @app.get("/detective", response_class=HTMLResponse)
    async def detective_page(request: Request):
        """侦探队列页。"""
        factory = get_session_factory()
        async with factory() as session:
            accounts_list = await list_accounts_with_balance(session)
            result = await session.execute(select(Category).order_by(Category.kind, Category.sort_order, Category.id))
            rows = result.scalars().all()
        account_options = [{"id": a["id"], "name": a["name"]} for a in accounts_list]
        grouped = {"expense": [], "income": []}
        for row in rows:
            d = {"id": row.id, "name": row.name, "icon": row.icon, "color": row.color}
            if row.kind in grouped:
                grouped[row.kind].append(d)
        return templates.TemplateResponse(
            request,
            "detective.html",
            {"accounts": account_options, "categories_grouped": grouped},
        )

    return app


app = create_app()


def main():
    """命令行入口：uvicorn 启动。"""
    settings = get_settings()
    import uvicorn

    uvicorn.run("ledger.main:app", host=settings.host, port=settings.port)
