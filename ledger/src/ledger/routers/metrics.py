from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from ledger.database import get_session_factory

# 创建指标路由，统一带有 metrics 标签
router = APIRouter(tags=["metrics"])


@router.get("/api/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus 指标接口：实时从数据库查询各项指标。"""
    from ledger import models

    lines: list[str] = []

    async with get_session_factory()() as session:
        batches_total = (
            await session.execute(select(func.count()).select_from(models.StatementBatch))
        ).scalar_one()

        rows = (
            await session.execute(
                select(models.StatementItem.status, func.count()).group_by(models.StatementItem.status)
            )
        ).all()
        status_counts = {status: count for status, count in rows}

        pending_count = status_counts.get("pending", 0)

        auto_sum = (
            await session.execute(select(func.coalesce(func.sum(models.StatementBatch.auto_count), 0)))
        ).scalar_one()
        total_sum = (
            await session.execute(select(func.coalesce(func.sum(models.StatementBatch.total_count), 0)))
        ).scalar_one()
        auto_match_rate = (auto_sum / total_sum) if total_sum else 0.0

        transactions_total = (
            await session.execute(select(func.count()).select_from(models.Transaction))
        ).scalar_one()

        accounts_total = (
            await session.execute(
                select(func.count())
                .select_from(models.Account)
                .where(models.Account.is_archived == 0)
            )
        ).scalar_one()

    lines.append("# HELP ledger_statement_batches_total 账单批次总数")
    lines.append("# TYPE ledger_statement_batches_total counter")
    lines.append(f"ledger_statement_batches_total {int(batches_total)}")

    lines.append("# HELP ledger_statement_items_total 账单条目按状态分组计数")
    lines.append("# TYPE ledger_statement_items_total counter")
    for status, count in status_counts.items():
        lines.append(f'ledger_statement_items_total{{status="{status}"}} {int(count)}')

    lines.append("# HELP ledger_detective_pending 待认领条目数（侦探队列）")
    lines.append("# TYPE ledger_detective_pending gauge")
    lines.append(f"ledger_detective_pending {int(pending_count)}")

    lines.append("# HELP ledger_auto_match_rate 自动匹配率")
    lines.append("# TYPE ledger_auto_match_rate gauge")
    lines.append(f"ledger_auto_match_rate {auto_match_rate:.3f}")

    lines.append("# HELP ledger_transactions_total 交易总数")
    lines.append("# TYPE ledger_transactions_total counter")
    lines.append(f"ledger_transactions_total {int(transactions_total)}")

    lines.append("# HELP ledger_accounts_total 账户总数（未归档）")
    lines.append("# TYPE ledger_accounts_total gauge")
    lines.append(f"ledger_accounts_total {int(accounts_total)}")

    try:
        from ledger.ocr_metrics import render_ocr_metrics

        lines.append(render_ocr_metrics())
    except Exception as exc:
        from ledger.logging import get_logger

        get_logger("metrics").warning("ocr_metrics_render_failed", extra={"extra_data": {"error": repr(exc)}})

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")
