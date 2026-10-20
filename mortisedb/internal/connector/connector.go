// Package connector 提供数据源连接器：csv、json、sqlite、dir 四种实现。
package connector

import (
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/pgsource"

	_ "modernc.org/sqlite"
)

// Row 表示一行数据，列名到值的映射。
type Row = map[string]any

// TableInfo 描述一张可同步的表。
type TableInfo struct {
	Name        string         // 目标表名
	SourceTable string         // 源表名（sqlite 场景下为源库表名，其余等于 Name）
	Primary     string         // 主键列名
	Columns     []infer.Column // 列定义
}

// Source 数据源接口。
type Source interface {
	Name() string
	Tables() ([]TableInfo, error)
	Rows(table string, since map[string]string) ([]Row, error)
	Close() error
}

// Open 根据配置打开对应的数据源。
func Open(cfg config.SourceConfig) (Source, error) {
	switch cfg.Type {
	case "csv":
		return openCSV(cfg)
	case "json":
		return openJSON(cfg)
	case "sqlite":
		return openSQLite(cfg)
	case "dir":
		return openDir(cfg)
	case "pg":
		return openPG(cfg)
	default:
		return nil, fmt.Errorf("不支持的数据源类型: %s", cfg.Type)
	}
}

// openPG 打开 PostgreSQL 只读数据源，把 SourceConfig 映射为 pgsource.Config，
// 再桥接为 connector.Source 返回。
func openPG(cfg config.SourceConfig) (Source, error) {
	if strings.TrimSpace(cfg.Options["conn_str"]) == "" {
		return nil, fmt.Errorf("数据源 %q (pg) 缺少 options.conn_str", cfg.Name)
	}
	pcfg := pgsource.Config{
		ConnStr: cfg.Options["conn_str"],
	}
	if len(cfg.Tables) > 0 {
		tables := make([]string, 0, len(cfg.Tables))
		for _, tm := range cfg.Tables {
			tables = append(tables, tm.Source)
		}
		pcfg.Tables = tables
	} else {
		pcfg.Tables = []string{cfg.Table}
	}

	cursorCol := ""
	if v := cfg.Options["cursor_column"]; strings.TrimSpace(v) != "" {
		cursorCol = v
	} else if strings.HasPrefix(cfg.Incremental, "column:") {
		cursorCol = strings.TrimPrefix(cfg.Incremental, "column:")
	} else {
		cursorCol = "updated_at"
	}

	batchSize := 1000
	if v := cfg.Options["batch_size"]; strings.TrimSpace(v) != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			batchSize = n
		}
	}
	pcfg.CursorColumn = cursorCol
	pcfg.BatchSize = batchSize

	src, err := pgsource.Open(context.Background(), pcfg)
	if err != nil {
		return nil, err
	}
	return NewPGAdapter(cfg.Name, src, cursorCol), nil
}

// ---------------- csv ----------------

type csvSource struct {
	cfg     config.SourceConfig
	columns []infer.Column
}

func openCSV(cfg config.SourceConfig) (Source, error) {
	if cfg.Path == "" {
		return nil, fmt.Errorf("csv 数据源 %q 缺少 path", cfg.Name)
	}
	if cfg.Table == "" {
		return nil, fmt.Errorf("csv 数据源 %q 缺少 table", cfg.Name)
	}
	if cfg.PrimaryKey == "" {
		return nil, fmt.Errorf("csv 数据源 %q 缺少 primary_key", cfg.Name)
	}
	// 零字节文件：无列可推断，返回空列的 source；sync 侧约定空列直接返回零统计。
	if fi, statErr := os.Stat(cfg.Path); statErr != nil {
		return nil, fmt.Errorf("读取 csv 文件状态失败: %w", statErr)
	} else if fi.Size() == 0 {
		return &csvSource{cfg: cfg, columns: nil}, nil
	}
	delim := cfg.Options["delimiter"]
	cols, err := infer.InferCSV(cfg.Path, delim)
	if err != nil {
		return nil, fmt.Errorf("推断 csv 列失败: %w", err)
	}
	if !hasColumn(cols, cfg.PrimaryKey) {
		return nil, fmt.Errorf("csv 数据源 %q 主键列 %q 不存在", cfg.Name, cfg.PrimaryKey)
	}
	return &csvSource{cfg: cfg, columns: cols}, nil
}

func (s *csvSource) Name() string { return s.cfg.Name }

func (s *csvSource) Tables() ([]TableInfo, error) {
	return []TableInfo{{
		Name:        s.cfg.Table,
		SourceTable: s.cfg.Table,
		Primary:     s.cfg.PrimaryKey,
		Columns:     s.columns,
	}}, nil
}

func (s *csvSource) Rows(table string, since map[string]string) ([]Row, error) {
	f, err := os.Open(s.cfg.Path)
	if err != nil {
		return nil, fmt.Errorf("打开 csv 文件失败: %w", err)
	}
	defer f.Close()

	r := csv.NewReader(f)
	delim := s.cfg.Options["delimiter"]
	if delim == "" {
		delim = ","
	}
	dr := []rune(delim)
	if len(dr) > 0 {
		r.Comma = dr[0]
	}
	r.FieldsPerRecord = -1

	header, err := r.Read()
	if err != nil {
		if err == io.EOF {
			return nil, nil
		}
		return nil, fmt.Errorf("读取 csv 表头失败: %w", err)
	}

	typeByCol := make(map[string]string, len(s.columns))
	for _, c := range s.columns {
		typeByCol[c.Name] = c.Type
	}

	var rows []Row
	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("读取 csv 行失败: %w", err)
		}
		row := make(Row, len(header))
		for i, h := range header {
			h = strings.TrimSpace(h)
			var raw string
			if i < len(rec) {
				raw = rec[i]
			}
			typ := typeByCol[h]
			if typ == "" {
				typ = "TEXT"
			}
			v, err := infer.ParseValue(raw, typ)
			if err != nil {
				return nil, fmt.Errorf("解析 csv 列 %q 值 %q 失败: %w", h, raw, err)
			}
			row[h] = v
		}
		if !matchSince(row, since) {
			continue
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func (s *csvSource) Close() error { return nil }

// ---------------- json ----------------

type jsonSource struct {
	cfg     config.SourceConfig
	columns []infer.Column
}

func openJSON(cfg config.SourceConfig) (Source, error) {
	if cfg.Path == "" {
		return nil, fmt.Errorf("json 数据源 %q 缺少 path", cfg.Name)
	}
	if cfg.Table == "" {
		return nil, fmt.Errorf("json 数据源 %q 缺少 table", cfg.Name)
	}
	if cfg.PrimaryKey == "" {
		return nil, fmt.Errorf("json 数据源 %q 缺少 primary_key", cfg.Name)
	}
	root := cfg.Options["root"]
	cols, err := infer.InferJSON(cfg.Path, root)
	if err != nil {
		return nil, fmt.Errorf("推断 json 列失败: %w", err)
	}
	if !hasColumn(cols, cfg.PrimaryKey) {
		return nil, fmt.Errorf("json 数据源 %q 主键列 %q 不存在", cfg.Name, cfg.PrimaryKey)
	}
	return &jsonSource{cfg: cfg, columns: cols}, nil
}

func (s *jsonSource) Name() string { return s.cfg.Name }

func (s *jsonSource) Tables() ([]TableInfo, error) {
	return []TableInfo{{
		Name:        s.cfg.Table,
		SourceTable: s.cfg.Table,
		Primary:     s.cfg.PrimaryKey,
		Columns:     s.columns,
	}}, nil
}

func (s *jsonSource) Rows(table string, since map[string]string) ([]Row, error) {
	data, err := os.ReadFile(s.cfg.Path)
	if err != nil {
		return nil, fmt.Errorf("读取 json 文件失败: %w", err)
	}
	var root any
	if err := json.Unmarshal(data, &root); err != nil {
		return nil, fmt.Errorf("解析 json 文件失败: %w", err)
	}
	rootPath := s.cfg.Options["root"]
	items, err := extractJSONArray(root, rootPath)
	if err != nil {
		return nil, err
	}

	typeByCol := make(map[string]string, len(s.columns))
	for _, c := range s.columns {
		typeByCol[c.Name] = c.Type
	}

	var rows []Row
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("json 数组元素不是对象")
		}
		row := make(Row, len(obj))
		for k, v := range obj {
			typ := typeByCol[k]
			if typ == "" {
				typ = "TEXT"
			}
			row[k] = normalizeJSONValue(v, typ)
		}
		if !matchSince(row, since) {
			continue
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func (s *jsonSource) Close() error { return nil }

// extractJSONArray 按 root 路径取出数组。
func extractJSONArray(root any, rootPath string) ([]any, error) {
	if rootPath == "" {
		arr, ok := root.([]any)
		if !ok {
			return nil, fmt.Errorf("json 顶层不是数组")
		}
		return arr, nil
	}
	cur := root
	for _, part := range strings.Split(rootPath, ".") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		m, ok := cur.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("json 路径 %q 解析失败: 中间不是对象", rootPath)
		}
		cur = m[part]
	}
	arr, ok := cur.([]any)
	if !ok {
		return nil, fmt.Errorf("json 路径 %q 不是数组", rootPath)
	}
	return arr, nil
}

// normalizeJSONValue 将 json 原生值按推断类型规范化为存储值。
func normalizeJSONValue(v any, typ string) any {
	if v == nil {
		return nil
	}
	switch tv := v.(type) {
	case string:
		out, err := infer.ParseValue(tv, typ)
		if err == nil {
			return out
		}
		return tv
	case bool:
		if typ == "BOOLEAN" {
			return tv
		}
		if tv {
			return int64(1)
		}
		return int64(0)
	case float64:
		switch typ {
		case "INTEGER":
			return int64(tv)
		case "REAL":
			return tv
		case "BOOLEAN":
			if tv != 0 {
				return true
			}
			return false
		default:
			return tv
		}
	case json.Number:
		if typ == "INTEGER" {
			if i, err := tv.Int64(); err == nil {
				return i
			}
		}
		if f, err := tv.Float64(); err == nil {
			return f
		}
		return tv.String()
	default:
		// 嵌套对象/数组转为 JSON 字符串
		b, err := json.Marshal(tv)
		if err != nil {
			return fmt.Sprintf("%v", tv)
		}
		return string(b)
	}
}

// ---------------- sqlite ----------------

type sqliteSource struct {
	cfg config.SourceConfig
	db  *sql.DB
}

func openSQLite(cfg config.SourceConfig) (Source, error) {
	if cfg.Path == "" {
		return nil, fmt.Errorf("sqlite 数据源 %q 缺少 path", cfg.Name)
	}
	if len(cfg.Tables) == 0 {
		return nil, fmt.Errorf("sqlite 数据源 %q 缺少 tables 映射", cfg.Name)
	}
	for _, tm := range cfg.Tables {
		if tm.Source == "" || tm.Target == "" || tm.PrimaryKey == "" {
			return nil, fmt.Errorf("sqlite 数据源 %q 的 tables 映射必须包含 source/target/primary_key", cfg.Name)
		}
	}
	dsn := "file:" + cfg.Path + "?mode=ro"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("打开 sqlite 数据源失败: %w", err)
	}
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("连接 sqlite 数据源失败: %w", err)
	}
	return &sqliteSource{cfg: cfg, db: db}, nil
}

func (s *sqliteSource) Name() string { return s.cfg.Name }

func (s *sqliteSource) Tables() ([]TableInfo, error) {
	var out []TableInfo
	for _, tm := range s.cfg.Tables {
		cols, err := s.tableColumns(tm.Source)
		if err != nil {
			return nil, err
		}
		if !hasColumn(cols, tm.PrimaryKey) {
			return nil, fmt.Errorf("sqlite 源表 %q 中主键列 %q 不存在", tm.Source, tm.PrimaryKey)
		}
		out = append(out, TableInfo{
			Name:        tm.Target,
			SourceTable: tm.Source,
			Primary:     tm.PrimaryKey,
			Columns:     cols,
		})
	}
	return out, nil
}

// tableColumns 查询源表列信息并推断类型。
func (s *sqliteSource) tableColumns(srcTable string) ([]infer.Column, error) {
	q := fmt.Sprintf(`PRAGMA table_info("%s")`, escapeIdent(srcTable))
	rows, err := s.db.Query(q)
	if err != nil {
		return nil, fmt.Errorf("查询表结构失败: %w", err)
	}
	defer rows.Close()

	var cols []infer.Column
	for rows.Next() {
		var cid int
		var name, ctype string
		var notnull int
		var dflt sql.NullString
		var pk int
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			return nil, fmt.Errorf("扫描表结构失败: %w", err)
		}
		cols = append(cols, infer.Column{Name: name, Type: sqliteToInfer(ctype)})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历表结构失败: %w", err)
	}
	return cols, nil
}

// sqliteToInfer 将 sqlite 声明类型映射为推断类型。
func sqliteToInfer(declared string) string {
	u := strings.ToUpper(strings.TrimSpace(declared))
	switch {
	case u == "":
		return "TEXT"
	case strings.Contains(u, "INT"):
		return "INTEGER"
	case strings.Contains(u, "REAL"), strings.Contains(u, "FLOA"), strings.Contains(u, "DOUB"):
		return "REAL"
	case strings.Contains(u, "BOOL"):
		return "BOOLEAN"
	case strings.Contains(u, "DATE"), strings.Contains(u, "TIME"):
		return "DATETIME"
	default:
		return "TEXT"
	}
}

func (s *sqliteSource) Rows(table string, since map[string]string) ([]Row, error) {
	var tm *config.TableMap
	for i := range s.cfg.Tables {
		if s.cfg.Tables[i].Target == table {
			tm = &s.cfg.Tables[i]
			break
		}
	}
	if tm == nil {
		return nil, fmt.Errorf("sqlite 数据源 %q 找不到目标表 %q 的映射", s.cfg.Name, table)
	}

	cols, err := s.tableColumns(tm.Source)
	if err != nil {
		return nil, err
	}

	var sb strings.Builder
	sb.WriteString("SELECT ")
	for i, c := range cols {
		if i > 0 {
			sb.WriteString(", ")
		}
		sb.WriteString(`"` + escapeIdent(c.Name) + `"`)
	}
	sb.WriteString(` FROM "` + escapeIdent(tm.Source) + `"`)
	// 注：水位线过滤在 Go 侧用 matchSince 做（双边日期格式规范化后比较），
	// 不下推 SQL WHERE，避免源表日期写法与水位线写法不一致导致误判；
	// 数据量大时的 SQL 级下推可作为后续优化。
	rows, err := s.db.Query(sb.String())
	if err != nil {
		return nil, fmt.Errorf("查询源表 %q 失败: %w", tm.Source, err)
	}
	defer rows.Close()

	colNames := make([]string, len(cols))
	for i, c := range cols {
		colNames[i] = c.Name
	}

	var out []Row
	for rows.Next() {
		scanDest := make([]any, len(cols))
		scanPtrs := make([]any, len(cols))
		for i := range scanDest {
			scanPtrs[i] = &scanDest[i]
		}
		if err := rows.Scan(scanPtrs...); err != nil {
			return nil, fmt.Errorf("扫描源表 %q 行失败: %w", tm.Source, err)
		}
		row := make(Row, len(cols))
		for i, name := range colNames {
			row[name] = normalizeDBValue(scanDest[i], cols[i].Type)
		}
		if !matchSince(row, since) {
			continue
		}
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历源表 %q 失败: %w", tm.Source, err)
	}
	return out, nil
}

func (s *sqliteSource) Close() error {
	if s.db != nil {
		return s.db.Close()
	}
	return nil
}

// normalizeDBValue 将数据库驱动返回的原值按目标类型规范化。
func normalizeDBValue(v any, typ string) any {
	if v == nil {
		return nil
	}
	switch tv := v.(type) {
	case int64:
		switch typ {
		case "REAL":
			return float64(tv)
		case "BOOLEAN":
			return tv != 0
		case "TEXT":
			return infer.Stringify(tv)
		default:
			return tv
		}
	case float64:
		switch typ {
		case "INTEGER":
			return int64(tv)
		case "BOOLEAN":
			return tv != 0
		case "TEXT":
			return infer.Stringify(tv)
		default:
			return tv
		}
	case bool:
		if typ == "INTEGER" {
			if tv {
				return int64(1)
			}
			return int64(0)
		}
		return tv
	case []byte:
		s := string(tv)
		if typ == "TEXT" || typ == "DATETIME" {
			return s
		}
		out, err := infer.ParseValue(s, typ)
		if err == nil {
			return out
		}
		return s
	case string:
		out, err := infer.ParseValue(tv, typ)
		if err == nil {
			return out
		}
		return tv
	case time.Time:
		return tv.UTC().Format(time.RFC3339)
	default:
		return tv
	}
}

// ---------------- dir ----------------

type dirSource struct {
	cfg config.SourceConfig
}

func openDir(cfg config.SourceConfig) (Source, error) {
	if cfg.Path == "" {
		return nil, fmt.Errorf("dir 数据源 %q 缺少 path", cfg.Name)
	}
	return &dirSource{cfg: cfg}, nil
}

func (s *dirSource) Name() string { return s.cfg.Name }

func (s *dirSource) tableName() string {
	if s.cfg.Table == "" {
		return "files"
	}
	return s.cfg.Table
}

func (s *dirSource) Tables() ([]TableInfo, error) {
	cols := []infer.Column{
		{Name: "path", Type: "TEXT"},
		{Name: "name", Type: "TEXT"},
		{Name: "size", Type: "INTEGER"},
		{Name: "modtime", Type: "DATETIME"},
		{Name: "ext", Type: "TEXT"},
		{Name: "is_dir", Type: "INTEGER"},
	}
	return []TableInfo{{
		Name:        s.tableName(),
		SourceTable: s.tableName(),
		Primary:     "path",
		Columns:     cols,
	}}, nil
}

func (s *dirSource) Rows(table string, since map[string]string) ([]Row, error) {
	root := s.cfg.Path
	info, err := os.Stat(root)
	if err != nil {
		return nil, fmt.Errorf("访问目录失败: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("路径不是目录: %s", root)
	}

	var rows []Row
	err = filepath.WalkDir(root, func(p string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if rel == "." {
			return nil // 跳过根目录自身
		}
		fi, err := d.Info()
		if err != nil {
			return err
		}
		row := Row{
			"path":    rel,
			"name":    d.Name(),
			"size":    fi.Size(),
			"modtime": fi.ModTime().UTC().Format(time.RFC3339),
			"ext":     strings.ToLower(filepath.Ext(d.Name())),
		}
		if d.IsDir() {
			row["is_dir"] = int64(1)
		} else {
			row["is_dir"] = int64(0)
		}
		if !matchSince(row, since) {
			return nil
		}
		rows = append(rows, row)
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("遍历目录失败: %w", err)
	}
	return rows, nil
}

func (s *dirSource) Close() error { return nil }

// ---------------- 辅助 ----------------

// hasColumn 判断列集合中是否包含指定名称的列。
func hasColumn(cols []infer.Column, name string) bool {
	for _, c := range cols {
		if c.Name == name {
			return true
		}
	}
	return false
}

// matchSince 使用规范化后比较判断行是否超过水位线。
// 增量列值为空时无法排序，按"未知时间=有变更"放行，避免静默丢行。
func matchSince(row Row, since map[string]string) bool {
	if len(since) == 0 {
		return true
	}
	for col, wm := range since {
		if wm == "" {
			continue
		}
		v := infer.NormalizeComparable(infer.Stringify(row[col]))
		if v == "" {
			continue
		}
		if v <= infer.NormalizeComparable(wm) {
			return false
		}
	}
	return true
}

// escapeIdent 转义 SQL 标识符中的双引号。
func escapeIdent(s string) string {
	return strings.ReplaceAll(s, `"`, `""`)
}

// 确保 sort 被使用（某些编译路径下用于稳定输出）。
var _ = sort.Strings
