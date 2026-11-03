package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B02WhitespaceWatermarkHealsToFullSync(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	if err := st.SetWatermark("s1", "t", "updated_at", "   "); err != nil {
		t.Fatalf("set watermark: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 12:00:00\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "job1")

	ts := tableStat(t, stats, "t")
	if ts.Inserted != 3 {
		t.Fatalf("inserted = %d, want 3 (blank watermark must trigger full sync)", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2026-10-20T12:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T12:00:00Z")
	}
}

func TestWmR2B02TabNewlineWatermarkHeals(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	if err := st.SetWatermark("s1", "t", "updated_at", "\t\n"); err != nil {
		t.Fatalf("set watermark: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 12:00:00\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "job1")

	ts := tableStat(t, stats, "t")
	if ts.Inserted != 3 {
		t.Fatalf("inserted = %d, want 3 (tab/newline watermark must trigger full sync)", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2026-10-20T12:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T12:00:00Z")
	}
}

func TestWmR2B02BlankEqualsAbsent(t *testing.T) {
	stAbsent, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store absent: %v", err)
	}
	if err := stAbsent.Migrate(); err != nil {
		t.Fatalf("migrate absent: %v", err)
	}

	wmAbsent, err := stAbsent.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark absent: %v", err)
	}
	if wmAbsent != "" {
		t.Fatalf("watermark absent = %q, want empty", wmAbsent)
	}

	stBlank, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store blank: %v", err)
	}
	if err := stBlank.Migrate(); err != nil {
		t.Fatalf("migrate blank: %v", err)
	}
	if err := stBlank.SetWatermark("s1", "t", "updated_at", "   "); err != nil {
		t.Fatalf("set watermark blank: %v", err)
	}

	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 12:00:00\n"
	pAbsent := writeCSVStr(t, dir, "absent.csv", content)
	pBlank := writeCSVStr(t, dir, "blank.csv", content)

	srcAbsent := config.SourceConfig{Type: "csv", Name: "s1", Path: pAbsent, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	statsAbsent := runSync(t, stAbsent, srcAbsent, "job1")
	tsAbsent := tableStat(t, statsAbsent, "t")

	srcBlank := config.SourceConfig{Type: "csv", Name: "s1", Path: pBlank, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	statsBlank := runSync(t, stBlank, srcBlank, "job1")
	tsBlank := tableStat(t, statsBlank, "t")

	if tsAbsent.Inserted != 3 {
		t.Fatalf("inserted absent = %d, want 3", tsAbsent.Inserted)
	}
	if tsAbsent.Inserted != tsBlank.Inserted {
		t.Fatalf("inserted absent = %d, inserted blank = %d, want equal", tsAbsent.Inserted, tsBlank.Inserted)
	}

	wmAbsentFinal, err := stAbsent.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark absent final: %v", err)
	}
	wmBlankFinal, err := stBlank.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark blank final: %v", err)
	}
	if wmAbsentFinal != wmBlankFinal {
		t.Fatalf("watermark absent = %q, watermark blank = %q, want equal", wmAbsentFinal, wmBlankFinal)
	}
	if wmAbsentFinal != "2026-10-20T12:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wmAbsentFinal, "2026-10-20T12:00:00Z")
	}
}
