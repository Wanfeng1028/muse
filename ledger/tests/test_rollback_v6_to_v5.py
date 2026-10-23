"""v6 -> v5 回滚脚本测试：dry-run、前置检查、冲突检测。"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rollback_v6_to_v5.py"

DDL_MATCH_RULES = (
    "CREATE TABLE match_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "keyword TEXT NOT NULL, category_id INTEGER NOT NULL, "
    "direction TEXT NOT NULL DEFAULT 'any', priority INTEGER NOT NULL DEFAULT 0, "
    "created_at TEXT NOT NULL, pattern_type TEXT NOT NULL, "
    "is_enabled INTEGER NOT NULL, hit_count INTEGER NOT NULL, "
    "CONSTRAINT uq_match_rules_keyword_ptype_direction UNIQUE (keyword, pattern_type, direction))"
)
DDL_ITEMS = (
    "CREATE TABLE statement_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "batch_id INTEGER NOT NULL, occurred_on TEXT NOT NULL, counterparty TEXT NOT NULL, "
    "summary TEXT NOT NULL, amount_cents INTEGER NOT NULL, direction TEXT NOT NULL, "
    "raw_json TEXT NOT NULL, fingerprint TEXT NOT NULL, match_source TEXT NOT NULL, "
    "confidence INTEGER NOT NULL, suggested_action TEXT NOT NULL, "
    "suggested_rule_id INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL, "
    "CONSTRAINT uq_statement_items_fingerprint UNIQUE (fingerprint))"
)
DDL_SCHEMES = (
    "CREATE TABLE report_schemes (name TEXT PRIMARY KEY, "
    "scheme_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL)"
)


def make_v6_db(path: Path, user_version: int = 6) -> Path:
    """建最小 v6 库：三表 + user_version。"""
    conn = sqlite3.connect(path)
    conn.execute(DDL_MATCH_RULES)
    conn.execute(DDL_ITEMS)
    conn.execute(DDL_SCHEMES)
    conn.execute(f"PRAGMA user_version = {user_version}")
    conn.commit()
    conn.close()
    return path


def run_script(db: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), *flags],
        capture_output=True, text=True, timeout=60,
    )


def user_version(db: Path) -> int:
    conn = sqlite3.connect(db)
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return uv


def add_rule(db: Path, keyword="k1", pattern_type="keyword", is_enabled=1, hit_count=0):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO match_rules (keyword, category_id, direction, priority, created_at, "
        "pattern_type, is_enabled, hit_count) VALUES (?,?,?,?,?,?,?,?)",
        (keyword, 1, "out", 0, "2026-10-24", pattern_type, is_enabled, hit_count),
    )
    conn.commit()
    conn.close()


def test_dry_run_clean_no_writes(tmp_path):
    """干净 v6 库默认 dry-run：exit 0、stdout 含 DRY-RUN、不写库、无 backups 目录。"""
    db = make_v6_db(tmp_path / "t.db")
    add_rule(db)
    r = run_script(db)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRY-RUN" in r.stdout
    assert user_version(db) == 6
    assert not (db.parent / "backups").exists()


def test_dry_run_flag_explicit(tmp_path):
    """显式 --dry-run 同默认行为。"""
    db = make_v6_db(tmp_path / "t.db")
    r = run_script(db, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRY-RUN" in r.stdout
    assert user_version(db) == 6


def test_mutually_exclusive_flags(tmp_path):
    """--dry-run 与 --yes 互斥：exit 2。"""
    db = make_v6_db(tmp_path / "t.db")
    r = run_script(db, "--dry-run", "--yes")
    assert r.returncode == 2, r.stdout + r.stderr


def test_reject_non_v6(tmp_path):
    """user_version != 6 拒绝：exit 2 且输出含 user_version。"""
    db = make_v6_db(tmp_path / "t.db", user_version=0)
    r = run_script(db, "--dry-run")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "user_version" in r.stdout


def test_db_flag_beats_env_var(tmp_path, monkeypatch):
    """显式 --db 优先级高于 LEDGER_DB 环境变量（全量套件 conftest 会设置该变量）。"""
    real_db = make_v6_db(tmp_path / "real.db")
    decoy = make_v6_db(tmp_path / "decoy.db", user_version=0)
    monkeypatch.setenv("LEDGER_DB", str(decoy))
    r = run_script(real_db, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRY-RUN" in r.stdout
    assert user_version(real_db) == 6
    assert user_version(decoy) == 0


def test_missing_file(tmp_path):
    """数据库文件不存在：exit 2 且输出含 不存在。"""
    db = tmp_path / "nope.db"
    r = run_script(db, "--dry-run")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "不存在" in r.stdout


def _conflict_json(db: Path):
    p = db.parent / ".rollback_conflicts.json"
    assert p.exists(), "冲突 JSON 未生成"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "冲突清单应为非空数组"
    for item in data:
        assert set(item.keys()) == {"table", "column", "row_id", "value"}, item
    return data


def test_conflict_regex_rule(tmp_path):
    """pattern_type='regex' 的规则是冲突：--yes 也 exit 3，冲突 JSON 四键齐全，库未被写入。"""
    db = make_v6_db(tmp_path / "t.db")
    add_rule(db, keyword="rx", pattern_type="regex", hit_count=5)
    r = run_script(db, "--yes")
    assert r.returncode == 3, r.stdout + r.stderr
    data = _conflict_json(db)
    assert any(d["table"] == "match_rules" and d["column"] == "pattern_type" for d in data)
    assert user_version(db) == 6


def test_conflict_report_schemes_nonempty(tmp_path):
    """report_schemes 非空是冲突：exit 3。"""
    db = make_v6_db(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO report_schemes (name, scheme_json, updated_at) VALUES ('s1', '{}', '2026-10-24')")
    conn.commit()
    conn.close()
    r = run_script(db, "--yes")
    assert r.returncode == 3, r.stdout + r.stderr
    data = _conflict_json(db)
    assert any(d["table"] == "report_schemes" for d in data)
    assert user_version(db) == 6


def test_conflict_suggested_rule_id(tmp_path):
    """statement_items.suggested_rule_id 非空是冲突：exit 3。"""
    db = make_v6_db(tmp_path / "t.db")
    add_rule(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO statement_items (batch_id, occurred_on, counterparty, summary, amount_cents, "
        "direction, raw_json, fingerprint, match_source, confidence, suggested_action, "
        "suggested_rule_id, status, created_at) VALUES "
        "(1,'2026-10-01','星巴克','咖啡',3500,'out','{}','fp-1','rule_keyword',95,'categorize',1,'pending','2026-10-24')"
    )
    conn.commit()
    conn.close()
    r = run_script(db, "--yes")
    assert r.returncode == 3, r.stdout + r.stderr
    data = _conflict_json(db)
    assert any(d["table"] == "statement_items" and d["column"] == "suggested_rule_id" for d in data)
    assert user_version(db) == 6


def test_conflict_duplicate_keyword_direction(tmp_path):
    """(keyword, direction) 重复组是冲突：exit 3。"""
    db = make_v6_db(tmp_path / "t.db")
    add_rule(db, keyword="dup", pattern_type="keyword")
    add_rule(db, keyword="dup", pattern_type="regex")
    r = run_script(db, "--yes")
    assert r.returncode == 3, r.stdout + r.stderr
    assert user_version(db) == 6


def test_real_rollback_happy_path(tmp_path):
    """--yes 真实回滚：exit 0，schema 精确回到 v5，数据保留，备份文件存在。"""
    db = make_v6_db(tmp_path / "t.db")
    add_rule(db, keyword="星巴克")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO statement_items (batch_id, occurred_on, counterparty, summary, amount_cents, "
        "direction, raw_json, fingerprint, match_source, confidence, suggested_action, "
        "status, created_at) VALUES "
        "(1,'2026-10-01','星巴克','咖啡',3500,'out','{}','fp-1','rule_keyword',95,'categorize','pending','2026-10-24')"
    )
    conn.commit()
    conn.close()
    r = run_script(db, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert user_version(db) == 5
    conn = sqlite3.connect(db)
    rule_cols = [row[1] for row in conn.execute("PRAGMA table_info(match_rules)").fetchall()]
    assert rule_cols == ["id", "keyword", "category_id", "direction", "priority", "created_at"], rule_cols
    item_cols = [row[1] for row in conn.execute("PRAGMA table_info(statement_items)").fetchall()]
    assert "suggested_rule_id" not in item_cols, item_cols
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='report_schemes'").fetchone()[0] == 0
    assert conn.execute("SELECT keyword FROM match_rules").fetchall() == [("星巴克",)]
    assert conn.execute("SELECT counterparty, amount_cents FROM statement_items").fetchall() == [("星巴克", 3500)]
    conn.close()
    backups = list((db.parent / "backups").glob("*.pre-rollback.sqlite3"))
    assert len(backups) == 1, backups
