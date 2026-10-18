package pgsource

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PGSource 是基于 pgx v5 的只读 PostgreSQL 数据源实现。
type PGSource struct {
	pool    *pgxpool.Pool
	cfg     Config
	mu      sync.Mutex
	schemas []TableSchema
}

// Open 建立只读连接池并验证 default_transaction_read_only=on。
func Open(ctx context.Context, cfg Config) (*PGSource, error) {
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("配置校验失败: %w", err)
	}
	connStr, err := EnsureReadOnlyConnStr(cfg.ConnStr)
	if err != nil {
		return nil, fmt.Errorf("构造只读连接串失败: %w", err)
	}
	poolCfg, err := pgxpool.ParseConfig(connStr)
	if err != nil {
		return nil, fmt.Errorf("解析连接池配置失败: %w", err)
	}
	if poolCfg.ConnConfig.RuntimeParams == nil {
		poolCfg.ConnConfig.RuntimeParams = make(map[string]string)
	}
	poolCfg.ConnConfig.RuntimeParams["default_transaction_read_only"] = "on"

	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("创建连接池失败: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("连接池 Ping 失败: %w", err)
	}

	var flag string
	if err := pool.QueryRow(ctx, "SHOW default_transaction_read_only").Scan(&flag); err != nil {
		pool.Close()
		return nil, fmt.Errorf("校验只读模式失败: %w", err)
	}
	if !strings.EqualFold(strings.TrimSpace(flag), "on") {
		pool.Close()
		return nil, fmt.Errorf("只读模式未启用: default_transaction_read_only=%q", flag)
	}

	return &PGSource{pool: pool, cfg: cfg}, nil
}

// quoteIdent 对 SQL 标识符做双引号转义。
func quoteIdent(s string) string {
	return `"` + strings.ReplaceAll(s, `"`, `""`) + `"`
}

// readTx 开启一个只读事务。
func (s *PGSource) readTx(ctx context.Context) (pgx.Tx, error) {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, fmt.Errorf("开启只读事务失败: %w", err)
	}
	return tx, nil
}

const columnsSQL = `SELECT column_name, udt_name FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position`

const primaryKeySQL = `SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema WHERE tc.table_schema='public' AND tc.table_name=$1 AND tc.constraint_type='PRIMARY KEY' ORDER BY kcu.ordinal_position LIMIT 1`

// PullTables 拉取配置中所有表的结构，结果缓存。
func (s *PGSource) PullTables(ctx context.Context) ([]TableSchema, error) {
	s.mu.Lock()
	if s.schemas != nil {
		cached := make([]TableSchema, len(s.schemas))
		copy(cached, s.schemas)
		s.mu.Unlock()
		return cached, nil
	}
	s.mu.Unlock()

	if err := AssertReadOnlySQL(columnsSQL); err != nil {
		return nil, fmt.Errorf("列查询未通过只读校验: %w", err)
	}
	if err := AssertReadOnlySQL(primaryKeySQL); err != nil {
		return nil, fmt.Errorf("主键查询未通过只读校验: %w", err)
	}

	result := make([]TableSchema, 0, len(s.cfg.Tables))
	for _, table := range s.cfg.Tables {
		schema, err := s.pullOneTable(ctx, table)
		if err != nil {
			return nil, err
		}
		result = append(result, schema)
	}

	s.mu.Lock()
	s.schemas = result
	cached := make([]TableSchema, len(result))
	copy(cached, result)
	s.mu.Unlock()
	return cached, nil
}

func (s *PGSource) pullOneTable(ctx context.Context, table string) (TableSchema, error) {
	var schema TableSchema
	schema.Name = table

	tx, err := s.readTx(ctx)
	if err != nil {
		return schema, fmt.Errorf("表 %s 拉取结构失败: %w", table, err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	rows, err := tx.Query(ctx, columnsSQL, table)
	if err != nil {
		return schema, fmt.Errorf("表 %s 查询列失败: %w", table, err)
	}
	var columns []Column
	for rows.Next() {
		var name, udt string
		if err := rows.Scan(&name, &udt); err != nil {
			rows.Close()
			return schema, fmt.Errorf("表 %s 读取列失败: %w", table, err)
		}
		columns = append(columns, Column{
			Name:        name,
			PGType:      udt,
			MortiseType: MapPGType(udt),
		})
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return schema, fmt.Errorf("表 %s 遍历列失败: %w", table, err)
	}
	if len(columns) == 0 {
		return schema, fmt.Errorf("表 %s 不存在或没有列", table)
	}

	var pk string
	if err := tx.QueryRow(ctx, primaryKeySQL, table).Scan(&pk); err != nil {
		if err == pgx.ErrNoRows {
			return schema, fmt.Errorf("表 %s 没有主键，只读源要求主键", table)
		}
		return schema, fmt.Errorf("表 %s 查询主键失败: %w", table, err)
	}
	if pk == "" {
		return schema, fmt.Errorf("表 %s 没有主键，只读源要求主键", table)
	}

	if err := tx.Commit(ctx); err != nil {
		return schema, fmt.Errorf("表 %s 提交只读事务失败: %w", table, err)
	}

	schema.PrimaryKey = pk
	schema.Columns = columns
	return schema, nil
}

func (s *PGSource) tableAllowed(table string) bool {
	for _, t := range s.cfg.Tables {
		if t == table {
			return true
		}
	}
	return false
}

func (s *PGSource) schemaFor(ctx context.Context, table string) (TableSchema, error) {
	schemas, err := s.PullTables(ctx)
	if err != nil {
		return TableSchema{}, err
	}
	for _, sc := range schemas {
		if sc.Name == table {
			return sc, nil
		}
	}
	return TableSchema{}, fmt.Errorf("表 %s 不在配置的表列表中", table)
}

// PullRows 按游标增量拉取表中的行。
func (s *PGSource) PullRows(ctx context.Context, table string, since Cursor) ([]Row, error) {
	if !s.tableAllowed(table) {
		return nil, fmt.Errorf("表 %s 不在配置的表列表中，拒绝拉取", table)
	}
	schema, err := s.schemaFor(ctx, table)
	if err != nil {
		return nil, err
	}

	cursorCol := s.cfg.CursorColumn
	if cursorCol == "" {
		cursorCol = "updated_at"
	}

	var hasCursor bool
	var hasPK bool
	for _, c := range schema.Columns {
		if c.Name == cursorCol {
			hasCursor = true
		}
		if c.Name == schema.PrimaryKey {
			hasPK = true
		}
	}
	if !hasCursor {
		return nil, fmt.Errorf("表 %s 缺少游标列 %s", table, cursorCol)
	}
	if !hasPK {
		return nil, fmt.Errorf("表 %s 缺少主键列 %s", table, schema.PrimaryKey)
	}

	colList := make([]string, 0, len(schema.Columns))
	for _, c := range schema.Columns {
		colList = append(colList, quoteIdent(c.Name))
	}
	qTable := quoteIdent(table)
	qCursor := quoteIdent(cursorCol)
	qPK := quoteIdent(schema.PrimaryKey)

	batchSize := s.cfg.BatchSize
	if batchSize <= 0 {
		batchSize = 1000
	}

	var sql string
	var args []any
	if since.UpdatedAt.IsZero() {
		sql = fmt.Sprintf(
			"SELECT %s FROM %s WHERE $1 = $1 ORDER BY %s ASC, %s ASC LIMIT %d",
			strings.Join(colList, ", "), qTable, qCursor, qPK, batchSize,
		)
		args = []any{true}
	} else {
		sql = fmt.Sprintf(
			"SELECT %s FROM %s WHERE %s > $1 OR (%s = $1 AND %s > $2) ORDER BY %s ASC, %s ASC LIMIT %d",
			strings.Join(colList, ", "), qTable, qCursor, qCursor, qPK, qCursor, qPK, batchSize,
		)
		args = []any{since.UpdatedAt, since.LastPK}
	}

	if err := AssertReadOnlySQL(sql); err != nil {
		return nil, fmt.Errorf("表 %s 行查询未通过只读校验: %w", table, err)
	}

	tx, err := s.readTx(ctx)
	if err != nil {
		return nil, fmt.Errorf("表 %s 拉取行失败: %w", table, err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	rows, err := tx.Query(ctx, sql, args...)
	if err != nil {
		return nil, fmt.Errorf("表 %s 执行行查询失败: %w", table, err)
	}
	defer rows.Close()

	fieldDescs := rows.FieldDescriptions()
	fieldNames := make([]string, len(fieldDescs))
	for i, fd := range fieldDescs {
		fieldNames[i] = fd.Name
	}

	var out []Row
	for rows.Next() {
		values, err := rows.Values()
		if err != nil {
			return nil, fmt.Errorf("表 %s 读取行失败: %w", table, err)
		}
		row := make(Row, len(fieldNames))
		for i, name := range fieldNames {
			row[name] = normalizeValue(values[i])
		}
		if _, ok := row[schema.PrimaryKey]; !ok {
			return nil, fmt.Errorf("表 %s 行缺少主键列 %s", table, schema.PrimaryKey)
		}
		if _, ok := row[cursorCol]; !ok {
			return nil, fmt.Errorf("表 %s 行缺少游标列 %s", table, cursorCol)
		}
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("表 %s 遍历行失败: %w", table, err)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("表 %s 提交只读事务失败: %w", table, err)
	}

	if out == nil {
		out = []Row{}
	}
	return out, nil
}

func normalizeValue(v any) any {
	switch t := v.(type) {
	case time.Time:
		return t.UTC().Format(time.RFC3339)
	case []byte:
		return string(t)
	default:
		return v
	}
}

// Close 关闭连接池。
func (s *PGSource) Close() error {
	if s.pool != nil {
		s.pool.Close()
	}
	return nil
}
