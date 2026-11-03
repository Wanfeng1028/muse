package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadValid(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mortise.yaml")
	content := `
version: 1
database: "./data/test.db"
addr: ":9000"
sources:
  - name: local_sqlite
    type: sqlite
    path: "./data/source.db"
    incremental: "column:updated_at"
    tables:
      - source: "users"
        target: "users"
        primary_key: "id"
      - source: "orders"
        target: "orders_v2"
        primary_key: "order_id"
  - name: csv_users
    type: csv
    path: "./data/users.csv"
    table: "csv_users"
    primary_key: "id"
    options:
      delimiter: ","
  - name: json_data
    type: json
    path: "./data/data.json"
    table: "json_data"
    primary_key: "key"
    options:
      root: "data.items"
  - name: files_dir
    type: dir
    path: "./data/files"
    table: "files"
    primary_key: "path"
    incremental: "hash"
views:
  - name: v_users
    sql: "SELECT * FROM users"
    description: "用户视图"
jobs:
  - name: job_all
    interval: "1m"
    sources: ["local_sqlite", "csv_users"]
  - name: job_json
    interval: "30s"
    sources: ["json_data"]
sync:
  conflict: "priority"
  priority: ["local_sqlite", "csv_users"]
  soft_delete: true
`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 YAML 失败: %v", err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}

	if cfg.Version != 1 {
		t.Errorf("Version = %d, 期望 1", cfg.Version)
	}
	if cfg.Database != "./data/test.db" {
		t.Errorf("Database = %q", cfg.Database)
	}
	if cfg.Addr != ":9000" {
		t.Errorf("Addr = %q", cfg.Addr)
	}
	if len(cfg.Sources) != 4 {
		t.Fatalf("Sources 数量 = %d, 期望 4", len(cfg.Sources))
	}

	sq := cfg.Sources[0]
	if sq.Name != "local_sqlite" || sq.Type != "sqlite" {
		t.Errorf("source[0] name/type 错误: %+v", sq)
	}
	if sq.Incremental != "column:updated_at" {
		t.Errorf("Incremental = %q", sq.Incremental)
	}
	if len(sq.Tables) != 2 {
		t.Fatalf("sqlite Tables 数量 = %d, 期望 2", len(sq.Tables))
	}
	if sq.Tables[1].Source != "orders" || sq.Tables[1].Target != "orders_v2" || sq.Tables[1].PrimaryKey != "order_id" {
		t.Errorf("Tables[1] 错误: %+v", sq.Tables[1])
	}

	cs := cfg.Sources[1]
	if cs.Type != "csv" || cs.Table != "csv_users" || cs.PrimaryKey != "id" {
		t.Errorf("csv source 错误: %+v", cs)
	}
	if cs.Options["delimiter"] != "," {
		t.Errorf("csv delimiter = %q", cs.Options["delimiter"])
	}

	js := cfg.Sources[2]
	if js.Type != "json" || js.Options["root"] != "data.items" {
		t.Errorf("json source 错误: %+v", js)
	}

	ds := cfg.Sources[3]
	if ds.Type != "dir" || ds.Table != "files" {
		t.Errorf("dir source 错误: %+v", ds)
	}

	if len(cfg.Views) != 1 || cfg.Views[0].Name != "v_users" {
		t.Errorf("Views 错误: %+v", cfg.Views)
	}
	if len(cfg.Jobs) != 2 || cfg.Jobs[0].Name != "job_all" {
		t.Errorf("Jobs 错误: %+v", cfg.Jobs)
	}
	if cfg.Jobs[0].Interval != "1m" || len(cfg.Jobs[0].Sources) != 2 {
		t.Errorf("Job[0] 错误: %+v", cfg.Jobs[0])
	}

	if cfg.Sync.Conflict != "priority" {
		t.Errorf("Sync.Conflict = %q", cfg.Sync.Conflict)
	}
	if len(cfg.Sync.Priority) != 2 {
		t.Errorf("Sync.Priority = %v", cfg.Sync.Priority)
	}
	if !cfg.Sync.SoftDelete {
		t.Errorf("Sync.SoftDelete 应为 true")
	}
}

func TestLoadInvalidType(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mortise.yaml")
	content := `
version: 1
database: "./data/test.db"
addr: ":8421"
sources:
  - name: bad
    type: "postgres"
    path: "./data/x"
    table: "t"
    primary_key: "id"
`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 YAML 失败: %v", err)
	}
	if _, err := Load(path); err == nil {
		t.Fatalf("非法 type 应返回错误")
	}
}

func TestSourceByName(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mortise.yaml")
	content := `
version: 1
database: "./data/test.db"
addr: ":8421"
sources:
  - name: a
    type: csv
    path: "./a.csv"
    table: "a"
    primary_key: "id"
  - name: b
    type: dir
    path: "./b"
    table: "b"
    primary_key: "path"
`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 YAML 失败: %v", err)
	}
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if got := cfg.SourceByName("a"); got == nil || got.Name != "a" {
		t.Errorf("SourceByName(a) = %+v", got)
	}
	if got := cfg.SourceByName("nope"); got != nil {
		t.Errorf("SourceByName(nope) 应为 nil, 得到 %+v", got)
	}
}

func TestLoadEnvOverride(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mortise.yaml")
	content := `
version: 1
database: "./data/test.db"
addr: ":8421"
sources:
  - name: a
    type: csv
    path: "./a.csv"
    table: "a"
    primary_key: "id"
`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 YAML 失败: %v", err)
	}
	t.Setenv("MORTISE_ADDR", ":7777")
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.Addr != ":7777" {
		t.Errorf("MORTISE_ADDR 未覆盖: Addr = %q", cfg.Addr)
	}
}
