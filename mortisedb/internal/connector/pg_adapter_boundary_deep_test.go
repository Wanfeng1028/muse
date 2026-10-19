package connector

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/pgsource"
)

// buildOrdersFake 造一个 orders 表的内存桩，三行数据，其中两行时间戳相同用来测边界。
func buildOrdersFake(t *testing.T) *pgsource.FakeSource {
	t.Helper()
	cfg := pgsource.Config{
		ConnStr:      "postgres://u:p@localhost:5432/db",
		Tables:       []string{"orders"},
		CursorColumn: "updated_at",
		BatchSize:    100,
	}
	schemas := []pgsource.TableSchema{
		{
			Name:       "orders",
			PrimaryKey: "id",
			Columns: []pgsource.Column{
				{Name: "id", PGType: "int8", MortiseType: "INTEGER"},
				{Name: "updated_at", PGType: "timestamptz", MortiseType: "DATETIME"},
				{Name: "name", PGType: "text", MortiseType: "TEXT"},
			},
		},
	}
	rows := map[string][]pgsource.Row{
		"orders": {
			{"id": "1", "updated_at": "2026-01-01T00:00:00Z", "name": "a"},
			{"id": "2", "updated_at": "2026-01-02T00:00:00Z", "name": "b"},
			{"id": "3", "updated_at": "2026-01-02T00:00:00Z", "name": "c"},
		},
	}
	pkCol := map[string]string{"orders": "id"}
	cursorCol := map[string]string{"orders": "updated_at"}
	return pgsource.NewFakeSource(cfg, schemas, rows, pkCol, cursorCol)
}

// TestPGAdapterTablesMapping 表结构要正确映射到 connector.TableInfo。
func TestPGAdapterTablesMapping(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg1", fake, "updated_at")

	tables, err := a.Tables()
	if err != nil {
		t.Fatalf("Tables 不应报错: %v", err)
	}
	if len(tables) != 1 {
		t.Fatalf("应当只有 1 张表，实际 %d 张", len(tables))
	}
	tb := tables[0]
	if tb.Name != "orders" {
		t.Fatalf("Name 应当为 orders，实际: %q", tb.Name)
	}
	if tb.SourceTable != "orders" {
		t.Fatalf("SourceTable 应当为 orders，实际: %q", tb.SourceTable)
	}
	if tb.Primary != "id" {
		t.Fatalf("Primary 应当为 id，实际: %q", tb.Primary)
	}
	want := []struct {
		name string
		typ  string
	}{
		{"id", "INTEGER"},
		{"updated_at", "DATETIME"},
		{"name", "TEXT"},
	}
	if len(tb.Columns) != len(want) {
		t.Fatalf("列数应当为 %d，实际 %d", len(want), len(tb.Columns))
	}
	for i, w := range want {
		if tb.Columns[i].Name != w.name {
			t.Fatalf("第 %d 列名应当为 %q，实际: %q", i, w.name, tb.Columns[i].Name)
		}
		if tb.Columns[i].Type != w.typ {
			t.Fatalf("第 %d 列类型应当为 %q，实际: %q", i, w.typ, tb.Columns[i].Type)
		}
	}
}

// TestPGAdapterRowsSinceFilter since 里的游标时间要能过滤掉更早的行。
func TestPGAdapterRowsSinceFilter(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg1", fake, "updated_at")

	rows, err := a.Rows("orders", map[string]string{"updated_at": "2026-01-01T12:00:00Z"})
	if err != nil {
		t.Fatalf("Rows 不应报错: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("应当返回 2 行，实际 %d 行", len(rows))
	}
	if rows[0]["id"] != "2" {
		t.Fatalf("第 1 行 id 应当为 2，实际: %v", rows[0]["id"])
	}
	if rows[1]["id"] != "3" {
		t.Fatalf("第 2 行 id 应当为 3，实际: %v", rows[1]["id"])
	}
}

// TestPGAdapterRowsCursorAccumulates 适配器内部会缓存游标。
// 第一次 Rows(nil) 从零开始拉全部三行，拉完游标推到最后一行的 (时间, 主键)。
// 第二次 Rows(nil) 因为 since 是 nil，用内部缓存的游标，所以一行都拉不到。
func TestPGAdapterRowsCursorAccumulates(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg1", fake, "updated_at")

	first, err := a.Rows("orders", nil)
	if err != nil {
		t.Fatalf("第一次 Rows 不应报错: %v", err)
	}
	if len(first) != 3 {
		t.Fatalf("第一次应当返回 3 行，实际 %d 行", len(first))
	}

	second, err := a.Rows("orders", nil)
	if err != nil {
		t.Fatalf("第二次 Rows 不应报错: %v", err)
	}
	if len(second) != 0 {
		t.Fatalf("第二次应当返回 0 行（内部游标已推进到最后），实际 %d 行", len(second))
	}
}

// TestPGAdapterRowsPKBoundary 同一时间戳下用主键边界区分。
func TestPGAdapterRowsPKBoundary(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg1", fake, "updated_at")

	rows, err := a.Rows("orders", map[string]string{
		"updated_at":    "2026-01-02T00:00:00Z",
		"updated_at:pk": "2",
	})
	if err != nil {
		t.Fatalf("Rows 不应报错: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("应当只返回 1 行，实际 %d 行", len(rows))
	}
	if rows[0]["id"] != "3" {
		t.Fatalf("应当返回 id 为 3 的行，实际: %v", rows[0]["id"])
	}
}

// TestPGAdapterRowsUnknownTable 不存在的表要报错。
func TestPGAdapterRowsUnknownTable(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg1", fake, "updated_at")

	if _, err := a.Rows("nope", nil); err == nil {
		t.Fatalf("未知表应当返回错误")
	}
}

// TestPGAdapterNameClose 名字和关闭要透传到底层。
func TestPGAdapterNameClose(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg1", fake, "updated_at")

	if got := a.Name(); got != "pg1" {
		t.Fatalf("Name 应当为 pg1，实际: %q", got)
	}
	if err := a.Close(); err != nil {
		t.Fatalf("Close 应当返回 nil，实际: %v", err)
	}
}

// TestPGAdapterDefaultCursorColumn cursorCol 传空时默认用 updated_at。
func TestPGAdapterDefaultCursorColumn(t *testing.T) {
	fake := buildOrdersFake(t)
	a := NewPGAdapter("pg2", fake, "")

	rows, err := a.Rows("orders", map[string]string{"updated_at": "2026-01-01T12:00:00Z"})
	if err != nil {
		t.Fatalf("Rows 不应报错: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("默认游标列生效时应当返回 2 行，实际 %d 行", len(rows))
	}
}
