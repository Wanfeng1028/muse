package store

import (
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	_ "modernc.org/sqlite"

	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
)

// ErrNotFound 表示查询的记录不存在。
var ErrNotFound = errors.New("not found")

// Store 封装数据库连接。
type Store struct {
	DB *sql.DB
}

// dbtx 是 *sql.DB 与 *sql.Tx 的公共子集，供同步批量事务使用。
// 批量同步时传入 *sql.Tx，普通调用传入 Store.DB。
type dbtx interface {
	Exec(query string, args ...any) (sql.Result, error)
	Query(query string, args ...any) (*sql.Rows, error)
	QueryRow(query string, args ...any) *sql.Row
}

// Open 打开数据库。":memory:" 走内存库；文件库先建父目录。
func Open(path string) (*Store, error) {
	if path == "" {
		path = ":memory:"
	}
	isMemory := path == ":memory:"
	if !isMemory {
		dir := filepath.Dir(path)
		if dir != "" && dir != "." {
			if err := os.MkdirAll(dir, 0o755); err != nil {
				return nil, fmt.Errorf("创建数据库目录失败: %w", err)
			}
		}
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("打开数据库失败: %w", err)
	}
	if !isMemory {
		if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
			db.Close()
			return nil, fmt.Errorf("设置 WAL 失败: %w", err)
		}
	}
	if _, err := db.Exec("PRAGMA foreign_keys=ON"); err != nil {
		db.Close()
		return nil, fmt.Errorf("开启外键失败: %w", err)
	}
	return &Store{DB: db}, nil
}

// Close 关闭数据库。
func (s *Store) Close() error {
	return s.DB.Close()
}

// Migrate 建立内部管理表。
func (s *Store) Migrate() error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS "_m_runs" (
			"id" INTEGER PRIMARY KEY AUTOINCREMENT,
			"job" TEXT,
			"started_at" TEXT,
			"finished_at" TEXT,
			"inserted" INTEGER,
			"updated" INTEGER,
			"deleted" INTEGER,
			"conflicts" INTEGER,
			"error" TEXT
		)`,
		`CREATE TABLE IF NOT EXISTS "_m_conflicts" (
			"id" INTEGER PRIMARY KEY AUTOINCREMENT,
			"table_name" TEXT,
			"pk" TEXT,
			"source_a" TEXT,
			"source_b" TEXT,
			"row_json" TEXT,
			"status" TEXT DEFAULT 'pending',
			"created_at" TEXT,
			"resolved_at" TEXT
		)`,
		`CREATE TABLE IF NOT EXISTS "_m_views" (
			"name" TEXT PRIMARY KEY,
			"sql" TEXT,
			"description" TEXT,
			"created_at" TEXT,
			"origin" TEXT NOT NULL DEFAULT 'manual',
			"materialized" INTEGER NOT NULL DEFAULT 0,
			"refresh_policy" TEXT NOT NULL DEFAULT '',
			"last_refresh_at" TEXT,
			"last_refresh_rows" INTEGER NOT NULL DEFAULT 0
		)`,

		`CREATE TABLE IF NOT EXISTS "_m_watermarks" (
			"source" TEXT,
			"table_name" TEXT,
			"column_name" TEXT,
			"value" TEXT,
			PRIMARY KEY("source","table_name","column_name")
		)`,
		`CREATE TABLE IF NOT EXISTS "_m_imports" (
			"id" INTEGER PRIMARY KEY AUTOINCREMENT,
			"source" TEXT NOT NULL,
			"file_hash" TEXT NOT NULL UNIQUE,
			"filename" TEXT NOT NULL DEFAULT '',
			"rows_total" INTEGER NOT NULL DEFAULT 0,
			"inserted" INTEGER NOT NULL DEFAULT 0,
			"updated" INTEGER NOT NULL DEFAULT 0,
			"error_rows" INTEGER NOT NULL DEFAULT 0,
			"created_at" TEXT NOT NULL
		)`,
	}
	for _, stmt := range stmts {
		if _, err := s.DB.Exec(stmt); err != nil {
			return fmt.Errorf("建表失败: %w", err)
		}
	}
	// v1.2/v1.3 兼容迁移：老库的 "_m_views" 表可能缺少部分列，
	// 通过 PRAGMA table_info 检查，缺失时补加（幂等，已存在则跳过）。
	existingCols := make(map[string]bool)
	rows, err := s.DB.Query(`PRAGMA table_info("_m_views")`)
	if err != nil {
		return fmt.Errorf("检查视图表结构失败: %w", err)
	}
	for rows.Next() {
		var cid int
		var name, colType string
		var notNull, pk int
		var dfltValue sql.NullString
		if err := rows.Scan(&cid, &name, &colType, &notNull, &dfltValue, &pk); err != nil {
			rows.Close()
			return fmt.Errorf("扫描视图表结构失败: %w", err)
		}
		existingCols[name] = true
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return fmt.Errorf("遍历视图表结构失败: %w", err)
	}
	rows.Close()
	// 待补列定义：列名、ADD COLUMN 语句、失败文案。
	migrations := []struct {
		column string
		stmt   string
		errMsg string
	}{
		{"origin", `ALTER TABLE "_m_views" ADD COLUMN "origin" TEXT NOT NULL DEFAULT 'manual'`, "迁移视图表 origin 列失败: %w"},
		{"materialized", `ALTER TABLE "_m_views" ADD COLUMN "materialized" INTEGER NOT NULL DEFAULT 0`, "迁移视图表 materialized 列失败: %w"},
		{"refresh_policy", `ALTER TABLE "_m_views" ADD COLUMN "refresh_policy" TEXT NOT NULL DEFAULT ''`, "迁移视图表 refresh_policy 列失败: %w"},
		{"last_refresh_at", `ALTER TABLE "_m_views" ADD COLUMN "last_refresh_at" TEXT`, "迁移视图表 last_refresh_at 列失败: %w"},
		{"last_refresh_rows", `ALTER TABLE "_m_views" ADD COLUMN "last_refresh_rows" INTEGER NOT NULL DEFAULT 0`, "迁移视图表 last_refresh_rows 列失败: %w"},
	}
	for _, m := range migrations {
		if existingCols[m.column] {
			continue
		}
		if _, err := s.DB.Exec(m.stmt); err != nil {
			return fmt.Errorf(m.errMsg, err)
		}
	}
	return nil
}

// quoteIdent 用双引号转义标识符。
func quoteIdent(name string) string {
	return `"` + strings.ReplaceAll(name, `"`, `""`) + `"`
}

// EnsureTable 确保目标表存在并追加内部列；pkCol 非空时将其声明为 PRIMARY KEY。
func (s *Store) EnsureTable(table, pkCol string, cols []infer.Column) error {
	var b strings.Builder
	b.WriteString("CREATE TABLE IF NOT EXISTS ")
	b.WriteString(quoteIdent(table))
	b.WriteString(" (")
	for i, c := range cols {
		if i > 0 {
			b.WriteString(", ")
		}
		b.WriteString(quoteIdent(c.Name))
		b.WriteString(" ")
		b.WriteString(infer.SQLiteType(c.Type))
		if pkCol != "" && c.Name == pkCol {
			b.WriteString(" PRIMARY KEY")
		}
	}
	b.WriteString(", ")
	b.WriteString(quoteIdent("_m_hash"))
	b.WriteString(" TEXT, ")
	b.WriteString(quoteIdent("_m_source"))
	b.WriteString(" TEXT, ")
	b.WriteString(quoteIdent("_m_synced_at"))
	b.WriteString(" TEXT, ")
	b.WriteString(quoteIdent("_m_deleted"))
	b.WriteString(" INTEGER NOT NULL DEFAULT 0)")
	if _, err := s.DB.Exec(b.String()); err != nil {
		return fmt.Errorf("确保表 %s 存在失败: %w", table, err)
	}
	return nil
}

// UpsertRow 插入或更新一行（按主键冲突）。
func (s *Store) UpsertRow(q dbtx, table, pkCol string, pkVal any, cols []string, vals []any, hash, source string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	allCols := make([]string, 0, len(cols)+4)
	allCols = append(allCols, cols...)
	allCols = append(allCols, "_m_hash", "_m_source", "_m_synced_at", "_m_deleted")
	allVals := make([]any, 0, len(vals)+4)
	allVals = append(allVals, vals...)
	allVals = append(allVals, hash, source, now, 0)

	placeholders := make([]string, len(allCols))
	for i := range allCols {
		placeholders[i] = "?"
	}

	quoted := make([]string, len(allCols))
	for i, c := range allCols {
		quoted[i] = quoteIdent(c)
	}

	var updates []string
	for _, c := range allCols {
		updates = append(updates, quoteIdent(c)+"=excluded."+quoteIdent(c))
	}

	stmt := fmt.Sprintf(
		"INSERT INTO %s (%s) VALUES (%s) ON CONFLICT(%s) DO UPDATE SET %s",
		quoteIdent(table),
		strings.Join(quoted, ", "),
		strings.Join(placeholders, ", "),
		quoteIdent(pkCol),
		strings.Join(updates, ", "),
	)
	if _, err := q.Exec(stmt, allVals...); err != nil {
		return fmt.Errorf("写入行失败: %w", err)
	}
	return nil
}

// GetHash 读取指定主键行的 hash、来源与删除标记。
func (s *Store) GetHash(q dbtx, table, pkCol string, pkVal any) (hash, source string, deleted bool, found bool, err error) {
	stmt := fmt.Sprintf(
		"SELECT %s, %s, %s FROM %s WHERE %s = ?",
		quoteIdent("_m_hash"), quoteIdent("_m_source"), quoteIdent("_m_deleted"),
		quoteIdent(table), quoteIdent(pkCol),
	)
	var (
		h   sql.NullString
		src sql.NullString
		del sql.NullInt64
	)
	row := q.QueryRow(stmt, pkVal)
	if err := row.Scan(&h, &src, &del); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return "", "", false, false, nil
		}
		return "", "", false, false, fmt.Errorf("读取 hash 失败: %w", err)
	}
	return h.String, src.String, del.Int64 != 0, true, nil
}

// ExistingPKs 返回表中所有主键（字符串化）。
func (s *Store) ExistingPKs(table, pkCol, source string) (map[string]bool, error) {
	stmt := fmt.Sprintf("SELECT %s FROM %s WHERE %s = ?", quoteIdent(pkCol), quoteIdent(table), quoteIdent("_m_source"))
	rows, err := s.DB.Query(stmt, source)
	if err != nil {
		return nil, fmt.Errorf("查询主键失败: %w", err)
	}
	defer rows.Close()
	result := make(map[string]bool)
	for rows.Next() {
		var v any
		if err := rows.Scan(&v); err != nil {
			return nil, fmt.Errorf("扫描主键失败: %w", err)
		}
		result[infer.Stringify(v)] = true
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历主键失败: %w", err)
	}
	return result, nil
}

// MarkDeleted 标记软删除。
func (s *Store) MarkDeleted(q dbtx, table, pkCol string, pkVal any) error {
	stmt := fmt.Sprintf("UPDATE %s SET %s = 1 WHERE %s = ?", quoteIdent(table), quoteIdent("_m_deleted"), quoteIdent(pkCol))
	if _, err := q.Exec(stmt, pkVal); err != nil {
		return fmt.Errorf("软删除失败: %w", err)
	}
	return nil
}

// DeleteRow 物理删除一行。
func (s *Store) DeleteRow(q dbtx, table, pkCol string, pkVal any) error {
	stmt := fmt.Sprintf("DELETE FROM %s WHERE %s = ?", quoteIdent(table), quoteIdent(pkCol))
	if _, err := q.Exec(stmt, pkVal); err != nil {
		return fmt.Errorf("删除失败: %w", err)
	}
	return nil
}

// GetWatermark 读取水位线，不存在返回空串。
func (s *Store) GetWatermark(source, table, column string) (string, error) {
	var value sql.NullString
	err := s.DB.QueryRow(
		`SELECT "value" FROM "_m_watermarks" WHERE "source"=? AND "table_name"=? AND "column_name"=?`,
		source, table, column,
	).Scan(&value)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return "", nil
		}
		return "", fmt.Errorf("读取水位线失败: %w", err)
	}
	return value.String, nil
}

// SetWatermark 写入水位线。
func (s *Store) SetWatermark(source, table, column, value string) error {
	_, err := s.DB.Exec(
		`INSERT INTO "_m_watermarks" ("source","table_name","column_name","value") VALUES (?,?,?,?)
		 ON CONFLICT("source","table_name","column_name") DO UPDATE SET "value"=excluded."value"`,
		source, table, column, value,
	)
	if err != nil {
		return fmt.Errorf("写入水位线失败: %w", err)
	}
	return nil
}

// ListWatermarks 列出所有水位线（source、table、column、value）。
func (s *Store) ListWatermarks() ([]Watermark, error) {
	rows, err := s.DB.Query(
		`SELECT "source","table_name","column_name","value" FROM "_m_watermarks" ORDER BY "source","table_name","column_name"`,
	)
	if err != nil {
		return nil, fmt.Errorf("查询水位线失败: %w", err)
	}
	defer rows.Close()
	var result []Watermark
	for rows.Next() {
		var w Watermark
		var src, tbl, col, val sql.NullString
		if err := rows.Scan(&src, &tbl, &col, &val); err != nil {
			return nil, fmt.Errorf("扫描水位线失败: %w", err)
		}
		w.Source = src.String
		w.Table = tbl.String
		w.Column = col.String
		w.Value = val.String
		result = append(result, w)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历水位线失败: %w", err)
	}
	return result, nil
}

// Watermark 表示一条水位线记录。
type Watermark struct {
	Source string
	Table  string
	Column string
	Value  string
}

// RunRecord 表示一次同步运行的记录。
type RunRecord struct {
	ID         int64  `json:"id"`
	Job        string `json:"job"`
	StartedAt  string `json:"started_at"`
	FinishedAt string `json:"finished_at"`
	Inserted   int    `json:"inserted"`
	Updated    int    `json:"updated"`
	Deleted    int    `json:"deleted"`
	Conflicts  int    `json:"conflicts"`
	Error      string `json:"error"`
}

// RecordRun 记录一次运行。
func (s *Store) RecordRun(r RunRecord) error {
	_, err := s.DB.Exec(
		`INSERT INTO "_m_runs" ("job","started_at","finished_at","inserted","updated","deleted","conflicts","error")
		 VALUES (?,?,?,?,?,?,?,?)`,
		r.Job, r.StartedAt, r.FinishedAt, r.Inserted, r.Updated, r.Deleted, r.Conflicts, r.Error,
	)
	if err != nil {
		return fmt.Errorf("记录运行失败: %w", err)
	}
	return nil
}

// ListRuns 按 id 倒序列出运行记录。
func (s *Store) ListRuns(limit int) ([]RunRecord, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := s.DB.Query(
		`SELECT "id","job","started_at","finished_at","inserted","updated","deleted","conflicts","error"
		 FROM "_m_runs" ORDER BY "id" DESC LIMIT ?`, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("查询运行记录失败: %w", err)
	}
	defer rows.Close()
	var result []RunRecord
	for rows.Next() {
		var r RunRecord
		var started, finished, jobName, errStr sql.NullString
		var inserted, updated, deleted, conflicts sql.NullInt64
		if err := rows.Scan(&r.ID, &jobName, &started, &finished, &inserted, &updated, &deleted, &conflicts, &errStr); err != nil {
			return nil, fmt.Errorf("扫描运行记录失败: %w", err)
		}
		r.Job = jobName.String
		r.StartedAt = started.String
		r.FinishedAt = finished.String
		r.Inserted = int(inserted.Int64)
		r.Updated = int(updated.Int64)
		r.Deleted = int(deleted.Int64)
		r.Conflicts = int(conflicts.Int64)
		r.Error = errStr.String
		result = append(result, r)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历运行记录失败: %w", err)
	}
	return result, nil
}

// Conflict 表示一条冲突记录。
type Conflict struct {
	ID         int64  `json:"id"`
	TableName  string `json:"table_name"`
	PK         string `json:"pk"`
	SourceA    string `json:"source_a"`
	SourceB    string `json:"source_b"`
	RowJSON    string `json:"row_json"`
	Status     string `json:"status"`
	CreatedAt  string `json:"created_at"`
	ResolvedAt string `json:"resolved_at"`
}

// RecordConflict 记录一条冲突，返回新 id。
func (s *Store) RecordConflict(q dbtx, c Conflict) (int64, error) {
	res, err := q.Exec(
		`INSERT INTO "_m_conflicts" ("table_name","pk","source_a","source_b","row_json","status","created_at","resolved_at")
		 VALUES (?,?,?,?,?,?,?,?)`,
		c.TableName, c.PK, c.SourceA, c.SourceB, c.RowJSON, c.Status, c.CreatedAt, c.ResolvedAt,
	)
	if err != nil {
		return 0, fmt.Errorf("记录冲突失败: %w", err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("获取冲突 id 失败: %w", err)
	}
	// 累计冲突计数（CLI 与 API 双路径覆盖）
	metrics.Default().Inc("mortise_conflicts_total")
	return id, nil
}

// ListConflicts 列出冲突，status 为空则查全部。
func (s *Store) ListConflicts(status string) ([]Conflict, error) {
	var (
		rows *sql.Rows
		err  error
	)
	if status == "" {
		rows, err = s.DB.Query(
			`SELECT "id","table_name","pk","source_a","source_b","row_json","status","created_at","resolved_at"
			 FROM "_m_conflicts" ORDER BY "id" DESC`,
		)
	} else {
		rows, err = s.DB.Query(
			`SELECT "id","table_name","pk","source_a","source_b","row_json","status","created_at","resolved_at"
			 FROM "_m_conflicts" WHERE "status"=? ORDER BY "id" DESC`, status,
		)
	}
	if err != nil {
		return nil, fmt.Errorf("查询冲突失败: %w", err)
	}
	defer rows.Close()
	var result []Conflict
	for rows.Next() {
		var c Conflict
		var tableName, pk, sa, sb, rj, st, ca, ra sql.NullString
		if err := rows.Scan(&c.ID, &tableName, &pk, &sa, &sb, &rj, &st, &ca, &ra); err != nil {
			return nil, fmt.Errorf("扫描冲突失败: %w", err)
		}
		c.TableName = tableName.String
		c.PK = pk.String
		c.SourceA = sa.String
		c.SourceB = sb.String
		c.RowJSON = rj.String
		c.Status = st.String
		c.CreatedAt = ca.String
		c.ResolvedAt = ra.String
		result = append(result, c)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历冲突失败: %w", err)
	}
	return result, nil
}

// ResolveConflict 更新冲突状态并写入解决时间。
func (s *Store) ResolveConflict(id int64, status string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := s.DB.Exec(
		`UPDATE "_m_conflicts" SET "status"=?, "resolved_at"=? WHERE "id"=?`,
		status, now, id,
	)
	if err != nil {
		return fmt.Errorf("解决冲突失败: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("获取影响行数失败: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// ResolveConflictsByPK 将指定表+主键的所有 pending 冲突标记为目标状态，返回影响行数。
func (s *Store) ResolveConflictsByPK(q dbtx, table, pk, status string) (int64, error) {
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := q.Exec(
		`UPDATE "_m_conflicts" SET "status"=?, "resolved_at"=? WHERE "table_name"=? AND "pk"=? AND "status"='pending'`,
		status, now, table, pk,
	)
	if err != nil {
		return 0, fmt.Errorf("按主键解决冲突失败: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("获取影响行数失败: %w", err)
	}
	return n, nil
}

// View 表示一个视图定义。
type View struct {
	Name            string `json:"name"`
	SQL             string `json:"sql"`
	Description     string `json:"description"`
	CreatedAt       string `json:"created_at"`
	Origin          string `json:"origin"`
	Materialized    bool   `json:"materialized"`
	RefreshPolicy   string `json:"refresh_policy"`
	LastRefreshAt   string `json:"last_refresh_at"`
	LastRefreshRows int64  `json:"last_refresh_rows"`
}

// SaveView 保存或更新视图定义。
func (s *Store) SaveView(name, sqlStr, desc string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.DB.Exec(
		`INSERT INTO "_m_views" ("name","sql","description","created_at","origin") VALUES (?,?,?,?,'manual')
		 ON CONFLICT("name") DO UPDATE SET "sql"=excluded."sql", "description"=excluded."description"`,
		name, sqlStr, desc, now,
	)
	if err != nil {
		return fmt.Errorf("保存视图失败: %w", err)
	}
	return nil
}

// SaveYAMLView 保存或更新来自 YAML 声明的视图定义，origin 标记为 yaml。
// 同名手工视图被 YAML 声明覆盖时，origin 转为 yaml 是预期行为。
func (s *Store) SaveYAMLView(name, sqlStr, desc string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.DB.Exec(
		`INSERT INTO "_m_views" ("name","sql","description","created_at","origin") VALUES (?,?,?,?,'yaml')
		 ON CONFLICT("name") DO UPDATE SET "sql"=excluded."sql", "description"=excluded."description", "origin"=excluded."origin"`,
		name, sqlStr, desc, now,
	)
	if err != nil {
		return fmt.Errorf("保存 YAML 视图失败: %w", err)
	}
	return nil
}

// ListViews 列出所有视图。
func (s *Store) ListViews() ([]View, error) {
	rows, err := s.DB.Query(
		`SELECT "name","sql","description","created_at","origin","materialized","refresh_policy","last_refresh_at","last_refresh_rows" FROM "_m_views" ORDER BY "name"`,
	)
	if err != nil {
		return nil, fmt.Errorf("查询视图失败: %w", err)
	}
	defer rows.Close()
	var result []View
	for rows.Next() {
		var v View
		var name, sqlStr, desc, ca, origin sql.NullString
		// materialized 列为 INTEGER 0/1，用 NullInt64 中转再转 bool，避免 modernc sqlite 直接 Scan 进 bool 的行为差异
		var mat sql.NullInt64
		// refresh_policy 列可能为 NULL
		var rp sql.NullString
		// last_refresh_at 列可能为 NULL
		var lra sql.NullString
		// last_refresh_rows 列可能为 NULL
		var lrr sql.NullInt64
		if err := rows.Scan(&name, &sqlStr, &desc, &ca, &origin, &mat, &rp, &lra, &lrr); err != nil {
			return nil, fmt.Errorf("扫描视图失败: %w", err)
		}
		v.Name = name.String
		v.SQL = sqlStr.String
		v.Description = desc.String
		v.CreatedAt = ca.String
		v.Origin = origin.String
		v.Materialized = mat.Int64 != 0
		v.RefreshPolicy = rp.String
		v.LastRefreshAt = lra.String
		v.LastRefreshRows = lrr.Int64
		result = append(result, v)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历视图失败: %w", err)
	}
	return result, nil
}

// DropView 删除视图定义。
func (s *Store) DropView(name string) error {
	res, err := s.DB.Exec(`DELETE FROM "_m_views" WHERE "name"=?`, name)
	if err != nil {
		return fmt.Errorf("删除视图失败: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("获取影响行数失败: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// GetView 获取视图，不存在返回 ErrNotFound。
func (s *Store) GetView(name string) (View, error) {
	var v View
	var nameS, sqlStr, desc, ca, origin, refreshPolicy, lastRefreshAt sql.NullString
	var materialized, lastRefreshRows sql.NullInt64
	err := s.DB.QueryRow(
		`SELECT "name","sql","description","created_at","origin","materialized","refresh_policy","last_refresh_at","last_refresh_rows" FROM "_m_views" WHERE "name"=?`, name,
	).Scan(&nameS, &sqlStr, &desc, &ca, &origin, &materialized, &refreshPolicy, &lastRefreshAt, &lastRefreshRows)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return View{}, ErrNotFound
		}
		return View{}, fmt.Errorf("读取视图失败: %w", err)
	}
	v.Name = nameS.String
	v.SQL = sqlStr.String
	v.Description = desc.String
	v.CreatedAt = ca.String
	v.Origin = origin.String
	v.Materialized = materialized.Int64 != 0
	v.RefreshPolicy = refreshPolicy.String
	v.LastRefreshAt = lastRefreshAt.String
	v.LastRefreshRows = lastRefreshRows.Int64
	return v, nil
}

// materializeNameRe 校验物化视图名称是否为合法标识符。
var materializeNameRe = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

// MaterializeTableName 返回视图的物化表名（_mv_<name>），名称非法返回错误。
func MaterializeTableName(name string) (string, error) {
	if !materializeNameRe.MatchString(name) {
		return "", fmt.Errorf("视图名称 %q 不是合法标识符，无法物化", name)
	}
	return "_mv_" + name, nil
}

// UpdateViewMaterialize 更新视图的物化开关与刷新策略；视图不存在返回 ErrNotFound。
func (s *Store) UpdateViewMaterialize(name string, materialized bool, policy string) error {
	if _, err := s.GetView(name); err != nil {
		return err
	}
	if !materialized {
		policy = ""
	}
	mv := 0
	if materialized {
		mv = 1
	}
	res, err := s.DB.Exec(
		`UPDATE "_m_views" SET "materialized"=?, "refresh_policy"=? WHERE "name"=?`,
		mv, policy, name,
	)
	if err != nil {
		return fmt.Errorf("更新视图物化配置失败: %w", err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrNotFound
	}
	return nil
}

// RecordViewRefresh 记录一次刷新完成（last_refresh_at=RFC3339，last_refresh_rows=rows）；视图不存在返回 ErrNotFound。
func (s *Store) RecordViewRefresh(name string, rows int64) error {
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := s.DB.Exec(
		`UPDATE "_m_views" SET "last_refresh_at"=?, "last_refresh_rows"=? WHERE "name"=?`,
		now, rows, name,
	)
	if err != nil {
		return fmt.Errorf("记录视图刷新失败: %w", err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrNotFound
	}
	return nil
}

// Query 执行只读查询。守卫：仅允许 SELECT/WITH/EXPLAIN 开头，且不含分号。
func (s *Store) Query(query string, args ...any) (cols []string, rows [][]any, err error) {
	trimmed := strings.TrimSpace(query)
	upper := strings.ToUpper(trimmed)
	if !(strings.HasPrefix(upper, "SELECT") || strings.HasPrefix(upper, "WITH") || strings.HasPrefix(upper, "EXPLAIN")) {
		return nil, nil, fmt.Errorf("仅允许 SELECT/WITH/EXPLAIN 查询")
	}
	if strings.Contains(trimmed, ";") {
		return nil, nil, fmt.Errorf("查询语句不能包含分号")
	}
	r, err := s.DB.Query(trimmed, args...)
	if err != nil {
		return nil, nil, fmt.Errorf("执行查询失败: %w", err)
	}
	defer r.Close()
	cols, err = r.Columns()
	if err != nil {
		return nil, nil, fmt.Errorf("获取列名失败: %w", err)
	}
	for r.Next() {
		row := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range row {
			ptrs[i] = &row[i]
		}
		if err := r.Scan(ptrs...); err != nil {
			return nil, nil, fmt.Errorf("扫描行失败: %w", err)
		}
		rows = append(rows, row)
	}
	if err := r.Err(); err != nil {
		return nil, nil, fmt.Errorf("遍历结果失败: %w", err)
	}
	return cols, rows, nil
}

// Tables 列出用户表（排除 sqlite_% 与 _m_%），已排序。
func (s *Store) Tables() ([]string, error) {
	rows, err := s.DB.Query(
		`SELECT "name" FROM "sqlite_master"
		 WHERE "type"='table' AND "name" NOT LIKE 'sqlite\_%' ESCAPE '\' AND "name" NOT LIKE '_m\_%' ESCAPE '\'
		 ORDER BY "name"`,
	)
	if err != nil {
		return nil, fmt.Errorf("查询表失败: %w", err)
	}
	defer rows.Close()
	var result []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, fmt.Errorf("扫描表名失败: %w", err)
		}
		result = append(result, name)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历表失败: %w", err)
	}
	return result, nil
}

// TableCount 统计未删除行数。
func (s *Store) TableCount(table string) (int64, error) {
	stmt := fmt.Sprintf("SELECT COUNT(*) FROM %s WHERE %s = 0", quoteIdent(table), quoteIdent("_m_deleted"))
	var n int64
	if err := s.DB.QueryRow(stmt).Scan(&n); err != nil {
		return 0, fmt.Errorf("统计行数失败: %w", err)
	}
	return n, nil
}
