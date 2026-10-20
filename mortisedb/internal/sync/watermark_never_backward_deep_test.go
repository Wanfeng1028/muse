package sync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// 本文件测试水位线永不回退语义：Sync 在增量同步时读取既有水位线，
// 新水位线取 max(旧水位线, 本批最大值)。旧水位线若为老格式日期先规范化再比较，
// 非法值水位线在遇到可解析日期后应被自愈纠正。

// 构造一个只含增量列 updated_at 的 CSV 源，写入若干行，返回目录与源配置。
func writeWatermarkCSV(t *testing.T, dir, name, content string) config.SourceConfig {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 文件失败: %v", err)
	}
	return config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
}

// 打开内存库并迁移，返回 store。
func openMemStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移内存库失败: %v", err)
	}
	return st
}

// 读取水位线，失败即终止。
func mustWatermark(t *testing.T, st *store.Store) string {
	t.Helper()
	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	return wm
}

// 场景 1：预置水位线晚于本批最大值，水位线必须保持旧值不回退。
func TestWatermarkNeverRegressWhenPresetNewer(t *testing.T) {
	dir := t.TempDir()
	// 本批数据最大 updated_at 为 2026-10-20T10:00:00Z
	content := "id,updated_at\n1,2026-10-20T10:00:00Z\n"
	src := writeWatermarkCSV(t, dir, "a.csv", content)

	st := openMemStore(t)
	// 预置一个更晚的水位线
	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-20T12:00:00Z"); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	got := mustWatermark(t, st)
	if got != "2026-10-20T12:00:00Z" {
		t.Fatalf("水位线不应回退，期望 2026-10-20T12:00:00Z，实际 %q", got)
	}
}

// 场景 2：预置老格式水位线（空格分隔），本批为更早的 RFC3339，
// 规范化后比较，水位线应保持旧值。
func TestWatermarkNeverRegressWithLegacyFormat(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T10:00:00Z\n"
	src := writeWatermarkCSV(t, dir, "a.csv", content)

	st := openMemStore(t)
	// 老格式，与 RFC3339 表示同一时刻但写法不同
	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-20 12:00:00"); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	got := mustWatermark(t, st)
	// 期望规范化后的等值表示，不回退到 10 点
	if got != "2026-10-20T12:00:00Z" {
		t.Fatalf("老格式水位线规范化后不应回退，期望 2026-10-20T12:00:00Z，实际 %q", got)
	}
}

// 场景 3：预置水位线早于本批最大值，水位线应更新为本批最大值。
func TestWatermarkAdvancesWhenBatchNewer(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T10:00:00Z\n2,2026-10-20T14:00:00Z\n"
	src := writeWatermarkCSV(t, dir, "a.csv", content)

	st := openMemStore(t)
	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-20T10:00:00Z"); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	got := mustWatermark(t, st)
	if got != "2026-10-20T14:00:00Z" {
		t.Fatalf("本批更大时应更新水位线，期望 2026-10-20T14:00:00Z，实际 %q", got)
	}
}

// 场景 4：预置非法值水位线（历史脏数据），本批有可解析日期，
// 应自愈纠正为日期最大值。
func TestWatermarkSelfHealsFromInvalidValue(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T10:00:00Z\n2,2026-10-20T09:00:00Z\n"
	src := writeWatermarkCSV(t, dir, "a.csv", content)

	st := openMemStore(t)
	if err := st.SetWatermark("s1", "t", "updated_at", "not-a-date"); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	got := mustWatermark(t, st)
	if got != "2026-10-20T10:00:00Z" {
		t.Fatalf("非法水位线应被本批日期自愈纠正，期望 2026-10-20T10:00:00Z，实际 %q", got)
	}
}

// 场景 5：预置空串水位线，应按无水位线处理，直接采用本批最大值。
func TestWatermarkEmptyTreatedAsAbsent(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T10:00:00Z\n2,2026-10-20T11:00:00Z\n"
	src := writeWatermarkCSV(t, dir, "a.csv", content)

	st := openMemStore(t)
	if err := st.SetWatermark("s1", "t", "updated_at", ""); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	got := mustWatermark(t, st)
	if got != "2026-10-20T11:00:00Z" {
		t.Fatalf("空水位线应按无水位线处理，期望 2026-10-20T11:00:00Z，实际 %q", got)
	}
}

// 场景 6：纯文本增量列，预置 "mike"，本批 "zulu"，
// 非日期按字符串比较，"zulu" > "mike" 应更新。
func TestWatermarkTextColumnAdvances(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,zulu\n"
	src := writeWatermarkCSV(t, dir, "a.csv", content)

	st := openMemStore(t)
	if err := st.SetWatermark("s1", "t", "updated_at", "mike"); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	got := mustWatermark(t, st)
	if got != "zulu" {
		t.Fatalf("纯文本水位线应更新为 zulu，实际 %q", got)
	}
}

// 场景 7：三轮递增同步，每轮水位线单调不减。
func TestWatermarkMonotonicAcrossRounds(t *testing.T) {
	dir := t.TempDir()
	st := openMemStore(t)

	cfgOf := func(p string) *config.Config {
		src := config.SourceConfig{
			Type:        "csv",
			Name:        "s1",
			Path:        p,
			Table:       "t",
			PrimaryKey:  "id",
			Incremental: "column:updated_at",
		}
		return &config.Config{
			Sources: []config.SourceConfig{src},
			Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
		}
	}

	// 第一轮
	p1 := filepath.Join(dir, "r1.csv")
	if err := os.WriteFile(p1, []byte("id,updated_at\n1,2026-10-20T08:00:00Z\n"), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	if _, err := Sync(cfgOf(p1), st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("第一轮同步失败: %v", err)
	}
	wm1 := mustWatermark(t, st)
	if wm1 != "2026-10-20T08:00:00Z" {
		t.Fatalf("第一轮水位线期望 2026-10-20T08:00:00Z，实际 %q", wm1)
	}

	// 第二轮
	p2 := filepath.Join(dir, "r2.csv")
	if err := os.WriteFile(p2, []byte("id,updated_at\n2,2026-10-20T10:00:00Z\n"), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	if _, err := Sync(cfgOf(p2), st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("第二轮同步失败: %v", err)
	}
	wm2 := mustWatermark(t, st)
	if wm2 != "2026-10-20T10:00:00Z" {
		t.Fatalf("第二轮水位线期望 2026-10-20T10:00:00Z，实际 %q", wm2)
	}

	// 第三轮
	p3 := filepath.Join(dir, "r3.csv")
	if err := os.WriteFile(p3, []byte("id,updated_at\n3,2026-10-20T12:00:00Z\n"), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	if _, err := Sync(cfgOf(p3), st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("第三轮同步失败: %v", err)
	}
	wm3 := mustWatermark(t, st)
	if wm3 != "2026-10-20T12:00:00Z" {
		t.Fatalf("第三轮水位线期望 2026-10-20T12:00:00Z，实际 %q", wm3)
	}

	// 单调不减检查
	if wm2 < wm1 {
		t.Fatalf("水位线应单调不减，第二轮 %q < 第一轮 %q", wm2, wm1)
	}
	if wm3 < wm2 {
		t.Fatalf("水位线应单调不减，第三轮 %q < 第二轮 %q", wm3, wm2)
	}
}