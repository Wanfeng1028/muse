package pgsource

import (
	"context"
	"strings"
	"testing"
	"time"
)

func TestDeep2MapPGType_Table(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"text", "TEXT"},
		{"VARCHAR", "TEXT"},
		{"character varying", "TEXT"},
		{"char", "TEXT"},
		{"character", "TEXT"},
		{"json", "TEXT"},
		{"jsonb", "TEXT"},
		{"uuid", "TEXT"},
		{"inet", "TEXT"},
		{"cidr", "TEXT"},
		{"macaddr", "TEXT"},
		{"int2", "INTEGER"},
		{"int4", "INTEGER"},
		{"Int8", "INTEGER"},
		{"smallint", "INTEGER"},
		{"integer", "INTEGER"},
		{"bigint", "INTEGER"},
		{"serial", "INTEGER"},
		{"bigserial", "INTEGER"},
		{"numeric", "REAL"},
		{"decimal", "REAL"},
		{"real", "REAL"},
		{"float4", "REAL"},
		{"float8", "REAL"},
		{"Double Precision", "REAL"},
		{"bool", "BOOLEAN"},
		{"boolean", "BOOLEAN"},
		{"timestamp", "DATETIME"},
		{"TIMESTAMPTZ", "DATETIME"},
		{"date", "DATETIME"},
		{"time", "DATETIME"},
		{"timetz", "DATETIME"},
		{"interval", "DATETIME"},
		{"bytea", "BLOB"},
		{"point", "TEXT"},
		{"mytype", "TEXT"},
		{"", "TEXT"},
	}
	for _, c := range cases {
		got := MapPGType(c.in)
		if got != c.want {
			t.Errorf("MapPGType(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestDeep2AssertReadOnlySQL(t *testing.T) {
	ok := []string{
		"SELECT 1",
		" select a from t",
		"WITH x AS (SELECT 1) SELECT * FROM x",
		"SeLeCt 1",
	}
	for _, q := range ok {
		if err := AssertReadOnlySQL(q); err != nil {
			t.Errorf("AssertReadOnlySQL(%q) = %v, want nil", q, err)
		}
	}

	bad := []string{
		"INSERT INTO t VALUES(1)",
		"update t set a=1",
		"DELETE FROM t",
		"DROP TABLE t",
		"SELECT 1; DELETE FROM t",
		"SELECT 1;",
		"",
		" ",
	}
	for _, q := range bad {
		err := AssertReadOnlySQL(q)
		if err == nil {
			t.Errorf("AssertReadOnlySQL(%q) = nil, want error", q)
			continue
		}
		if !strings.Contains(err.Error(), "只读") {
			t.Errorf("AssertReadOnlySQL(%q) error = %q, want contains 只读", q, err.Error())
		}
	}
}

func TestDeep2CursorAdvance(t *testing.T) {
	t1 := time.Date(2026, 1, 2, 10, 0, 0, 0, time.UTC)
	t2 := time.Date(2026, 1, 2, 10, 1, 0, 0, time.UTC)
	t0 := time.Date(2026, 1, 2, 9, 0, 0, 0, time.UTC)

	var cur Cursor
	if !cur.Advance(t1, "a") {
		t.Fatalf("zero cursor Advance(t1,a) = false, want true")
	}
	if !cur.UpdatedAt.Equal(t1) || cur.LastPK != "a" {
		t.Fatalf("cursor after first advance = %v/%q, want t1/a", cur.UpdatedAt, cur.LastPK)
	}

	if !cur.Advance(t1, "b") {
		t.Fatalf("Advance(same time, larger pk) = false, want true")
	}
	if cur.LastPK != "b" {
		t.Fatalf("LastPK after larger pk = %q, want b", cur.LastPK)
	}

	before := cur
	if cur.Advance(t1, "a") {
		t.Fatalf("Advance(same time, smaller pk) = true, want false")
	}
	if !cur.UpdatedAt.Equal(before.UpdatedAt) || cur.LastPK != before.LastPK {
		t.Fatalf("cursor changed on rejected advance: %v/%q", cur.UpdatedAt, cur.LastPK)
	}

	if cur.Advance(t0, "z") {
		t.Fatalf("Advance(earlier time) = true, want false")
	}
	if !cur.UpdatedAt.Equal(before.UpdatedAt) || cur.LastPK != before.LastPK {
		t.Fatalf("cursor changed on earlier time: %v/%q", cur.UpdatedAt, cur.LastPK)
	}

	if !cur.Advance(t2, "a") {
		t.Fatalf("Advance(later time) = false, want true")
	}
	if !cur.UpdatedAt.Equal(t2) || cur.LastPK != "a" {
		t.Fatalf("cursor after later time = %v/%q, want t2/a", cur.UpdatedAt, cur.LastPK)
	}
}

func TestDeep2ConfigValidate(t *testing.T) {
	cfg := Config{ConnStr: "", Tables: []string{"t"}, CursorColumn: "", BatchSize: 0}
	if err := cfg.Validate(); err == nil {
		t.Fatalf("empty ConnStr Validate = nil, want error")
	}

	cfg = Config{ConnStr: "postgres://u:p@h:5432/db", Tables: nil, CursorColumn: "", BatchSize: 0}
	if err := cfg.Validate(); err == nil {
		t.Fatalf("empty Tables Validate = nil, want error")
	}

	cfg = Config{ConnStr: "mysql://x", Tables: []string{"t"}, CursorColumn: "", BatchSize: 0}
	if err := cfg.Validate(); err == nil {
		t.Fatalf("mysql scheme Validate = nil, want error")
	}

	cfg = Config{ConnStr: "postgres://u:p@h:5432/db", Tables: []string{"t"}, CursorColumn: "", BatchSize: 0}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("valid config Validate = %v, want nil", err)
	}
	if cfg.CursorColumn != "updated_at" {
		t.Fatalf("CursorColumn = %q, want updated_at", cfg.CursorColumn)
	}
	if cfg.BatchSize != 1000 {
		t.Fatalf("BatchSize = %d, want 1000", cfg.BatchSize)
	}
}

func TestDeep2EnsureReadOnlyConnStr(t *testing.T) {
	got, err := EnsureReadOnlyConnStr("postgres://u:p@h:5432/db")
	if err != nil {
		t.Fatalf("EnsureReadOnlyConnStr(postgres) = %v, want nil", err)
	}
	if !strings.Contains(got, "default_transaction_read_only=on") {
		t.Fatalf("EnsureReadOnlyConnStr(postgres) = %q, want contains default_transaction_read_only=on", got)
	}

	got, err = EnsureReadOnlyConnStr("postgres://u:p@h:5432/db?default_transaction_read_only=off")
	if err != nil {
		t.Fatalf("EnsureReadOnlyConnStr(existing) = %v, want nil", err)
	}
	if !strings.Contains(got, "default_transaction_read_only=off") {
		t.Fatalf("EnsureReadOnlyConnStr(existing) = %q, want keep off", got)
	}
	if strings.Contains(got, "default_transaction_read_only=on") {
		t.Fatalf("EnsureReadOnlyConnStr(existing) = %q, must not overwrite to on", got)
	}

	if _, err := EnsureReadOnlyConnStr("mysql://h/db"); err == nil {
		t.Fatalf("EnsureReadOnlyConnStr(mysql) = nil, want error")
	}

	if _, err := EnsureReadOnlyConnStr(""); err == nil {
		t.Fatalf("EnsureReadOnlyConnStr(empty) = nil, want error")
	}
}

func TestDeep2FakePullTablesDeepCopy(t *testing.T) {
	cfg := Config{ConnStr: "postgres://u:p@h:5432/db", Tables: []string{"orders"}, CursorColumn: "updated_at", BatchSize: 10}
	schemas := []TableSchema{
		{
			Name:       "orders",
			PrimaryKey: "id",
			Columns: []Column{
				{Name: "id", PGType: "int8", MortiseType: "INTEGER"},
				{Name: "updated_at", PGType: "timestamptz", MortiseType: "DATETIME"},
			},
		},
	}
	src := NewFakeSource(cfg, schemas, nil, map[string]string{"orders": "id"}, map[string]string{"orders": "updated_at"})

	ctx := context.Background()
	first, err := src.PullTables(ctx)
	if err != nil {
		t.Fatalf("PullTables first = %v, want nil", err)
	}
	if len(first) != 1 || len(first[0].Columns) == 0 {
		t.Fatalf("PullTables first shape unexpected: %#v", first)
	}
	first[0].Columns[0].Name = "polluted"
	first[0].Name = "polluted_table"

	second, err := src.PullTables(ctx)
	if err != nil {
		t.Fatalf("PullTables second = %v, want nil", err)
	}
	if second[0].Columns[0].Name != "id" {
		t.Fatalf("internal columns polluted: %q", second[0].Columns[0].Name)
	}
	if second[0].Name != "orders" {
		t.Fatalf("internal table name polluted: %q", second[0].Name)
	}
}

func deep2Rows() map[string][]Row {
	mk := func(id string, ts time.Time) Row {
		return Row{
			"id":         id,
			"updated_at": ts.Format(time.RFC3339),
		}
	}
	t10_00 := time.Date(2026, 1, 2, 10, 0, 0, 0, time.UTC)
	t10_01 := time.Date(2026, 1, 2, 10, 1, 0, 0, time.UTC)
	t10_02 := time.Date(2026, 1, 2, 10, 2, 0, 0, time.UTC)
	t10_03 := time.Date(2026, 1, 2, 10, 3, 0, 0, time.UTC)
	return map[string][]Row{
		"orders": {
			mk("a", t10_00),
			mk("b", t10_00),
			mk("c", t10_01),
			mk("d", t10_02),
			mk("e", t10_03),
		},
	}
}

func deep2Source(t *testing.T, batch int) *FakeSource {
	t.Helper()
	cfg := Config{
		ConnStr:      "postgres://u:p@h:5432/db",
		Tables:       []string{"orders"},
		CursorColumn: "updated_at",
		BatchSize:    batch,
	}
	schemas := []TableSchema{
		{
			Name:       "orders",
			PrimaryKey: "id",
			Columns: []Column{
				{Name: "id", PGType: "int8", MortiseType: "INTEGER"},
				{Name: "updated_at", PGType: "timestamptz", MortiseType: "DATETIME"},
			},
		},
	}
	return NewFakeSource(cfg, schemas, deep2Rows(), map[string]string{"orders": "id"}, map[string]string{"orders": "updated_at"})
}

func deep2IDs(rows []Row) []string {
	out := make([]string, 0, len(rows))
	for _, r := range rows {
		if v, ok := r["id"].(string); ok {
			out = append(out, v)
		}
	}
	return out
}

func deep2Eq(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestDeep2FakePullRowsCursor(t *testing.T) {
	src := deep2Source(t, 10)
	ctx := context.Background()

	t10_00 := time.Date(2026, 1, 2, 10, 0, 0, 0, time.UTC)
	t10_03 := time.Date(2026, 1, 2, 10, 3, 0, 0, time.UTC)

	var zero Cursor
	rows, err := src.PullRows(ctx, "orders", zero)
	if err != nil {
		t.Fatalf("PullRows zero = %v, want nil", err)
	}
	if got := deep2IDs(rows); !deep2Eq(got, []string{"a", "b", "c", "d", "e"}) {
		t.Fatalf("PullRows zero ids = %v, want [a b c d e]", got)
	}

	since := Cursor{UpdatedAt: t10_00, LastPK: "a"}
	rows, err = src.PullRows(ctx, "orders", since)
	if err != nil {
		t.Fatalf("PullRows since(t10_00,a) = %v, want nil", err)
	}
	if got := deep2IDs(rows); !deep2Eq(got, []string{"b", "c", "d", "e"}) {
		t.Fatalf("PullRows since(t10_00,a) ids = %v, want [b c d e]", got)
	}

	since = Cursor{UpdatedAt: t10_03, LastPK: "e"}
	rows, err = src.PullRows(ctx, "orders", since)
	if err != nil {
		t.Fatalf("PullRows since(t10_03,e) = %v, want nil", err)
	}
	if len(rows) != 0 {
		t.Fatalf("PullRows since(t10_03,e) len = %d, want 0", len(rows))
	}
}

func TestDeep2FakePullRowsBatchLimit(t *testing.T) {
	src := deep2Source(t, 2)
	ctx := context.Background()

	var cur Cursor
	page1, err := src.PullRows(ctx, "orders", cur)
	if err != nil {
		t.Fatalf("page1 = %v, want nil", err)
	}
	if got := deep2IDs(page1); !deep2Eq(got, []string{"a", "b"}) {
		t.Fatalf("page1 ids = %v, want [a b]", got)
	}
	for _, r := range page1 {
		ts, err := time.Parse(time.RFC3339, r["updated_at"].(string))
		if err != nil {
			t.Fatalf("parse page1 updated_at: %v", err)
		}
		cur.Advance(ts, r["id"].(string))
	}

	page2, err := src.PullRows(ctx, "orders", cur)
	if err != nil {
		t.Fatalf("page2 = %v, want nil", err)
	}
	if got := deep2IDs(page2); !deep2Eq(got, []string{"c", "d"}) {
		t.Fatalf("page2 ids = %v, want [c d]", got)
	}
	for _, r := range page2 {
		ts, err := time.Parse(time.RFC3339, r["updated_at"].(string))
		if err != nil {
			t.Fatalf("parse page2 updated_at: %v", err)
		}
		cur.Advance(ts, r["id"].(string))
	}

	page3, err := src.PullRows(ctx, "orders", cur)
	if err != nil {
		t.Fatalf("page3 = %v, want nil", err)
	}
	if got := deep2IDs(page3); !deep2Eq(got, []string{"e"}) {
		t.Fatalf("page3 ids = %v, want [e]", got)
	}
}

func TestDeep2FakePullRowsUnknownTable(t *testing.T) {
	src := deep2Source(t, 10)
	ctx := context.Background()
	if _, err := src.PullRows(ctx, "unknown_table", Cursor{}); err == nil {
		t.Fatalf("PullRows(unknown) = nil, want error")
	}
}

func TestDeep2FakeAdvanceCursor(t *testing.T) {
	src := deep2Source(t, 10)
	t10_03 := time.Date(2026, 1, 2, 10, 3, 0, 0, time.UTC)

	var cur Cursor
	if err := src.AdvanceCursor("orders", &cur); err != nil {
		t.Fatalf("AdvanceCursor = %v, want nil", err)
	}
	if !cur.UpdatedAt.Equal(t10_03) {
		t.Fatalf("Advanced UpdatedAt = %v, want %v", cur.UpdatedAt, t10_03)
	}
	if cur.LastPK != "e" {
		t.Fatalf("Advanced LastPK = %q, want e", cur.LastPK)
	}
}

func TestDeep2FakeClose(t *testing.T) {
	src := deep2Source(t, 10)
	if err := src.Close(); err != nil {
		t.Fatalf("Close() = %v, want nil", err)
	}
}
