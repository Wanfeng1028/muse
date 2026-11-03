package sync

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func writeCSVStr(t *testing.T, dir, name, content string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}
	return p
}

func runSync(t *testing.T, st *store.Store, src config.SourceConfig, job string) []SourceStats {
	t.Helper()
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	stats, err := Sync(cfg, st, []string{src.Name}, job)
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	return stats
}

func tableStat(t *testing.T, stats []SourceStats, table string) TableStats {
	t.Helper()
	for _, s := range stats {
		for _, ts := range s.Tables {
			if ts.Table == table {
				return ts
			}
		}
	}
	t.Fatalf("未找到表 %q 的统计", table)
	return TableStats{}
}

func TestWatermarkMixedSixFormatsFirstRound(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-20T08:00:00Z\n" +
		"2,2026-10-20 09:00:00\n" +
		"3,2026-10-20T10:00:00\n" +
		"4,2026-10-20 11:00\n" +
		"5,2026-10-20\n" +
		"6,2026/10/20 12:00:00\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 6 {
		t.Fatalf("首轮 Inserted=%d 期望 6", got.Inserted)
	}
	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatal(err)
	}
	if wm != "2026-10-20T12:00:00Z" {
		t.Fatalf("水位线=%q 期望 2026-10-20T12:00:00Z", wm)
	}
}

func TestWatermarkSecondRoundNoNewRows(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20T10:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	wm1, _ := st.GetWatermark("s1", "t", "updated_at")
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 0 {
		t.Fatalf("次轮 Inserted=%d 期望 0", got.Inserted)
	}
	wm2, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm1 != wm2 {
		t.Fatalf("水位线变化 %q -> %q", wm1, wm2)
	}
	if wm2 != "2026-10-20T10:00:00Z" {
		t.Fatalf("水位线=%q", wm2)
	}
}

func TestWatermarkAppendOnlyIncremental(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20T10:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	csv2 := csv + "3,2026-10-20T11:00:00Z\n"
	writeCSVStr(t, dir, "a.csv", csv2)
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 1 {
		t.Fatalf("增量 Inserted=%d 期望 1", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T11:00:00Z" {
		t.Fatalf("水位线=%q", wm)
	}
}

func TestWatermarkTimezoneOffsetFilter(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20T03:00:00Z\n2,2026-10-20T02:30:00+08:00\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T03:00:00Z" {
		t.Fatalf("水位线=%q 期望 2026-10-20T03:00:00Z", wm)
	}
}

func TestWatermarkTimezoneOffsetLessThanWatermark(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20T03:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	csv2 := csv + "2,2026-10-20T10:00:00+08:00\n"
	writeCSVStr(t, dir, "a.csv", csv2)
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 0 {
		t.Fatalf("Inserted=%d 期望 0（10:00+08:00 == 02:00Z < 03:00Z）", got.Inserted)
	}
}

func TestWatermarkLexicographicTrapStorage(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-20 09:00:00\n" +
		"2,2026-10-20T08:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 2 {
		t.Fatalf("Inserted=%d 期望 2", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("水位线=%q 期望 2026-10-20T09:00:00Z（时间更大但字典序更小）", wm)
	}
	stats2 := runSync(t, st, src, "j2")
	got2 := tableStat(t, stats2, "t")
	if got2.Inserted != 0 {
		t.Fatalf("次轮 Inserted=%d 期望 0（旧行不应重拉）", got2.Inserted)
	}
}

func TestWatermarkLexicographicTrapNoRepull(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20T08:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	csv2 := csv + "3,2026-10-20T10:00:00Z\n"
	writeCSVStr(t, dir, "a.csv", csv2)
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 1 {
		t.Fatalf("Inserted=%d 期望 1", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("水位线=%q", wm)
	}
}

func TestWatermarkPresetOldFormatBilateralNormalize(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-19 10:00:00\n" +
		"2,2026-10-20 11:00:00\n" +
		"3,2026-10-20T09:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-19 10:00:00"); err != nil {
		t.Fatal(err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 2 {
		t.Fatalf("Inserted=%d 期望 2（10-19 10:00 应被过滤，另两行拉取）", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T11:00:00Z" {
		t.Fatalf("水位线=%q", wm)
	}
}

func TestWatermarkMultiSourceIndependent(t *testing.T) {
	dir := t.TempDir()
	csvA := "id,updated_at\n1,2026-10-20T09:00:00Z\n"
	csvB := "id,updated_at\n2,2026-10-20 08:00:00\n"
	pa := writeCSVStr(t, dir, "a.csv", csvA)
	pb := writeCSVStr(t, dir, "b.csv", csvB)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	srcA := config.SourceConfig{Type: "csv", Name: "sA", Path: pa, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	srcB := config.SourceConfig{Type: "csv", Name: "sB", Path: pb, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, srcA, "j1")
	runSync(t, st, srcB, "j2")
	wmA, _ := st.GetWatermark("sA", "t", "updated_at")
	wmB, _ := st.GetWatermark("sB", "t", "updated_at")
	if wmA != "2026-10-20T09:00:00Z" {
		t.Fatalf("源A水位线=%q", wmA)
	}
	if wmB != "2026-10-20T08:00:00Z" {
		t.Fatalf("源B水位线=%q", wmB)
	}
}

func TestWatermarkSameSourceFormatChange(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20T09:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	csv2 := "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n"
	writeCSVStr(t, dir, "a.csv", csv2)
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 1 {
		t.Fatalf("Inserted=%d 期望 1", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("水位线=%q", wm)
	}
}

func TestWatermarkSlashAndDateOnly(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026/10/20 08:00:00\n" +
		"2,2026-10-20\n" +
		"3,2026/10/20 09:00:00\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 3 {
		t.Fatalf("Inserted=%d 期望 3", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("水位线=%q 期望 2026-10-20T09:00:00Z", wm)
	}
}

func TestWatermarkEmptyValueFirstRound(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 2 {
		t.Fatalf("Inserted=%d 期望 2（空值行不丢）", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("水位线=%q 期望不被空值污染", wm)
	}
}

func TestWatermarkEmptyValueSecondRoundPulled(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20T09:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	csv2 := csv + "2,\n"
	writeCSVStr(t, dir, "a.csv", csv2)
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 1 {
		t.Fatalf("Inserted=%d 期望 1（新增空值行应被同步）", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("水位线=%q 期望不被空值污染", wm)
	}
}

func TestWatermarkInvalidValueNotPollute(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-20T09:00:00Z\n" +
		"2,not-a-date\n" +
		"3,2026-10-20T10:00:00Z\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 3 {
		t.Fatalf("Inserted=%d 期望 3", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("水位线=%q 期望不被非法值污染", wm)
	}
}

func TestWatermarkPureTextColumnCompatible(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,alpha\n2,bravo\n3,charlie\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "j1")
	got := tableStat(t, stats, "t")
	if got.Inserted != 3 {
		t.Fatalf("Inserted=%d 期望 3", got.Inserted)
	}
	if _, err := st.GetWatermark("s1", "t", "updated_at"); err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
}

func TestWatermarkPureTextColumnSecondRound(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,alpha\n2,bravo\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	csv2 := csv + "3,zulu\n"
	writeCSVStr(t, dir, "a.csv", csv2)
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 1 {
		t.Fatalf("Inserted=%d 期望 1", got.Inserted)
	}
}

func TestNormalizeComparableTable(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"2026-10-20T08:00:00Z", "2026-10-20T08:00:00Z"},
		{"2026-10-20T10:00:00+08:00", "2026-10-20T02:00:00Z"},
		{"2026-10-20 09:00:00", "2026-10-20T09:00:00Z"},
		{"2026-10-20T09:00:00", "2026-10-20T09:00:00Z"},
		{"2026/10/20 12:00:00", "2026-10-20T12:00:00Z"},
		{"2026-10-20", "2026-10-20T00:00:00Z"},
		{"", ""},
		{"not-a-date", "not-a-date"},
		{"  2026-10-20 09:00:00  ", "2026-10-20T09:00:00Z"},
	}
	for _, c := range cases {
		got := infer.NormalizeComparable(c.in)
		if got != c.want {
			t.Errorf("NormalizeComparable(%q)=%q 期望 %q", c.in, got, c.want)
		}
	}
}

func TestWatermarkFormatMixedSecondRoundNoDuplicates(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-20T08:00:00Z\n" +
		"2,2026-10-20 09:00:00\n" +
		"3,2026-10-20T10:00:00\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	stats := runSync(t, st, src, "j2")
	got := tableStat(t, stats, "t")
	if got.Inserted != 0 {
		t.Fatalf("Inserted=%d 期望 0", got.Inserted)
	}
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("水位线=%q", wm)
	}
}

func TestWatermarkNormalizedStoredFormat(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n1,2026-10-20 09:00:00\n"
	p := writeCSVStr(t, dir, "a.csv", csv)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src, "j1")
	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("水位线=%q 期望规范化为 RFC3339 UTC", wm)
	}
	if wm == "2026-10-20 09:00:00" {
		t.Fatalf("水位线未规范化")
	}
}

var _ = fmt.Sprintf
