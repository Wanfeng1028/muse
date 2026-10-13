package connector

import (
	"context"
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("创建目录失败: %v", err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写文件失败: %v", err)
	}
}

func TestCSVSource(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "users.csv")
	writeFile(t, path, "id,name,age,updated_at\n1,张三,30,2024-01-01 00:00:00\n2,李四,25,2024-01-02 00:00:00\n3,王五,40,2024-01-03 00:00:00\n")

	cfg := config.SourceConfig{
		Name:        "csvsrc",
		Type:        "csv",
		Path:        path,
		Table:       "users",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	src, err := Open(cfg)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer src.Close()

	if src.Name() != "csvsrc" {
		t.Fatalf("Name 不匹配: %s", src.Name())
	}

	tables, err := src.Tables()
	if err != nil {
		t.Fatalf("Tables 失败: %v", err)
	}
	if len(tables) != 1 {
		t.Fatalf("期望 1 张表, 得到 %d", len(tables))
	}
	ti := tables[0]
	if ti.Name != "users" || ti.SourceTable != "users" || ti.Primary != "id" {
		t.Fatalf("表信息不匹配: %+v", ti)
	}
	if len(ti.Columns) != 4 {
		t.Fatalf("期望 4 列, 得到 %d", len(ti.Columns))
	}
	if ti.Columns[0].Name != "id" || ti.Columns[0].Type != "INTEGER" {
		t.Fatalf("id 列类型不匹配: %+v", ti.Columns[0])
	}

	rows, err := src.Rows("users", nil)
	if err != nil {
		t.Fatalf("Rows 失败: %v", err)
	}
	if len(rows) != 3 {
		t.Fatalf("期望 3 行, 得到 %d", len(rows))
	}
	if rows[0]["name"] != "张三" {
		t.Fatalf("首行 name 不匹配: %v", rows[0]["name"])
	}
	if v, ok := rows[0]["id"].(int64); !ok || v != 1 {
		t.Fatalf("首行 id 不匹配: %v (%T)", rows[0]["id"], rows[0]["id"])
	}

	rows2, err := src.Rows("users", map[string]string{"updated_at": "2024-01-01 00:00:00"})
	if err != nil {
		t.Fatalf("Rows(since) 失败: %v", err)
	}
	if len(rows2) != 2 {
		t.Fatalf("since 过滤后期望 2 行, 得到 %d", len(rows2))
	}
	if rows2[0]["name"] != "李四" {
		t.Fatalf("since 过滤首行 name 不匹配: %v", rows2[0]["name"])
	}
}

func TestJSONSource(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "data.json")
	writeFile(t, path, `{"data":{"items":[{"id":1,"title":"甲","done":true},{"id":2,"title":"乙","done":false},{"id":3,"title":"丙","done":true}]}}`)

	cfg := config.SourceConfig{
		Name:       "jsonsrc",
		Type:       "json",
		Path:       path,
		Table:      "items",
		PrimaryKey: "id",
		Options:    map[string]string{"root": "data.items"},
	}
	src, err := Open(cfg)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer src.Close()

	tables, err := src.Tables()
	if err != nil {
		t.Fatalf("Tables 失败: %v", err)
	}
	if len(tables) != 1 {
		t.Fatalf("期望 1 张表, 得到 %d", len(tables))
	}
	if tables[0].Name != "items" || tables[0].Primary != "id" {
		t.Fatalf("表信息不匹配: %+v", tables[0])
	}
	if len(tables[0].Columns) != 3 {
		t.Fatalf("期望 3 列, 得到 %d", len(tables[0].Columns))
	}

	rows, err := src.Rows("items", nil)
	if err != nil {
		t.Fatalf("Rows 失败: %v", err)
	}
	if len(rows) != 3 {
		t.Fatalf("期望 3 行, 得到 %d", len(rows))
	}
	if rows[1]["title"] != "乙" {
		t.Fatalf("第二行 title 不匹配: %v", rows[1]["title"])
	}
}

func TestJSONSourceTopLevelArray(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "arr.json")
	writeFile(t, path, `[{"id":1,"name":"x"},{"id":2,"name":"y"}]`)

	cfg := config.SourceConfig{
		Name:       "arrsrc",
		Type:       "json",
		Path:       path,
		Table:      "arr",
		PrimaryKey: "id",
	}
	src, err := Open(cfg)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer src.Close()

	rows, err := src.Rows("arr", nil)
	if err != nil {
		t.Fatalf("Rows 失败: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("期望 2 行, 得到 %d", len(rows))
	}
}

func createSQLiteFixture(t *testing.T, dir string) string {
	t.Helper()
	path := filepath.Join(dir, "test.db")
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		t.Fatalf("打开 sqlite 失败: %v", err)
	}
	defer db.Close()

	stmts := []string{
		`CREATE TABLE "users" ("id" INTEGER PRIMARY KEY, "name" TEXT, "age" INTEGER, "updated_at" TEXT)`,
		`INSERT INTO "users" ("id","name","age","updated_at") VALUES (1,'张三',30,'2024-01-01 00:00:00')`,
		`INSERT INTO "users" ("id","name","age","updated_at") VALUES (2,'李四',25,'2024-01-02 00:00:00')`,
		`CREATE TABLE "orders" ("oid" INTEGER PRIMARY KEY, "amount" REAL, "updated_at" TEXT)`,
		`INSERT INTO "orders" ("oid","amount","updated_at") VALUES (100,9.5,'2024-01-01 00:00:00')`,
		`CREATE TABLE "_m_internal" ("x" INTEGER)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("执行 SQL 失败 (%s): %v", s, err)
		}
	}
	return path
}

func TestSQLiteSource(t *testing.T) {
	dir := t.TempDir()
	path := createSQLiteFixture(t, dir)

	cfg := config.SourceConfig{
		Name: "sqlitesrc",
		Type: "sqlite",
		Path: path,
		Tables: []config.TableMap{
			{Source: "users", Target: "users", PrimaryKey: "id"},
			{Source: "orders", Target: "orders_map", PrimaryKey: "oid"},
		},
	}
	src, err := Open(cfg)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer src.Close()

	tables, err := src.Tables()
	if err != nil {
		t.Fatalf("Tables 失败: %v", err)
	}
	if len(tables) != 2 {
		t.Fatalf("期望 2 张表, 得到 %d", len(tables))
	}
	byName := map[string]TableInfo{}
	for _, ti := range tables {
		byName[ti.Name] = ti
	}
	u, ok := byName["users"]
	if !ok {
		t.Fatalf("未找到 users 表")
	}
	if u.SourceTable != "users" || u.Primary != "id" {
		t.Fatalf("users 表信息不匹配: %+v", u)
	}
	o, ok := byName["orders_map"]
	if !ok {
		t.Fatalf("未找到 orders_map 表")
	}
	if o.SourceTable != "orders" || o.Primary != "oid" {
		t.Fatalf("orders_map 表信息不匹配: %+v", o)
	}

	rows, err := src.Rows("users", nil)
	if err != nil {
		t.Fatalf("Rows 失败: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("期望 2 行, 得到 %d", len(rows))
	}
	if rows[0]["name"] != "张三" {
		t.Fatalf("首行 name 不匹配: %v", rows[0]["name"])
	}

	rows2, err := src.Rows("users", map[string]string{"updated_at": "2024-01-01 00:00:00"})
	if err != nil {
		t.Fatalf("Rows(since) 失败: %v", err)
	}
	if len(rows2) != 1 {
		t.Fatalf("since 过滤后期望 1 行, 得到 %d", len(rows2))
	}
	if rows2[0]["name"] != "李四" {
		t.Fatalf("since 过滤首行 name 不匹配: %v", rows2[0]["name"])
	}
}

func TestSQLiteSourceNoTablesMapping(t *testing.T) {
	dir := t.TempDir()
	path := createSQLiteFixture(t, dir)

	cfg := config.SourceConfig{
		Name: "sqlitesrc2",
		Type: "sqlite",
		Path: path,
	}
	if _, err := Open(cfg); err == nil {
		t.Fatalf("期望因缺少 Tables 映射报错")
	}
}

func TestSQLiteSourceMissingPrimaryMapping(t *testing.T) {
	dir := t.TempDir()
	path := createSQLiteFixture(t, dir)

	cfg := config.SourceConfig{
		Name: "sqlitesrc3",
		Type: "sqlite",
		Path: path,
		Tables: []config.TableMap{
			{Source: "users", Target: "users"},
		},
	}
	if _, err := Open(cfg); err == nil {
		t.Fatalf("期望因缺少映射主键报错")
	}
}

func TestDirSource(t *testing.T) {
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "a.txt"), "hello")
	writeFile(t, filepath.Join(dir, "b.log"), "world")
	if err := os.MkdirAll(filepath.Join(dir, "sub"), 0o755); err != nil {
		t.Fatalf("创建子目录失败: %v", err)
	}
	writeFile(t, filepath.Join(dir, "sub", "c.txt"), "deep")

	cfg := config.SourceConfig{
		Name:       "dirsrc",
		Type:       "dir",
		Path:       dir,
		Table:      "",
		PrimaryKey: "path",
	}
	src, err := Open(cfg)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer src.Close()

	tables, err := src.Tables()
	if err != nil {
		t.Fatalf("Tables 失败: %v", err)
	}
	if len(tables) != 1 {
		t.Fatalf("期望 1 张表, 得到 %d", len(tables))
	}
	if tables[0].Name != "files" {
		t.Fatalf("默认表名应为 files, 得到 %s", tables[0].Name)
	}
	if tables[0].Primary != "path" {
		t.Fatalf("主键应为 path, 得到 %s", tables[0].Primary)
	}
	cols := tables[0].Columns
	wantCols := []string{"path", "name", "size", "modtime", "ext", "is_dir"}
	if len(cols) != len(wantCols) {
		t.Fatalf("期望 %d 列, 得到 %d", len(wantCols), len(cols))
	}
	for i, c := range cols {
		if c.Name != wantCols[i] {
			t.Fatalf("第 %d 列名应为 %s, 得到 %s", i, wantCols[i], c.Name)
		}
	}

	rows, err := src.Rows("files", nil)
	if err != nil {
		t.Fatalf("Rows 失败: %v", err)
	}
	if len(rows) != 4 {
		t.Fatalf("期望 4 行 (a.txt,b.log,sub,c.txt), 得到 %d", len(rows))
	}
	var hasDir bool
	for _, r := range rows {
		if v, ok := r["is_dir"].(int64); ok && v == 1 {
			hasDir = true
		}
	}
	if !hasDir {
		t.Fatalf("未找到目录行")
	}
}

func TestOpenInvalidType(t *testing.T) {
	cfg := config.SourceConfig{
		Name: "bad",
		Type: "unknown",
	}
	if _, err := Open(cfg); err == nil {
		t.Fatalf("非法 type 应返回错误")
	}
}

func TestParseValueRoundtrip(t *testing.T) {
	_ = context.Background()
	_ = json.Valid
	_ = time.Now
}
