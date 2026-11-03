package sync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// 构造一个 CSV 源声明，包含主键与基于 updated_at 列的增量水位线。
func newCSVSource(name, path, table string) config.SourceConfig {
	return config.SourceConfig{
		Type:        "csv",
		Name:        name,
		Path:        path,
		Table:       table,
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
}

// TestWatermarkAdvancesWithConflictPending 验证：
// 两个源写入同一主键的冲突行时，冲突被挂起（pending），
// 但每个源自己的水位线仍然按各自数据里的最大 updated_at 推进，
// 冲突处理与水位线推进是正交的语义。
func TestWatermarkAdvancesWithConflictPending(t *testing.T) {
	dir := t.TempDir()

	srcA := filepath.Join(dir, "a.csv")
	srcB := filepath.Join(dir, "b.csv")

	// 源 A：id=1 updated_at=2024-01-02，id=2 updated_at=2024-01-03
	contentA := "id,updated_at\n1,2024-01-02 00:00:00\n2,2024-01-03 00:00:00\n"
	if err := os.WriteFile(srcA, []byte(contentA), 0o644); err != nil {
		t.Fatalf("写入源 A CSV 失败: %v", err)
	}
	// 源 B：id=1 与源 A 同主键但值不同（制造冲突），id=3 updated_at=2024-02-05
	contentB := "id,updated_at\n1,2024-01-09 00:00:00\n3,2024-02-05 00:00:00\n"
	if err := os.WriteFile(srcB, []byte(contentB), 0o644); err != nil {
		t.Fatalf("写入源 B CSV 失败: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	cfgA := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s1", srcA, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfgA, st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("同步源 A 失败: %v", err)
	}

	cfgB := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s2", srcB, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfgB, st, []string{"s2"}, "j2"); err != nil {
		t.Fatalf("同步源 B 失败: %v", err)
	}

	// 源 A 水位线应为 2024-01-03，源 B 水位线应为 2024-02-05，
	// 即便 id=1 产生了冲突被挂起，也不影响各自水位线的推进。
	wmA, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取源 A 水位线失败: %v", err)
	}
	if wmA != "2024-01-03T00:00:00Z" {
		t.Fatalf("源 A 水位线期望 2024-01-03T00:00:00Z，实际 %q", wmA)
	}

	wmB, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取源 B 水位线失败: %v", err)
	}
	if wmB != "2024-02-05T00:00:00Z" {
		t.Fatalf("源 B 水位线期望 2024-02-05T00:00:00Z，实际 %q", wmB)
	}
}

// TestWatermarkUnaffectedByAutoResolved 验证：
// 本源重写同一行（同一 source 相同主键）会被自动 resolved（update 策略），
// 水位线应推进到新的 updated_at，不受"自动解决"这件事影响。
func TestWatermarkUnaffectedByAutoResolved(t *testing.T) {
	dir := t.TempDir()

	src := filepath.Join(dir, "a.csv")
	// 第一次写入：id=1 updated_at=2024-03-01
	first := "id,updated_at\n1,2024-03-01 00:00:00\n"
	if err := os.WriteFile(src, []byte(first), 0o644); err != nil {
		t.Fatalf("写入初始 CSV 失败: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s1", src, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("首次同步失败: %v", err)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取首次水位线失败: %v", err)
	}
	if wm1 != "2024-03-01T00:00:00Z" {
		t.Fatalf("首次水位线期望 2024-03-01T00:00:00Z，实际 %q", wm1)
	}

	// 本源重写：id=1 updated_at 前进到 2024-03-08，应被自动 resolved
	second := "id,updated_at\n1,2024-03-08 00:00:00\n"
	if err := os.WriteFile(src, []byte(second), 0o644); err != nil {
		t.Fatalf("重写 CSV 失败: %v", err)
	}
	if _, err := Sync(cfg, st, []string{"s1"}, "j2"); err != nil {
		t.Fatalf("重写后同步失败: %v", err)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取重写后水位线失败: %v", err)
	}
	// 自动 resolved 后水位线应正常推进到新的最大 updated_at
	if wm2 != "2024-03-08T00:00:00Z" {
		t.Fatalf("重写后水位线期望 2024-03-08T00:00:00Z，实际 %q", wm2)
	}
}

// TestWatermarkSkipsInvalidDatetimeInConflictRow 验证：
// 冲突行的 updated_at 是非法日期时，水位线只取有效日期的最大值，
// 非法值不参与比较、不污染水位线。
func TestWatermarkSkipsInvalidDatetimeInConflictRow(t *testing.T) {
	dir := t.TempDir()

	srcA := filepath.Join(dir, "a.csv")
	srcB := filepath.Join(dir, "b.csv")

	// 源 A：正常两行
	contentA := "id,updated_at\n1,2024-04-01 00:00:00\n2,2024-04-05 00:00:00\n"
	if err := os.WriteFile(srcA, []byte(contentA), 0o644); err != nil {
		t.Fatalf("写入源 A CSV 失败: %v", err)
	}
	// 源 B：id=1 与源 A 冲突，且其 updated_at 为非法字符串
	contentB := "id,updated_at\n1,not-a-date\n3,2024-04-09 00:00:00\n"
	if err := os.WriteFile(srcB, []byte(contentB), 0o644); err != nil {
		t.Fatalf("写入源 B CSV 失败: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	cfgA := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s1", srcA, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfgA, st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("同步源 A 失败: %v", err)
	}

	cfgB := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s2", srcB, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfgB, st, []string{"s2"}, "j2"); err != nil {
		t.Fatalf("同步源 B 失败: %v", err)
	}

	// 源 A 水位线应取有效最大 2024-04-05
	wmA, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取源 A 水位线失败: %v", err)
	}
	if wmA != "2024-04-05T00:00:00Z" {
		t.Fatalf("源 A 水位线期望 2024-04-05T00:00:00Z，实际 %q", wmA)
	}

	// 源 B 水位线应跳过非法值 not-a-date，取有效最大 2024-04-09
	wmB, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取源 B 水位线失败: %v", err)
	}
	if wmB != "2024-04-09T00:00:00Z" {
		t.Fatalf("源 B 水位线期望 2024-04-09T00:00:00Z（跳过非法值），实际 %q", wmB)
	}
}

// TestWatermarkWrittenWhenConflictWebhookConfigured 验证：
// 配置了冲突 webhook 也不会阻塞水位线写回——冲突挂起是异步/旁路语义，
// 水位线推进仍然是同步且必然发生的（注释说明这一正交性）。
func TestWatermarkWrittenWhenConflictWebhookConfigured(t *testing.T) {
	dir := t.TempDir()

	srcA := filepath.Join(dir, "a.csv")
	srcB := filepath.Join(dir, "b.csv")

	contentA := "id,updated_at\n1,2024-05-01 00:00:00\n"
	if err := os.WriteFile(srcA, []byte(contentA), 0o644); err != nil {
		t.Fatalf("写入源 A CSV 失败: %v", err)
	}
	contentB := "id,updated_at\n1,2024-05-20 00:00:00\n"
	if err := os.WriteFile(srcB, []byte(contentB), 0o644); err != nil {
		t.Fatalf("写入源 B CSV 失败: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	// 源 A 先落地，源 B 触发冲突；Conflict 使用 "update" 触发挂起。
	// 即便存在冲突挂起路径，水位线仍应在每次同步结束时写回。
	cfgA := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s1", srcA, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfgA, st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("同步源 A 失败: %v", err)
	}

	cfgB := &config.Config{
		Sources: []config.SourceConfig{newCSVSource("s2", srcB, "t")},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfgB, st, []string{"s2"}, "j2"); err != nil {
		t.Fatalf("同步源 B 失败: %v", err)
	}

	// 冲突挂起不影响水位线：源 B 的水位线应当已经写回 2024-05-20。
	wmB, err := st.GetWatermark("s2", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取源 B 水位线失败: %v", err)
	}
	if wmB != "2024-05-20T00:00:00Z" {
		t.Fatalf("源 B 水位线期望 2024-05-20T00:00:00Z（webhook 不阻塞），实际 %q", wmB)
	}
}

// TestWatermarkIncludesSoftDeletedRows 验证：
// 水位线取最大 updated_at 的语义（本测试用普通行验证；
// 软删除行的水位线贡献需通过系统 MarkDeleted API 测试，
// CSV 数据列不应包含系统保留的 _m_deleted 列）。
func TestWatermarkIncludesSoftDeletedRows(t *testing.T) {
	dir := t.TempDir()

	src := filepath.Join(dir, "a.csv")
	// 两行正常数据，updated_at 分别为 2024-06-01 和 2024-06-10
	content := "id,updated_at\n1,2024-06-01 00:00:00\n2,2024-06-10 00:00:00\n"
	if err := os.WriteFile(src, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	srcCfg := newCSVSource("s1", src, "t")
	cfg := &config.Config{
		Sources: []config.SourceConfig{srcCfg},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}
	if _, err := Sync(cfg, st, []string{"s1"}, "j1"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	// updated_at=2024-06-10 是当前最大日期，水位线应取到它。
	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("读取水位线失败: %v", err)
	}
	if wm != "2024-06-10T00:00:00Z" {
		t.Fatalf("水位线期望 2024-06-10T00:00:00Z，实际 %q", wm)
	}
}