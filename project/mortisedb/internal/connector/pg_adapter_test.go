package connector

import (
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/pgsource"
)

func buildFakeSource(t *testing.T) *pgsource.FakeSource {
	t.Helper()
	cfg := pgsource.Config{
		ConnStr:      "postgres://muse_reader:change_me@127.0.0.1:5432/target_db",
		Tables:       []string{"orders", "users"},
		CursorColumn: "updated_at",
		BatchSize:    1000,
	}
	schemas := []pgsource.TableSchema{
		{
			Name:       "orders",
			PrimaryKey: "order_id",
			Columns: []pgsource.Column{
				{Name: "order_id", MortiseType: "string"},
				{Name: "updated_at", MortiseType: "time"},
			},
		},
		{
			Name:       "users",
			PrimaryKey: "id",
			Columns: []pgsource.Column{
				{Name: "id", MortiseType: "string"},
				{Name: "updated_at", MortiseType: "time"},
			},
		},
	}
	rows := map[string][]pgsource.Row{
		"orders": {
			{"order_id": "o1", "updated_at": "2024-01-01T00:00:00Z"},
			{"order_id": "o2", "updated_at": "2024-01-02T00:00:00Z"},
		},
		"users": {
			{"id": "u1", "updated_at": "2024-02-01T00:00:00Z"},
		},
	}
	pkCol := map[string]string{
		"orders": "order_id",
		"users":  "id",
	}
	cursorCol := map[string]string{
		"orders": "updated_at",
		"users":  "updated_at",
	}
	return pgsource.NewFakeSource(cfg, schemas, rows, pkCol, cursorCol)
}

func TestPGAdapter_Tables(t *testing.T) {
	src := buildFakeSource(t)
	a := NewPGAdapter("pgmain", src, "")

	infos, err := a.Tables()
	if err != nil {
		t.Fatalf("Tables 失败: %v", err)
	}
	if len(infos) != 2 {
		t.Fatalf("期望 2 张表，实际 %d", len(infos))
	}
	if infos[0].Name != "orders" || infos[0].Primary != "order_id" {
		t.Fatalf("orders 表信息不符: %+v", infos[0])
	}
	if len(infos[0].Columns) != 2 {
		t.Fatalf("orders 期望 2 列，实际 %d", len(infos[0].Columns))
	}
	if infos[0].Columns[0].Name != "order_id" || infos[0].Columns[0].Type != "string" {
		t.Fatalf("orders 首列不符: %+v", infos[0].Columns[0])
	}
	if infos[1].Name != "users" || infos[1].Primary != "id" {
		t.Fatalf("users 表信息不符: %+v", infos[1])
	}
}

func TestPGAdapter_RowsIncrementalAndCursor(t *testing.T) {
	src := buildFakeSource(t)
	a := NewPGAdapter("pgmain", src, "")

	if _, err := a.Tables(); err != nil {
		t.Fatalf("Tables 失败: %v", err)
	}

	rows, err := a.Rows("orders", nil)
	if err != nil {
		t.Fatalf("首次 Rows 失败: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("首次期望 2 行，实际 %d", len(rows))
	}
	if rows[0]["order_id"] != "o1" || rows[1]["order_id"] != "o2" {
		t.Fatalf("首次行内容不符: %+v", rows)
	}

	rows2, err := a.Rows("orders", nil)
	if err != nil {
		t.Fatalf("第二次 Rows 失败: %v", err)
	}
	if len(rows2) != 0 {
		t.Fatalf("游标推进后第二次期望 0 行，实际 %d", len(rows2))
	}
}

func TestPGAdapter_UnknownTable(t *testing.T) {
	src := buildFakeSource(t)
	a := NewPGAdapter("pgmain", src, "")

	_, err := a.Rows("not_exist", nil)
	if err == nil {
		t.Fatalf("未知表期望报错，实际通过")
	}
}

func TestPGAdapter_Close(t *testing.T) {
	src := buildFakeSource(t)
	a := NewPGAdapter("pgmain", src, "")
	if err := a.Close(); err != nil {
		t.Fatalf("Close 失败: %v", err)
	}
}

func TestOpenPG_MissingConnStr(t *testing.T) {
	cfg := config.SourceConfig{
		Name: "pgmain",
		Type: "pg",
		Tables: []config.TableMap{
			{Source: "orders", Target: "orders", PrimaryKey: "order_id"},
		},
		Options: map[string]string{},
	}
	src, err := openPG(cfg)
	if err == nil {
		t.Fatalf("缺 conn_str 期望报错，实际通过")
	}
	if src != nil {
		t.Fatalf("出错时不应返回 Source")
	}
	if !strings.Contains(err.Error(), "conn_str") {
		t.Fatalf("错误信息不符: %v", err)
	}
}
