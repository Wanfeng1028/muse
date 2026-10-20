package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B10DriftClearsWatermarkAndOldRows(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	csv1 := "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:00\n"
	p1 := writeCSVStr(t, dir, "round1.csv", csv1)

	src := config.SourceConfig{
		Name:        "s1",
		Type:        "csv",
		Path:        p1,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}

	stats1 := runSync(t, st, src, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("round1 inserted = %d, want 2", ts1.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round1: %v", err)
	}
	if wm1 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round1 watermark = %q, want %q", wm1, "2026-10-20T10:00:00Z")
	}

	cnt1, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("table count round1: %v", err)
	}
	if cnt1 != 2 {
		t.Fatalf("round1 table count = %d, want 2", cnt1)
	}

	csv2 := "id,name\n1,alice\n2,bob\n3,carol\n"
	p2 := writeCSVStr(t, dir, "round2.csv", csv2)

	src2 := config.SourceConfig{
		Name:        "s1",
		Type:        "csv",
		Path:        p2,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}

	stats2 := runSync(t, st, src2, "job1")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 3 {
		t.Fatalf("round2 inserted = %d, want 3", ts2.Inserted)
	}

	cnt2, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("table count round2: %v", err)
	}
	if cnt2 != 3 {
		t.Fatalf("round2 table count = %d, want 3 (old 2 rows cleared)", cnt2)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round2: %v", err)
	}
	if wm2 != "" {
		t.Fatalf("round2 drifted watermark = %q, want empty", wm2)
	}
}

func TestWmR2B10DriftDoesNotTouchOtherSource(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	csv1 := "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:00\n"
	p1 := writeCSVStr(t, dir, "s1round1.csv", csv1)

	src1 := config.SourceConfig{
		Name:        "s1",
		Type:        "csv",
		Path:        p1,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	stats1 := runSync(t, st, src1, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("s1 round1 inserted = %d, want 2", ts1.Inserted)
	}

	csv1b := "id,name\n1,alice\n2,bob\n3,carol\n"
	p1b := writeCSVStr(t, dir, "s1round2.csv", csv1b)

	src1b := config.SourceConfig{
		Name:        "s1",
		Type:        "csv",
		Path:        p1b,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	stats1b := runSync(t, st, src1b, "job1")
	ts1b := tableStat(t, stats1b, "t")
	if ts1b.Inserted != 3 {
		t.Fatalf("s1 round2 inserted = %d, want 3", ts1b.Inserted)
	}

	cntBefore, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("table count before s2: %v", err)
	}
	if cntBefore != 3 {
		t.Fatalf("table count before s2 = %d, want 3", cntBefore)
	}

	csv2 := "id,name\n101,dave\n102,erin\n"
	p2 := writeCSVStr(t, dir, "s2.csv", csv2)

	src2 := config.SourceConfig{
		Name:        "s2",
		Type:        "csv",
		Path:        p2,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "",
	}
	stats2 := runSync(t, st, src2, "job2")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 2 {
		t.Fatalf("s2 inserted = %d, want 2", ts2.Inserted)
	}

	cntAfter, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("table count after s2: %v", err)
	}
	if cntAfter != 5 {
		t.Fatalf("table count after s2 = %d, want 5 (s1 rows untouched)", cntAfter)
	}

}
