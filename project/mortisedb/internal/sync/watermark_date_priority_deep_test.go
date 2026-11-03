package sync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// 构造一个 CSV 源配置：以 updated_at 为增量列，主键 id。
func wmSource(name, path, table string) config.SourceConfig {
	return config.SourceConfig{
		Type:        "csv",
		Name:        name,
		Path:        path,
		Table:       table,
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
}

// 写入一个 CSV 文件到 dir 下的文件名，返回完整路径。
func wmWriteCSV(t *testing.T, dir, file, content string) string {
	t.Helper()
	p := filepath.Join(dir, file)
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 文件失败: %v", err)
	}
	return p
}

// 用例 1：非法值穿插在合法日期之间，水位线应取可解析日期的规范化最大值，
// 非法值 "not-a-date" 不参与水位线计算，但行仍应被同步。
func TestSyncWatermarkSkipsInvalidDate(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,not-a-date\n3,2026-10-20T10:00:00Z\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("水位线期望 2026-10-20T10:00:00Z，实际 %q", wm)
	}
}

// 用例 2：全部为非法值（纯文本），水位线应退化为字符串 max；
// 且第二轮新增更大的字符串 "zzz" 能被增量拉取，说明增量不死锁。
func TestSyncWatermarkAllInvalidThenAppend(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,foo\n2,bar\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "foo" {
		t.Fatalf("全非法值时水位线期望字符串 max \"foo\"，实际 %q", wm)
	}

	// 第二轮追加一个字符串更大的行，应能被拉取
	content2 := "id,updated_at\n1,foo\n2,bar\n3,zzz\n"
	p2 := wmWriteCSV(t, dir, "b.csv", content2)
	src2 := wmSource("s1", p2, "t")
	cfg2 := &config.Config{
		Sources: []config.SourceConfig{src2},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg2, st, []string{src2.Name}, "j2"); err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm2 != "zzz" {
		t.Fatalf("次轮水位线期望 \"zzz\"，实际 %q", wm2)
	}
}

// 用例 3：首轮纯日期，次轮追加非法值行；水位线应保持首轮日期最大值，
// 非法行本身仍应被同步插入（不因非法值被丢弃）。
func TestSyncWatermarkInvalidInSecondRound(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,2026-10-20T10:00:00Z\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}

	// 次轮追加一行非法值
	content2 := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,2026-10-20T10:00:00Z\n3,not-a-date\n"
	p2 := wmWriteCSV(t, dir, "b.csv", content2)
	src2 := wmSource("s1", p2, "t")
	cfg2 := &config.Config{
		Sources: []config.SourceConfig{src2},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg2, st, []string{src2.Name}, "j2"); err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("次轮含非法值时水位线期望保持 2026-10-20T10:00:00Z，实际 %q", wm)
	}
}

// 用例 4：混入 unicode 垃圾值，水位线仍只由可解析日期决定。
func TestSyncWatermarkUnicodeGarbage(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,日期\n3,not-a-date\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("混入 unicode 垃圾值时期望 2026-10-20T09:00:00Z，实际 %q", wm)
	}
}

// 用例 5：空值混入，空串不参与水位线计算，取合法日期最大值。
func TestSyncWatermarkEmptyMixed(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,\n3,2026-10-20T10:00:00Z\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("空值混入时期望 2026-10-20T10:00:00Z，实际 %q", wm)
	}
}

// 用例 6：纯文本列，水位线取字符串 max（legacy 语义）。
func TestSyncWatermarkPlainTextStringMax(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,delta\n2,alpha\n3,charlie\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "delta" {
		t.Fatalf("纯文本列期望字符串 max \"delta\"，实际 %q", wm)
	}
}

// 用例 7：日期与文本混合列，有可解析日期时优先取日期最大值。
func TestSyncWatermarkDateBeatsText(t *testing.T) {
	dir := t.TempDir()
	content := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,zulu\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2026-10-20T09:00:00Z" {
		t.Fatalf("日期与文本混合时期望取日期最大值 2026-10-20T09:00:00Z，实际 %q", wm)
	}
}

// 用例 8：水位线永不回退，即使本批最大日期小于已记录水位线。
func TestSyncWatermarkNeverRegresses(t *testing.T) {
	dir := t.TempDir()

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	// 预置一个更高的水位线
	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-20T12:00:00Z"); err != nil {
		t.Fatalf("预置水位线失败: %v", err)
	}

	content := "id,updated_at\n1,2026-10-20T09:00:00Z\n2,2026-10-20T10:00:00Z\n"
	p := wmWriteCSV(t, dir, "a.csv", content)

	src := wmSource("s1", p, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2026-10-20T12:00:00Z" {
		t.Fatalf("水位线不应回退，期望保持 2026-10-20T12:00:00Z，实际 %q", wm)
	}
}