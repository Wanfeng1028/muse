package config

import (
	"strings"
	"testing"
)

func TestPGSource_MissingConnStr(t *testing.T) {
	body := `
version: 1
sources:
  - name: pgmain
    type: pg
    incremental: "column:updated_at"
    tables:
      - source: orders
        target: orders
        primary_key: order_id
`
	p := writeTempYAML(t, "pg_missing_connstr.yaml", body)
	if _, err := Load(p); err == nil {
		t.Fatalf("pg 缺少 options.conn_str 应报错")
	} else if !strings.Contains(err.Error(), "缺少 options.conn_str") {
		t.Fatalf("错误信息应含\"缺少 options.conn_str\"，实际: %v", err)
	}
}

func TestPGSource_MissingTablesAndTable(t *testing.T) {
	body := `
version: 1
sources:
  - name: pgmain
    type: pg
    incremental: "column:updated_at"
    options:
      conn_str: "postgres://u:p@127.0.0.1:5432/db"
`
	p := writeTempYAML(t, "pg_missing_tables.yaml", body)
	if _, err := Load(p); err == nil {
		t.Fatalf("pg 缺少 tables 或 table+primary_key 应报错")
	} else if !strings.Contains(err.Error(), "必须填写 tables 或 table+primary_key") {
		t.Fatalf("错误信息应含\"必须填写 tables 或 table+primary_key\"，实际: %v", err)
	}
}

func TestPGSource_TargetRenameRejected(t *testing.T) {
	body := `
version: 1
sources:
  - name: pgmain
    type: pg
    incremental: "column:updated_at"
    tables:
      - source: orders
        target: orders_renamed
        primary_key: order_id
    options:
      conn_str: "postgres://u:p@127.0.0.1:5432/db"
`
	p := writeTempYAML(t, "pg_target_rename.yaml", body)
	if _, err := Load(p); err == nil {
		t.Fatalf("pg 表改名应报错")
	} else if !strings.Contains(err.Error(), "暂不支持表改名") {
		t.Fatalf("错误信息应含\"暂不支持表改名\"，实际: %v", err)
	}
}

func TestPGSource_NoPathRequired(t *testing.T) {
	body := `
version: 1
sources:
  - name: pgmain
    type: pg
    incremental: "column:updated_at"
    tables:
      - source: orders
        target: orders
        primary_key: order_id
    options:
      conn_str: "postgres://u:p@127.0.0.1:5432/db"
`
	p := writeTempYAML(t, "pg_no_path.yaml", body)
	if _, err := Load(p); err != nil {
		t.Fatalf("pg 合法配置不应要求 path，实际报错: %v", err)
	}
}

func TestPGSource_ValidTablesForm(t *testing.T) {
	body := `
version: 1
sources:
  - name: pgmain
    type: pg
    incremental: "column:updated_at"
    tables:
      - source: orders
        target: orders
        primary_key: order_id
    options:
      conn_str: "postgres://u:p@127.0.0.1:5432/db"
`
	p := writeTempYAML(t, "pg_valid_tables.yaml", body)
	if _, err := Load(p); err != nil {
		t.Fatalf("pg tables 写法合法配置应通过，实际报错: %v", err)
	}
}

func TestPGSource_ValidTablePrimaryKeyForm(t *testing.T) {
	body := `
version: 1
sources:
  - name: pgmain
    type: pg
    incremental: "column:updated_at"
    table: orders
    primary_key: order_id
    options:
      conn_str: "postgres://u:p@127.0.0.1:5432/db"
`
	p := writeTempYAML(t, "pg_valid_table_pk.yaml", body)
	if _, err := Load(p); err != nil {
		t.Fatalf("pg table+primary_key 写法合法配置应通过，实际报错: %v", err)
	}
}
