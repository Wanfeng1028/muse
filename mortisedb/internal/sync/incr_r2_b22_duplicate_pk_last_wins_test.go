package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestIncrR2B22DuplicatePKLastWins(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := writeCSVStr(t, t.TempDir(), "dup.csv", "id,name\n1,first\n1,second\n2,only\n")
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id"}
	stats := runSync(t, st, src, "job1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 2 {
		t.Fatalf("Inserted = %d, want 2", ts.Inserted)
	}
	if ts.Updated != 1 {
		t.Fatalf("Updated = %d, want 1", ts.Updated)
	}

	var name string
	if err := st.DB.QueryRow("SELECT \"name\" FROM \"t\" WHERE \"id\"='1'").Scan(&name); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if name != "second" {
		t.Fatalf("name = %q, want %q", name, "second")
	}
}

func TestIncrR2B22TripleDuplicatePK(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := writeCSVStr(t, t.TempDir(), "dup3.csv", "id,name\n1,v1\n1,v2\n1,v3\n")
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id"}
	stats := runSync(t, st, src, "job1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 1 {
		t.Fatalf("Inserted = %d, want 1", ts.Inserted)
	}
	if ts.Updated != 2 {
		t.Fatalf("Updated = %d, want 2", ts.Updated)
	}

	var name string
	if err := st.DB.QueryRow("SELECT \"name\" FROM \"t\" WHERE \"id\"='1'").Scan(&name); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if name != "v3" {
		t.Fatalf("name = %q, want %q", name, "v3")
	}
}
