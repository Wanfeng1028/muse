package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestIncrR2B21ReorderedRowsAllSkipped(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	round1 := "id,name,updated_at\n" +
		"1,alpha,2026-10-20 10:00:00\n" +
		"2,bravo,2026-10-20 11:00:00\n" +
		"3,charlie,2026-10-20 12:00:00\n" +
		"4,delta,2026-10-20 13:00:00\n" +
		"5,echo,2026-10-20 14:00:00\n"
	p := writeCSVStr(t, t.TempDir(), "round1.csv", round1)
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: ""}

	stats1 := runSync(t, st, src, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 5 {
		t.Fatalf("round1 Inserted = %d, want 5", ts1.Inserted)
	}

	round2 := "id,name,updated_at\n" +
		"5,echo,2026-10-20 14:00:00\n" +
		"3,charlie,2026-10-20 12:00:00\n" +
		"1,alpha,2026-10-20 10:00:00\n" +
		"4,delta,2026-10-20 13:00:00\n" +
		"2,bravo,2026-10-20 11:00:00\n"
	p2 := writeCSVStr(t, t.TempDir(), "round2.csv", round2)
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: ""}

	stats2 := runSync(t, st, src2, "job1")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 0 {
		t.Fatalf("round2 Inserted = %d, want 0", ts2.Inserted)
	}
	if ts2.Skipped != 5 {
		t.Fatalf("round2 Skipped = %d, want 5", ts2.Skipped)
	}
}

func TestIncrR2B21ReorderedWithOneChanged(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	round1 := "id,name,updated_at\n" +
		"1,alpha,2026-10-20 10:00:00\n" +
		"2,bravo,2026-10-20 11:00:00\n" +
		"3,charlie,2026-10-20 12:00:00\n" +
		"4,delta,2026-10-20 13:00:00\n" +
		"5,echo,2026-10-20 14:00:00\n"
	p := writeCSVStr(t, t.TempDir(), "round1.csv", round1)
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: ""}

	stats1 := runSync(t, st, src, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 5 {
		t.Fatalf("round1 Inserted = %d, want 5", ts1.Inserted)
	}

	round2 := "id,name,updated_at\n" +
		"5,echo,2026-10-20 14:00:00\n" +
		"3,charlie,2026-10-20 12:00:00\n" +
		"1,alpha,2026-10-20 10:00:00\n" +
		"4,delta,2026-10-20 13:00:00\n" +
		"2,bravo,2026-10-20 11:00:00\n"
	p2 := writeCSVStr(t, t.TempDir(), "round2.csv", round2)
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: ""}

	stats2 := runSync(t, st, src2, "job1")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 0 {
		t.Fatalf("round2 Inserted = %d, want 0", ts2.Inserted)
	}
	if ts2.Skipped != 5 {
		t.Fatalf("round2 Skipped = %d, want 5", ts2.Skipped)
	}

	round3 := "id,name,updated_at\n" +
		"5,echo,2026-10-20 14:00:00\n" +
		"3,charlie-modified,2026-10-20 12:00:00\n" +
		"1,alpha,2026-10-20 10:00:00\n" +
		"4,delta,2026-10-20 13:00:00\n" +
		"2,bravo,2026-10-20 11:00:00\n"
	p3 := writeCSVStr(t, t.TempDir(), "round3.csv", round3)
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: p3, Table: "t", PrimaryKey: "id", Incremental: ""}

	stats3 := runSync(t, st, src3, "job1")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Updated != 1 {
		t.Fatalf("round3 Updated = %d, want 1", ts3.Updated)
	}
	if ts3.Skipped != 4 {
		t.Fatalf("round3 Skipped = %d, want 4", ts3.Skipped)
	}
}
