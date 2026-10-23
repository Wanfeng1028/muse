#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import pathlib
import shutil
import sqlite3
import sys


def resolve_db_path(args):
    """Determine the database file path based on --db argument and environment.

    优先级：显式 --db > 环境变量 LEDGER_DB > 默认值（脚本所在项目根下的 data/ledger.db）。
    相对路径按当前工作目录解析（与应用内 LEDGER_DB 行为一致）。
    """
    if args.db:
        return pathlib.Path(args.db)

    env_path = os.getenv("LEDGER_DB")
    if env_path:
        return pathlib.Path(env_path)

    # Default
    project_root = pathlib.Path(__file__).resolve().parent.parent
    return project_root / "data" / "ledger.db"


def pre_checks(conn):
    """Perform pre‑checks required for both dry‑run and real rollback."""
    cur = conn.cursor()
    # user_version must be 6
    cur.execute("PRAGMA user_version")
    uv = cur.fetchone()[0]
    if uv != 6:
        print(f"仅支持从 v6 回滚到 v5，当前 user_version={uv}")
        return False

    # integrity_check must be 'ok'
    cur.execute("PRAGMA integrity_check")
    ic = cur.fetchone()[0]
    if ic != "ok":
        print(f"数据库完整性检查失败: {ic}")
        return False
    return True


def detect_conflicts(conn):
    """Detect all conflicts defined in the spec. Returns a list of conflict dicts."""
    cur = conn.cursor()
    conflicts = []

    # a) report_schemes table row count > 0
    cur.execute("SELECT COUNT(*) FROM report_schemes")
    if cur.fetchone()[0] > 0:
        cur.execute("SELECT rowid, name, scheme_json, updated_at FROM report_schemes")
        for row_id, name, scheme_json, updated_at in cur.fetchall():
            conflicts.append({
                "table": "report_schemes",
                "column": "name",
                "row_id": row_id,
                "value": f"name={name}, scheme_json={scheme_json}, updated_at={updated_at}"
            })

    # b) match_rules columns deviating from expected defaults
    cur.execute("SELECT id, pattern_type, is_enabled, hit_count FROM match_rules")
    for row_id, pattern_type, is_enabled, hit_count in cur.fetchall():
        if pattern_type != "keyword":
            conflicts.append({
                "table": "match_rules",
                "column": "pattern_type",
                "row_id": row_id,
                "value": str(pattern_type)
            })
        if is_enabled != 1:
            conflicts.append({
                "table": "match_rules",
                "column": "is_enabled",
                "row_id": row_id,
                "value": str(is_enabled)
            })
        if hit_count != 0:
            conflicts.append({
                "table": "match_rules",
                "column": "hit_count",
                "row_id": row_id,
                "value": str(hit_count)
            })

    # c) statement_items rows where suggested_rule_id IS NOT NULL
    cur.execute("SELECT rowid, suggested_rule_id FROM statement_items WHERE suggested_rule_id IS NOT NULL")
    for row_id, val in cur.fetchall():
        conflicts.append({
            "table": "statement_items",
            "column": "suggested_rule_id",
            "row_id": row_id,
            "value": str(val)
        })

    # d) duplicate (keyword, direction) pairs in match_rules
    # Get pairs that appear more than once
    cur.execute("SELECT keyword, direction FROM match_rules GROUP BY keyword, direction HAVING COUNT(*) > 1")
    duplicate_pairs = cur.fetchall()
    for keyword, direction in duplicate_pairs:
        # Fetch all ids for this pair
        cur.execute("SELECT id FROM match_rules WHERE keyword = ? AND direction = ? ORDER BY id", (keyword, direction))
        ids = [r[0] for r in cur.fetchall()]
        # Every row beyond the first is a conflict
        for dup_id in ids[1:]:
            conflicts.append({
                "table": "match_rules",
                "column": "keyword",
                "row_id": dup_id,
                "value": f"keyword={keyword}, direction={direction}"
            })

    return conflicts


def write_conflicts_json(conflicts, db_path):
    json_path = db_path.parent / ".rollback_conflicts.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(conflicts, f, ensure_ascii=False, indent=2)
    return json_path


def print_dry_run_steps(db_path, backup_path):
    print("DRY-RUN: 将执行以下操作：")
    print("- 检查数据库文件是否存在")
    print("- 检查 PRAGMA user_version == 6")
    print("- 检查数据库完整性")
    print("- 创建 match_rules_v5_tmp 表")
    print("- 复制 match_rules 数据")
    print("- 删除旧 match_rules 表")
    print("- 重命名 match_rules_v5_tmp 为 match_rules")
    print("- 创建 statement_items_v5_tmp 表")
    print("- 复制 statement_items 数据")
    print("- 删除旧 statement_items 表")
    print("- 重命名 statement_items_v5_tmp 为 statement_items")
    print("- 删除 report_schemes 表")
    print("- 设置 PRAGMA user_version = 5")
    print("- 回滚事务并提交")
    print(f"- 将创建备份文件: {backup_path}")
    print("中止：仅为干跑模式，跳过实际写入")


def build_statement_items_table_sql(conn):
    """Generate column definitions for statement_items_v5_tmp, excluding suggested_rule_id."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info('statement_items')")
    columns = []
    for cid, name, col_type, notnull, dflt_value, pk in cur.fetchall():
        if name == "suggested_rule_id":
            continue
        if name == "id" and pk:
            # Preserve AUTOINCREMENT for the primary key
            columns.append(f"{name} {col_type} PRIMARY KEY AUTOINCREMENT")
            continue
        parts = [f"{name} {col_type}"]
        if notnull:
            parts.append("NOT NULL")
        if dflt_value is not None:
            parts.append(f"DEFAULT {dflt_value}")
        if pk:
            parts.append("PRIMARY KEY")
        columns.append(" ".join(parts))
    return ", ".join(columns)


def main():
    parser = argparse.ArgumentParser(description="回滚 ledger 数据库从 v6 到 v5")
    parser.add_argument("--db", help="数据库文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅打印操作，不修改数据库")
    parser.add_argument("--yes", action="store_true", help="确认执行回滚")
    args = parser.parse_args()

    # Validate mutually exclusive flags
    if args.dry_run and args.yes:
        print("--dry-run 与 --yes 互斥")
        sys.exit(2)

    db_path = resolve_db_path(args)

    # File existence check
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        sys.exit(2)
    conn = sqlite3.connect(db_path)
    if not pre_checks(conn):
        conn.close()
        sys.exit(2)
    conflicts = detect_conflicts(conn)
    if conflicts:
        json_path = write_conflicts_json(conflicts, db_path)
        print(f"发现 {len(conflicts)} 个冲突，回滚中止，冲突清单已写入 {json_path}")
        conn.close()
        sys.exit(3)
    conn.close()
    if not args.yes:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_preview = db_path.parent / "backups" / ("ledger-" + ts + ".pre-rollback.sqlite3")
        print_dry_run_steps(db_path, backup_preview)
        print("冲突检查通过：0 个冲突")
        sys.exit(0)
    backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backups_dir / ("ledger-" + ts + ".pre-rollback.sqlite3")
    shutil.copy2(db_path, backup_path)
    print(f"已创建备份: {backup_path}")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE match_rules_v5_tmp (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "keyword TEXT NOT NULL, category_id INTEGER NOT NULL REFERENCES categories(id), "
            "direction TEXT NOT NULL DEFAULT 'any', priority INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL, "
            "CONSTRAINT uq_match_rules_keyword_direction UNIQUE (keyword, direction))"
        )
        conn.execute(
            "INSERT INTO match_rules_v5_tmp "
            "(id, keyword, category_id, direction, priority, created_at) "
            "SELECT id, keyword, category_id, direction, priority, created_at FROM match_rules"
        )
        conn.execute("DROP TABLE match_rules")
        conn.execute("ALTER TABLE match_rules_v5_tmp RENAME TO match_rules")
        cols_sql = build_statement_items_table_sql(conn)
        conn.execute(
            "CREATE TABLE statement_items_v5_tmp (" + cols_sql + ", "
            "CONSTRAINT uq_statement_items_fingerprint UNIQUE (fingerprint), "
            "CONSTRAINT ck_statement_items_amount_positive CHECK (amount_cents > 0))"
        )
        cur2 = conn.execute("PRAGMA table_info('statement_items_v5_tmp')")
        col_names = [r[1] for r in cur2.fetchall()]
        collist = ", ".join(col_names)
        conn.execute("INSERT INTO statement_items_v5_tmp (" + collist + ") SELECT " + collist + " FROM statement_items")
        conn.execute("DROP TABLE statement_items")
        conn.execute("ALTER TABLE statement_items_v5_tmp RENAME TO statement_items")
        conn.execute("DROP TABLE IF EXISTS report_schemes")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
        print("回滚完成：v6 -> v5")
        print(f"备份保留在: {backup_path}，如需恢复请手动复制覆盖")
    except Exception as e:
        conn.rollback()
        print(f"回滚失败，已回滚事务：{e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
