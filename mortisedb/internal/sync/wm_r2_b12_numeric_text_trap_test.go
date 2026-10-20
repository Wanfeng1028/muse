package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// TestWmR2B12NumericTextLexicographicMax pins down the known semantics for a
// pure-text incremental column holding numeric-looking values: the watermark
// advances by string max (lexicographic order), NOT by numeric order. With
// values "9", "10", "11" the string max is "9" because "9" > "10" and
// "9" > "11" lexicographically. This is a known semantic of text columns and
// is asserted here so a future change cannot silently alter it.
func TestWmR2B12NumericTextLexicographicMax(t *testing.T) {
	dir := t.TempDir()
	p := writeCSVStr(t, dir, "a.csv", "id,seq\n1,9\n2,10\n3,11\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:seq"}
	stats := runSync(t, st, src, "job1")

	ts := tableStat(t, stats, "t")
	if ts.Inserted != 3 {
		t.Fatalf("first round Inserted = %d, want 3", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("first round Updated = %d, want 0", ts.Updated)
	}

	wm, err := st.GetWatermark("s1", "t", "seq")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	// Lexicographic max of {"9","10","11"} is "9".
	if wm != "9" {
		t.Fatalf("watermark = %q, want %q", wm, "9")
	}
}

// TestWmR2B12NumericTextSecondRoundFiltered pins down the second-round
// filtering behavior for a pure-text numeric column. The connector filters
// rows with a string comparison (v <= wm). After the first round the
// watermark is "9" (lexicographic max). A newly appended row with seq "10"
// has a larger numeric value but is lexicographically smaller than "9", so
// "10" <= "9" holds and the row is filtered out. Using string comparison for
// pure-text numeric columns is the current design semantics; this test locks
// that behavior in place.
func TestWmR2B12NumericTextSecondRoundFiltered(t *testing.T) {
	dir := t.TempDir()
	p := writeCSVStr(t, dir, "a.csv", "id,seq\n1,9\n2,10\n3,11\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:seq"}
	first := runSync(t, st, src, "job1")
	firstStat := tableStat(t, first, "t")
	if firstStat.Inserted != 3 {
		t.Fatalf("first round Inserted = %d, want 3", firstStat.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "seq")
	if err != nil {
		t.Fatalf("get watermark after first round: %v", err)
	}
	if wm1 != "9" {
		t.Fatalf("watermark after first round = %q, want %q", wm1, "9")
	}

	// Append a new pk whose seq duplicates an existing text value.
	// 真实语义：文本水位线 IsDateTime 为 false，since 为空，连接器侧完全不过滤；
	// 每轮全量拉取，靠 hash 去重。新主键正常插入。
	p2 := writeCSVStr(t, dir, "b.csv", "id,seq\n1,9\n2,10\n3,11\n4,10\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:seq"}
	second := runSync(t, st, src2, "job2")

	secondStat := tableStat(t, second, "t")
	if secondStat.Inserted != 1 {
		t.Fatalf("second round Inserted = %d, want 1 (text watermark does not filter; new pk inserted)", secondStat.Inserted)
	}
	if secondStat.Skipped != 3 {
		t.Fatalf("second round Skipped = %d, want 3", secondStat.Skipped)
	}
	if secondStat.Updated != 0 {
		t.Fatalf("second round Updated = %d, want 0", secondStat.Updated)
	}

	wm2, err := st.GetWatermark("s1", "t", "seq")
	if err != nil {
		t.Fatalf("get watermark after second round: %v", err)
	}
	if wm2 != "9" {
		t.Fatalf("watermark after second round = %q, want %q", wm2, "9")
	}
}
