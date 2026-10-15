from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger import matching, statement_parser
from ledger.database import get_session
from ledger.models import (
    Account,
    Category,
    MatchRule,
    StatementBatch,
    StatementItem,
    StatementTemplate,
    Transaction,
    utcnow,
)
from ledger.schemas import (
    ClaimIn,
    ClaimTransferIn,
    MatchRuleCreate,
    MatchRuleOut,
    ParsePreviewOut,
    StatementBatchOut,
    StatementCandidate,
    StatementItemOut,
    StatementTemplateCreate,
    StatementTemplateOut,
    UploadOut,
)

router = APIRouter(tags=["statements"])

# 账单侦探


async def ensure_builtin_templates(session: AsyncSession) -> None:
    """确保内置账单模板存在（按 name 查无则插入）。"""
    existing = (await session.execute(select(StatementTemplate.name))).scalars().all()
    existing_set = set(existing)
    for name, tpl in statement_parser.BUILTIN_TEMPLATES.items():
        if tpl["name"] in existing_set:
            continue
        session.add(
            StatementTemplate(
                name=tpl["name"],
                source=tpl["source"],
                mapping_json=json.dumps(tpl["mapping"], ensure_ascii=False),
            )
        )
    await session.commit()


def _all_builtin_header_hint() -> set[str]:
    """汇总所有内置模板的表头名，作为表头探测提示。"""
    hint: set[str] = set()
    for tpl in statement_parser.BUILTIN_TEMPLATES.values():
        for v in tpl["mapping"].values():
            if v:
                hint.add(v)
    return hint


def _extract_table(text: str, mapping_hint: dict) -> tuple[list[str], list[dict]]:
    """解析 CSV 文本，前 15 行内探测表头并返回 (headers, data_rows)。

    命中率 >=60% 的第一行作为表头；找不到则默认第 1 行为表头。空行跳过。
    """
    reader = csv.reader(io.StringIO(text))
    all_rows = [row for row in reader if any((c or "").strip() for c in row)]
    if not all_rows:
        return [], []

    # 表头探测：逐模板计算命中率，取最优（模板，行）；避免用全模板并集稀释比率
    template_headers: list[set[str]] = []
    if mapping_hint:
        template_headers.append({v for v in mapping_hint.values() if v})
    else:
        for tpl in statement_parser.BUILTIN_TEMPLATES.values():
            template_headers.append({v for v in tpl["mapping"].values() if v})

    header_idx = 0
    limit = min(15, len(all_rows))
    best: tuple[float, int] | None = None
    for names in template_headers:
        if not names:
            continue
        for i in range(limit):
            row = all_rows[i]
            if not row:
                continue
            cells = {(c or "").strip() for c in row}
            matched = sum(1 for h in names if h in cells)
            ratio = matched / len(names)
            if ratio >= 0.6 and (best is None or ratio > best[0]):
                best = (ratio, i)
    if best is not None:
        header_idx = best[1]
    # 若未命中，header_idx 保持 0（默认第 1 行为表头）

    headers = [h.strip() for h in all_rows[header_idx]]
    data_rows: list[dict] = []
    for row in all_rows[header_idx + 1 :]:
        if not row:
            continue
        record = {}
        for i, h in enumerate(headers):
            record[h] = row[i] if i < len(row) else ""
        data_rows.append(record)
    return headers, data_rows


def _resolve_mapping(
    explicit: dict | None,
    template: StatementTemplate | None,
    headers: list[str],
) -> dict[str, str]:
    """确定列映射：显式 > 模板 > 自动探测。"""
    if explicit:
        mapping = dict(explicit)
    elif template is not None:
        try:
            mapping = json.loads(template.mapping_json)
        except json.JSONDecodeError:
            mapping = {}
        if not isinstance(mapping, dict):
            mapping = {}
    else:
        mapping = statement_parser.auto_detect_mapping(headers)
    return mapping


def _builtin_name_for_mapping(mapping: dict) -> str | None:
    """按 mapping 反查内置模板名（自动识别命中时用）。"""
    for tpl in statement_parser.BUILTIN_TEMPLATES.values():
        if tpl["mapping"] == mapping:
            return tpl["name"]
    return None


async def _builtin_template_id(session: AsyncSession, name: str) -> int | None:
    """按模板名查库内模板 id（内置模板已由 ensure_builtin_templates 落库）。"""
    row = (
        await session.execute(select(StatementTemplate.id).where(StatementTemplate.name == name))
    ).scalar_one_or_none()
    return int(row) if row is not None else None


async def _load_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


def _direction_matches_kind(direction: str, kind: str) -> bool:
    """校验 direction 与 category.kind 是否对应（in→income/out→expense）。"""
    if direction == "in":
        return kind == "income"
    if direction == "out":
        return kind == "expense"
    return False


def _build_note(counterparty: str, summary: str) -> str:
    return f"{counterparty or ''} {summary or ''}".strip()


async def _load_history(session: AsyncSession) -> list[dict]:
    """构造历史记录列表，用于 match_by_history / suggest_candidates。"""
    rows = (
        await session.execute(
            select(
                StatementItem.counterparty,
                StatementItem.summary,
                StatementItem.claimed_category_id,
                StatementItem.suggested_category_id,
                StatementItem.direction,
            ).where(StatementItem.status.in_(("claimed", "auto")))
        )
    ).all()
    history: list[dict] = []
    for counterparty, summary, claimed, suggested, direction in rows:
        cat_id = claimed if claimed is not None else suggested
        if cat_id is None:
            continue
        history.append(
            {
                "counterparty": counterparty,
                "summary": summary,
                "category_id": cat_id,
                "direction": direction,
            }
        )
    return history


async def _load_top_categories(session: AsyncSession, direction: str) -> list[tuple[int, int]]:
    """按收支方向统计分类次数，取前 10（'in'→income，'out'→expense）。"""
    tx_type = "income" if direction == "in" else "expense"
    rows = (
        await session.execute(
            select(Transaction.category_id, func.count(Transaction.id))
            .where(Transaction.category_id.is_not(None), Transaction.type == tx_type)
            .group_by(Transaction.category_id)
            .order_by(func.count(Transaction.id).desc())
            .limit(10)
        )
    ).all()
    return [(int(cid), int(cnt)) for cid, cnt in rows if cid is not None]


async def _load_rules(session: AsyncSession) -> list[dict]:
    """加载全部匹配规则（排除已删分类）。"""
    rows = (await session.execute(select(MatchRule))).scalars().all()
    valid_cat_ids = set((await session.execute(select(Category.id))).scalars().all())
    rules: list[dict] = []
    for r in rows:
        if r.category_id not in valid_cat_ids:
            continue
        rules.append(
            {
                "keyword": r.keyword,
                "category_id": r.category_id,
                "direction": r.direction,
                "priority": r.priority,
            }
        )
    return rules


async def _load_account_names(session: AsyncSession) -> dict[int, str]:
    rows = (await session.execute(select(Account.id, Account.name))).all()
    return {int(aid): name for aid, name in rows}


async def _load_category_names(session: AsyncSession) -> dict[int, str]:
    rows = (await session.execute(select(Category.id, Category.name))).all()
    return {int(cid): name for cid, name in rows}


async def _load_category_kinds(session: AsyncSession) -> dict[int, str]:
    rows = (await session.execute(select(Category.id, Category.kind))).all()
    return {int(cid): kind for cid, kind in rows}


def _compute_candidates(
    item: StatementItem,
    history: list[dict],
    top_by_direction: dict[str, list[tuple[int, int]]],
) -> list[StatementCandidate]:
    """为 pending 条目计算候选分类。"""
    raw = matching.suggest_candidates(
        item.counterparty or "",
        item.summary or "",
        item.direction,
        history,
        top_by_direction.get(item.direction, []),
    )
    out: list[StatementCandidate] = []
    for category_id, reason, confidence in raw:
        out.append(
            StatementCandidate(
                category_id=category_id,
                category_name="",
                reason=reason,
                confidence=confidence,
            )
        )
    return out


async def _fill_item_out(
    item: StatementItem,
    category_names: dict[int, str],
    history: list[dict] | None = None,
    top_by_direction: dict[str, list[tuple[int, int]]] | None = None,
) -> StatementItemOut:
    """填充 StatementItemOut 的分类名与候选。"""
    out = StatementItemOut.model_validate(item)
    out.suggested_category_name = category_names.get(item.suggested_category_id) if item.suggested_category_id else None
    out.claimed_category_name = category_names.get(item.claimed_category_id) if item.claimed_category_id else None
    if item.status == "pending" and history is not None and top_by_direction is not None:
        cands = _compute_candidates(item, history, top_by_direction)
        for c in cands:
            c.category_name = category_names.get(c.category_id, "")
        out.candidates = cands
        # 确认时冷启动无候选，列表页重算出候选后把展示口径对齐为"侦探推测"
        if cands and out.match_source == "none":
            out.match_source = "suggestion"
            if out.suggested_category_id is None:
                first = cands[0]
                out.suggested_category_id = first.category_id
                out.suggested_category_name = first.category_name
                out.confidence = first.confidence
    else:
        out.candidates = []
    return out


# ---------------------- 模板相关 ----------------------


@router.post("/api/statements/parse-preview", response_model=ParsePreviewOut)
async def parse_preview(
    file: UploadFile = File(...),
    template_id: int | None = Form(None),
    mapping: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> ParsePreviewOut:
    """解析账单文件预览，不写库。"""
    await ensure_builtin_templates(session)

    raw = await file.read()
    try:
        text, encoding = statement_parser.decode_bytes(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"文件解码失败：{exc}") from exc

    explicit_mapping: dict | None = None
    if mapping:
        try:
            parsed = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="mapping 不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="mapping 必须为对象")
        explicit_mapping = parsed

    template: StatementTemplate | None = None
    if template_id is not None:
        template = await session.get(StatementTemplate, template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="模板不存在")

    # 表头提示：显式 mapping > 模板 mapping > 全部内置并集
    hint: dict = {}
    if explicit_mapping:
        hint = explicit_mapping
    elif template is not None:
        try:
            m = json.loads(template.mapping_json)
            hint = m if isinstance(m, dict) else {}
        except json.JSONDecodeError:
            hint = {}

    headers, data_rows = _extract_table(text, hint)
    resolved = _resolve_mapping(explicit_mapping, template, headers)

    if "date" not in resolved or "amount" not in resolved:
        raise HTTPException(status_code=400, detail="mapping 必须包含 date 和 amount")

    records, errors = statement_parser.apply_mapping(data_rows, resolved)

    auto_name = None if template else _builtin_name_for_mapping(resolved)
    return ParsePreviewOut(
        encoding=encoding,
        headers=headers,
        mapping=resolved,
        template_name=template.name if template else auto_name,
        total_rows=len(records) + len(errors),
        sample=records[:10],
        errors=errors,
    )


@router.post("/api/statements/upload", response_model=UploadOut)
async def upload_statement(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    template_id: int | None = Form(None),
    mapping: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> UploadOut:
    """上传账单文件，创建批次与条目（preview 状态）。"""
    await ensure_builtin_templates(session)

    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账户不存在")

    raw = await file.read()
    try:
        text, _encoding = statement_parser.decode_bytes(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"文件解码失败：{exc}") from exc

    explicit_mapping: dict | None = None
    if mapping:
        try:
            parsed = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="mapping 不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="mapping 必须为对象")
        explicit_mapping = parsed

    template: StatementTemplate | None = None
    if template_id is not None:
        template = await session.get(StatementTemplate, template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="模板不存在")

    hint: dict = {}
    if explicit_mapping:
        hint = explicit_mapping
    elif template is not None:
        try:
            m = json.loads(template.mapping_json)
            hint = m if isinstance(m, dict) else {}
        except json.JSONDecodeError:
            hint = {}

    headers, data_rows = _extract_table(text, hint)
    resolved = _resolve_mapping(explicit_mapping, template, headers)

    if "date" not in resolved or "amount" not in resolved:
        raise HTTPException(status_code=400, detail="mapping 必须包含 date 和 amount")

    records, errors = statement_parser.apply_mapping(data_rows, resolved)

    resolved_template_id = template_id
    if resolved_template_id is None:
        auto_name = _builtin_name_for_mapping(resolved)
        if auto_name:
            resolved_template_id = await _builtin_template_id(session, auto_name)

    batch = StatementBatch(
        filename=file.filename or "",
        template_id=resolved_template_id,
        account_id=account_id,
        status="preview",
        total_count=0,
        auto_count=0,
        pending_count=0,
    )
    session.add(batch)
    await session.flush()

    duplicates_skipped = 0
    seen_fingerprints: set[str] = set()
    existing_fps = set((await session.execute(select(StatementItem.fingerprint))).scalars().all())
    inserted = 0

    for rec in records:
        occurred_on = rec.get("occurred_on")
        counterparty = rec.get("counterparty") or ""
        summary = rec.get("summary") or ""
        amount_cents = rec.get("amount_cents")
        direction = rec.get("direction")
        if occurred_on is None or amount_cents is None or direction not in ("in", "out"):
            errors.append({"row": rec.get("row", -1), "error": "记录缺少必要字段"})
            continue

        fp = matching.fingerprint(occurred_on, int(amount_cents), direction, counterparty, summary)
        if fp in seen_fingerprints or fp in existing_fps:
            duplicates_skipped += 1
            continue

        seen_fingerprints.add(fp)
        item = StatementItem(
            batch_id=batch.id,
            occurred_on=occurred_on,
            counterparty=counterparty,
            summary=summary,
            amount_cents=int(amount_cents),
            direction=direction,
            raw_json=rec.get("raw_json") or "",
            fingerprint=fp,
            status="preview",
        )
        session.add(item)
        inserted += 1

    batch.total_count = inserted
    await session.commit()
    await session.refresh(batch)

    return UploadOut(
        batch=StatementBatchOut.model_validate(batch),
        parsed=inserted,
        errors=errors,
        duplicates_skipped=duplicates_skipped,
    )


@router.get("/api/statement-templates", response_model=list[StatementTemplateOut])
async def list_templates(session: AsyncSession = Depends(get_session)) -> list[StatementTemplateOut]:
    """列出所有账单模板。"""
    await ensure_builtin_templates(session)
    rows = (await session.execute(select(StatementTemplate).order_by(StatementTemplate.id))).scalars().all()
    out: list[StatementTemplateOut] = []
    for t in rows:
        try:
            m = json.loads(t.mapping_json)
            mapping = m if isinstance(m, dict) else {}
        except json.JSONDecodeError:
            mapping = {}
        item = StatementTemplateOut(
            id=t.id,
            name=t.name,
            source=t.source,
            mapping=mapping,
            created_at=t.created_at,
            builtin=t.source != "custom",
        )
        out.append(item)
    return out


@router.post("/api/statement-templates", response_model=StatementTemplateOut, status_code=201)
async def create_template(
    payload: StatementTemplateCreate,
    session: AsyncSession = Depends(get_session),
) -> StatementTemplateOut:
    """创建自定义模板。"""
    existing = (
        await session.execute(select(StatementTemplate).where(StatementTemplate.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="模板名称已存在")

    tpl = StatementTemplate(
        name=payload.name,
        source=payload.source,
        mapping_json=json.dumps(payload.mapping, ensure_ascii=False),
    )
    session.add(tpl)
    await session.commit()
    await session.refresh(tpl)

    return StatementTemplateOut(
        id=tpl.id,
        name=tpl.name,
        source=tpl.source,
        mapping=payload.mapping,
        created_at=tpl.created_at,
        builtin=tpl.source != "custom",
    )


@router.delete("/api/statement-templates/{template_id}")
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """删除自定义模板（内置不可删）。"""
    tpl = await session.get(StatementTemplate, template_id)
    if tpl is None or tpl.source != "custom":
        raise HTTPException(status_code=404, detail="模板不存在")
    await session.delete(tpl)
    await session.commit()
    return {"ok": True}


# ---------------------- 批次与条目 ----------------------


@router.get("/api/statements/batches", response_model=list[StatementBatchOut])
async def list_batches(session: AsyncSession = Depends(get_session)) -> list[StatementBatchOut]:
    """列出所有账单批次（按 id 倒序）。"""
    rows = (await session.execute(select(StatementBatch).order_by(StatementBatch.id.desc()))).scalars().all()
    return [StatementBatchOut.model_validate(b) for b in rows]


@router.get("/api/statements/{batch_id}", response_model=StatementBatchOut)
async def get_batch(batch_id: int, session: AsyncSession = Depends(get_session)) -> StatementBatchOut:
    """获取单个批次。"""
    batch = await session.get(StatementBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return StatementBatchOut.model_validate(batch)


@router.get("/api/statements/{batch_id}/items")
async def list_items(
    batch_id: int,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """列出批次条目，支持状态过滤与分页。"""
    batch = await session.get(StatementBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")

    base = select(StatementItem).where(StatementItem.batch_id == batch_id)
    count_stmt = select(func.count(StatementItem.id)).where(StatementItem.batch_id == batch_id)
    if status:
        base = base.where(StatementItem.status == status)
        count_stmt = count_stmt.where(StatementItem.status == status)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(base.order_by(StatementItem.id).limit(limit).offset(offset))).scalars().all()

    category_names = await _load_category_names(session)

    has_pending = any(r.status == "pending" for r in rows)
    history: list[dict] = []
    top_by_direction: dict[str, list[tuple[int, int]]] = {}
    if has_pending:
        history = await _load_history(session)
        top_by_direction = {
            "in": await _load_top_categories(session, "in"),
            "out": await _load_top_categories(session, "out"),
        }

    items = [await _fill_item_out(r, category_names, history, top_by_direction) for r in rows]
    return {"items": items, "total": int(total)}


@router.delete("/api/statements/{batch_id}")
async def delete_batch(batch_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """删除批次及其所有条目。"""
    batch = await session.get(StatementBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    await session.execute(delete(StatementItem).where(StatementItem.batch_id == batch_id))
    await session.delete(batch)
    await session.commit()
    return {"ok": True}


@router.post("/api/statements/{batch_id}/confirm", response_model=StatementBatchOut)
async def confirm_batch(batch_id: int, session: AsyncSession = Depends(get_session)) -> StatementBatchOut:
    """确认批次：自动分类、匹配历史、计算候选。"""
    batch = await session.get(StatementBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    if batch.status != "preview":
        raise HTTPException(status_code=400, detail="批次状态不允许确认")

    rules = await _load_rules(session)
    account_names = await _load_account_names(session)
    category_kinds = await _load_category_kinds(session)
    history = await _load_history(session)
    top_by_direction = {
        "in": await _load_top_categories(session, "in"),
        "out": await _load_top_categories(session, "out"),
    }

    items = (
        (
            await session.execute(
                select(StatementItem).where(
                    StatementItem.batch_id == batch_id,
                    StatementItem.status == "preview",
                )
            )
        )
        .scalars()
        .all()
    )

    # 收集全部已存在指纹（含其它批次），避免循环查库
    all_fps = set(
        (await session.execute(select(StatementItem.fingerprint).where(StatementItem.batch_id != batch_id)))
        .scalars()
        .all()
    )
    # 本批次内已处理的指纹
    batch_fps = set(
        (
            await session.execute(
                select(StatementItem.fingerprint).where(
                    StatementItem.batch_id == batch_id,
                    StatementItem.status != "preview",
                )
            )
        )
        .scalars()
        .all()
    )

    auto_count = 0
    pending_count = 0

    for item in items:
        # 重复指纹
        if item.fingerprint in all_fps or item.fingerprint in batch_fps:
            item.status = "duplicate"
            continue
        batch_fps.add(item.fingerprint)

        counterparty = item.counterparty or ""
        summary = item.summary or ""
        direction = item.direction

        # 转账检测
        transfer_to = matching.detect_transfer(counterparty, account_names)
        if transfer_to is not None and transfer_to != batch.account_id:
            item.suggested_action = "transfer"
            item.suggested_to_account_id = transfer_to
            item.status = "pending"
            item.match_source = "none"
            pending_count += 1
            continue

        # 规则匹配
        rule_hit = matching.match_by_rules(counterparty, summary, direction, rules)
        matched_category_id: int | None = None
        matched_source: str | None = None
        matched_confidence = 0

        if rule_hit is not None:
            cid = rule_hit[0]
            kind = category_kinds.get(cid)
            if kind is not None and _direction_matches_kind(direction, kind):
                matched_category_id = cid
                matched_source = "rule"
                matched_confidence = 95

        # 历史匹配
        if matched_category_id is None:
            hist_hit = matching.match_by_history(counterparty, summary, direction, history)
            if hist_hit is not None:
                cid, confidence = hist_hit
                kind = category_kinds.get(cid)
                if kind is not None and _direction_matches_kind(direction, kind) and confidence >= 80:
                    matched_category_id = cid
                    matched_source = "history"
                    matched_confidence = confidence

        if matched_category_id is not None:
            tx_type = "income" if direction == "in" else "expense"
            now = utcnow()
            tx = Transaction(
                type=tx_type,
                account_id=batch.account_id,
                to_account_id=None,
                category_id=matched_category_id,
                amount_cents=item.amount_cents,
                occurred_on=item.occurred_on,
                note=_build_note(counterparty, summary),
                created_at=now,
                updated_at=now,
            )
            session.add(tx)
            await session.flush()
            item.status = "auto"
            item.suggested_category_id = matched_category_id
            item.match_source = matched_source
            item.confidence = matched_confidence
            item.transaction_id = tx.id
            item.suggested_action = "categorize"
            auto_count += 1
            continue

        # 候选建议
        raw_candidates = matching.suggest_candidates(
            counterparty, summary, direction, history, top_by_direction.get(direction, [])
        )
        if raw_candidates:
            first = raw_candidates[0]
            item.match_source = "suggestion"
            item.suggested_category_id = first[0]
            item.confidence = first[2]
            item.suggested_action = "categorize"
        else:
            item.match_source = "none"
            item.suggested_category_id = None
            item.confidence = 0
            item.suggested_action = "none"
        item.status = "pending"
        pending_count += 1

    batch.status = "confirmed"
    batch.auto_count = auto_count
    batch.pending_count = pending_count
    batch.total_count = auto_count + pending_count + sum(1 for it in items if it.status in ("duplicate", "skipped"))
    await session.commit()
    await session.refresh(batch)
    return StatementBatchOut.model_validate(batch)


# ---------------------- 条目操作 ----------------------


@router.post("/api/statements/items/{item_id}/claim", response_model=StatementItemOut)
async def claim_item(
    item_id: int,
    payload: ClaimIn,
    session: AsyncSession = Depends(get_session),
) -> StatementItemOut:
    """认领条目并归类。"""
    item = await session.get(StatementItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="条目状态不允许认领")

    category = await session.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    if not _direction_matches_kind(item.direction, category.kind):
        raise HTTPException(status_code=400, detail="分类类型与收支方向不匹配")

    batch = await session.get(StatementBatch, item.batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")

    tx_type = "income" if item.direction == "in" else "expense"
    now = utcnow()
    tx = Transaction(
        type=tx_type,
        account_id=batch.account_id,
        to_account_id=None,
        category_id=payload.category_id,
        amount_cents=item.amount_cents,
        occurred_on=item.occurred_on,
        note=_build_note(item.counterparty or "", item.summary or ""),
        created_at=now,
        updated_at=now,
    )
    session.add(tx)
    await session.flush()

    item.status = "claimed"
    item.claimed_category_id = payload.category_id
    item.transaction_id = tx.id

    if batch.pending_count > 0:
        batch.pending_count -= 1

    if payload.save_rule:
        keyword = (item.counterparty or "").strip() or (item.summary or "").strip()
        if keyword:
            dup = (
                await session.execute(
                    select(MatchRule).where(
                        MatchRule.keyword == keyword,
                        MatchRule.direction == item.direction,
                    )
                )
            ).scalar_one_or_none()
            if dup is not None:
                raise HTTPException(status_code=409, detail="匹配规则已存在")
            session.add(
                MatchRule(
                    keyword=keyword,
                    category_id=payload.category_id,
                    direction=item.direction,
                    priority=0,
                )
            )

    await session.commit()
    await session.refresh(item)

    category_names = await _load_category_names(session)
    return await _fill_item_out(item, category_names)


@router.post("/api/statements/items/{item_id}/claim-transfer", response_model=StatementItemOut)
async def claim_transfer(
    item_id: int,
    payload: ClaimTransferIn,
    session: AsyncSession = Depends(get_session),
) -> StatementItemOut:
    """认领为转账。"""
    item = await session.get(StatementItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="条目状态不允许认领")

    batch = await session.get(StatementBatch, item.batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")

    if payload.to_account_id == batch.account_id:
        raise HTTPException(status_code=400, detail="转入账户不能与账单账户相同")
    to_account = await session.get(Account, payload.to_account_id)
    if to_account is None:
        raise HTTPException(status_code=404, detail="转入账户不存在")

    now = utcnow()
    tx = Transaction(
        type="transfer",
        account_id=batch.account_id,
        to_account_id=payload.to_account_id,
        category_id=None,
        amount_cents=item.amount_cents,
        occurred_on=item.occurred_on,
        note=_build_note(item.counterparty or "", item.summary or ""),
        created_at=now,
        updated_at=now,
    )
    session.add(tx)
    await session.flush()

    item.status = "claimed"
    item.transaction_id = tx.id
    if batch.pending_count > 0:
        batch.pending_count -= 1
    await session.commit()
    await session.refresh(item)

    category_names = await _load_category_names(session)
    return await _fill_item_out(item, category_names)


@router.post("/api/statements/items/{item_id}/skip")
async def skip_item(item_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """跳过条目。"""
    item = await session.get(StatementItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="条目状态不允许跳过")
    item.status = "skipped"
    batch = await session.get(StatementBatch, item.batch_id)
    if batch is not None and batch.pending_count > 0:
        batch.pending_count -= 1
    await session.commit()
    return {"ok": True}


# ---------------------- 匹配规则 ----------------------


@router.get("/api/match-rules", response_model=list[MatchRuleOut])
async def list_match_rules(session: AsyncSession = Depends(get_session)) -> list[MatchRuleOut]:
    """列出所有匹配规则。"""
    rows = (await session.execute(select(MatchRule).order_by(MatchRule.priority.desc(), MatchRule.id))).scalars().all()
    category_names = await _load_category_names(session)
    out: list[MatchRuleOut] = []
    for r in rows:
        out.append(
            MatchRuleOut(
                id=r.id,
                keyword=r.keyword,
                category_id=r.category_id,
                direction=r.direction,
                priority=r.priority,
                created_at=r.created_at,
                category_name=category_names.get(r.category_id, ""),
            )
        )
    return out


@router.post("/api/match-rules", response_model=MatchRuleOut, status_code=201)
async def create_match_rule(
    payload: MatchRuleCreate,
    session: AsyncSession = Depends(get_session),
) -> MatchRuleOut:
    """创建匹配规则。"""
    category = await session.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")

    dup = (
        await session.execute(
            select(MatchRule).where(
                MatchRule.keyword == payload.keyword,
                MatchRule.direction == payload.direction,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail="匹配规则已存在")

    rule = MatchRule(
        keyword=payload.keyword,
        category_id=payload.category_id,
        direction=payload.direction,
        priority=payload.priority,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)

    return MatchRuleOut(
        id=rule.id,
        keyword=rule.keyword,
        category_id=rule.category_id,
        direction=rule.direction,
        priority=rule.priority,
        created_at=rule.created_at,
        category_name=category.name,
    )


@router.delete("/api/match-rules/{rule_id}")
async def delete_match_rule(rule_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """删除匹配规则。"""
    rule = await session.get(MatchRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="匹配规则不存在")
    await session.delete(rule)
    await session.commit()
    return {"ok": True}
