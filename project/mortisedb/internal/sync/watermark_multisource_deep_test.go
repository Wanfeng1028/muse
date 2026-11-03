package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// 说明：本文件测试"多源独立水位线"的语义——
// 两源同表名不同源名时，各自水位线独立演进；
// 混合日期格式各自规范化；非法值只污染该源；源名大小写/特殊字符隔离；
// 删除一源后重建水位线从空开始。
// 这里复用被测包与既有 API：store.Open / Migrate / GetWatermark /
// config.Config / config.SourceConfig / config.SyncPolicy / Sync。

// 写一个 CSV 源文件，返回其绝对路径。

// 构造同步配置，便于各用例复用。
func newCfg(sources ...config.SourceConfig) *config.Config {
	return &config.Config{
		Sources: sources,
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
}

// 在测：两源同名表、不同源名，各自使用不同的日期格式，
// 同步后水位线应各自规范化成 RFC3339 UTC，互不影响。
func TestMultiSourceWatermarkIndependentFormats(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	// s1 使用 "2006-01-02 15:04:05" 格式
	p1 := writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n")
	// s2 使用 "2006/01/02 15:04:05" 格式
	p2 := writeCSVStr(t, dir, "s2.csv",
		"id,name,updated_at\n1,bob,2026/10/20 09:00:00\n")

	src1 := config.SourceConfig{
		Type: "csv", Name: "s1", Path: p1, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	src2 := config.SourceConfig{
		Type: "csv", Name: "s2", Path: p2, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	cfg := newCfg(src1, src2)

	if _, err := Sync(cfg, st, []string{"s1", "s2"}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s1 水位线失败: %v", err)
	}
	wm2, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s2 水位线失败: %v", err)
	}
	want := "2026-10-20T09:00:00Z"
	if wm1 != want {
		t.Fatalf("s1 水位线期望 %q，实际 %q", want, wm1)
	}
	if wm2 != want {
		t.Fatalf("s2 水位线期望 %q，实际 %q", want, wm2)
	}
}

// 在测：s1 追加新行而 s2 不动时，s1 水位线前进，s2 水位线保持原值。
func TestMultiSourceWatermarkAdvanceOnlyChangedSource(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n")
	p2 := writeCSVStr(t, dir, "s2.csv",
		"id,name,updated_at\n1,bob,2026/10/20 09:00:00\n")

	src1 := config.SourceConfig{
		Type: "csv", Name: "s1", Path: p1, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	src2 := config.SourceConfig{
		Type: "csv", Name: "s2", Path: p2, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	cfg := newCfg(src1, src2)

	if _, err := Sync(cfg, st, []string{"s1", "s2"}, "j1"); err != nil {
		t.Fatalf("首次同步失败: %v", err)
	}
	wm2Before, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s2 水位线失败: %v", err)
	}

	// s1 追加一行更晚的时间
	p1 = writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n2,carol,2026-10-21 10:30:00\n")
	src1.Path = p1
	cfg = newCfg(src1, src2)

	if _, err := Sync(cfg, st, []string{"s1", "s2"}, "j2"); err != nil {
		t.Fatalf("二次同步失败: %v", err)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s1 水位线失败: %v", err)
	}
	wm2After, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s2 水位线失败: %v", err)
	}

	if wm1 != "2026-10-21T10:30:00Z" {
		t.Fatalf("s1 水位线期望前进到 %q，实际 %q", "2026-10-21T10:30:00Z", wm1)
	}
	if wm2After != wm2Before {
		t.Fatalf("s2 未变更，水位线期望保持 %q，实际 %q", wm2Before, wm2After)
	}
}

// 在测：两源存在相同主键 id=1 时按冲突策略处理，
// 但两源水位线依旧各自独立演进，互不串扰。
func TestMultiSourceWatermarkWithSamePrimaryKey(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n")
	p2 := writeCSVStr(t, dir, "s2.csv",
		"id,name,updated_at\n1,bob,2026/10/22 11:00:00\n")

	src1 := config.SourceConfig{
		Type: "csv", Name: "s1", Path: p1, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	src2 := config.SourceConfig{
		Type: "csv", Name: "s2", Path: p2, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	cfg := newCfg(src1, src2)

	if _, err := Sync(cfg, st, []string{"s1", "s2"}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s1 水位线失败: %v", err)
	}
	wm2, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s2 水位线失败: %v", err)
	}
	if wm1 != "2026-10-20T09:00:00Z" {
		t.Fatalf("s1 水位线期望 %q，实际 %q", "2026-10-20T09:00:00Z", wm1)
	}
	if wm2 != "2026-10-22T11:00:00Z" {
		t.Fatalf("s2 水位线期望 %q，实际 %q", "2026-10-22T11:00:00Z", wm2)
	}
}

// 在测：某一源混入非法日期值时，仅影响该源；
// s1 仍取合法日期最大值，s2 不受污染保持自身水位线。
func TestMultiSourceWatermarkInvalidValueIsolated(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	// s1 含一行非法 updated_at
	p1 := writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n2,bad,not-a-date\n")
	p2 := writeCSVStr(t, dir, "s2.csv",
		"id,name,updated_at\n1,bob,2026/10/20 09:00:00\n")

	src1 := config.SourceConfig{
		Type: "csv", Name: "s1", Path: p1, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	src2 := config.SourceConfig{
		Type: "csv", Name: "s2", Path: p2, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	cfg := newCfg(src1, src2)

	if _, err := Sync(cfg, st, []string{"s1", "s2"}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s1 水位线失败: %v", err)
	}
	wm2, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s2 水位线失败: %v", err)
	}
	// s1 的非法值不参与比较，合法最大值仍是 2026-10-20 09:00:00
	if wm1 != "2026-10-20T09:00:00Z" {
		t.Fatalf("s1 水位线期望 %q，实际 %q", "2026-10-20T09:00:00Z", wm1)
	}
	if wm2 != "2026-10-20T09:00:00Z" {
		t.Fatalf("s2 水位线期望 %q，实际 %q", "2026-10-20T09:00:00Z", wm2)
	}
}

// 在测：源名大小写与特殊字符不同时，水位线按源名严格隔离，
// 互不覆盖。
func TestMultiSourceWatermarkNameIsolation(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "a.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n")
	p2 := writeCSVStr(t, dir, "b.csv",
		"id,name,updated_at\n1,bob,2026-10-22 11:00:00\n")

	src1 := config.SourceConfig{
		Type: "csv", Name: "Src-A", Path: p1, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	src2 := config.SourceConfig{
		Type: "csv", Name: "src-a", Path: p2, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	cfg := newCfg(src1, src2)

	if _, err := Sync(cfg, st, []string{"Src-A", "src-a"}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm1, err := st.GetWatermark("Src-A", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 Src-A 水位线失败: %v", err)
	}
	wm2, err := st.GetWatermark("src-a", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 src-a 水位线失败: %v", err)
	}
	if wm1 != "2026-10-20T09:00:00Z" {
		t.Fatalf("Src-A 水位线期望 %q，实际 %q", "2026-10-20T09:00:00Z", wm1)
	}
	if wm2 != "2026-10-22T11:00:00Z" {
		t.Fatalf("src-a 水位线期望 %q，实际 %q", "2026-10-22T11:00:00Z", wm2)
	}
}

// 在测：源被删除（水位线被清理）后以同名重建，
// 水位线应从空开始，不继承旧源的残留值。
func TestMultiSourceWatermarkRecreateAfterDelete(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-10-20 09:00:00\n")

	src1 := config.SourceConfig{
		Type: "csv", Name: "s1", Path: p1, Table: "t",
		PrimaryKey: "id", Incremental: "column:updated_at",
	}
	cfg := newCfg(src1)

	if _, err := Sync(cfg, st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("首次同步失败: %v", err)
	}
	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取 s1 水位线失败: %v", err)
	}
	if wm1 != "2026-10-20T09:00:00Z" {
		t.Fatalf("s1 首次水位线期望 %q，实际 %q", "2026-10-20T09:00:00Z", wm1)
	}

	// 删除该源的水位线（模拟删除一源）
	if err := st.DeleteWatermark("s1", "t", "updated_at"); err != nil {
		t.Fatalf("清理 s1 水位线失败: %v", err)
	}
	wmGone, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("删除后读取 s1 水位线失败: %v", err)
	}
	if wmGone != "" {
		t.Fatalf("删除后 s1 水位线期望为空，实际 %q", wmGone)
	}

	// 以同名重建（新文件、新数据），水位线应从空开始并重新演进
	p1 = writeCSVStr(t, dir, "s1.csv",
		"id,name,updated_at\n1,alice,2026-11-01 08:00:00\n")
	src1.Path = p1
	cfg = newCfg(src1)

	if _, err := Sync(cfg, st, []string{"s1"}, "j2"); err != nil {
		t.Fatalf("重建后同步失败: %v", err)
	}
	wmRebuilt, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("重建后读取 s1 水位线失败: %v", err)
	}
	if wmRebuilt != "2026-11-01T08:00:00Z" {
		t.Fatalf("重建后 s1 水位线期望 %q，实际 %q", "2026-11-01T08:00:00Z", wmRebuilt)
	}
}