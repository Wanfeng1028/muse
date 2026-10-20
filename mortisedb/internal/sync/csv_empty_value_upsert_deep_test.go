package sync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// TestCSVEmptyIncrementalInsert 验证：增量列（updated_at）为空值的行，新主键应正常插入。
func TestCSVEmptyIncrementalInsert(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := filepath.Join(dir, "a.csv")
	content := "id,name,updated_at\n1,alice,\n"
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	src := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}

	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 1 {
		t.Fatalf("首轮空增量值行应插入 1 行，实际 Inserted=%d", ts.Inserted)
	}
	if ts.Updated != 0 || ts.Skipped != 0 {
		t.Fatalf("首轮不应有更新或跳过，实际 Updated=%d Skipped=%d", ts.Updated, ts.Skipped)
	}
}

// TestCSVEmptyIncrementalNewPrimaryKeyInsert 验证：次轮新增一条空增量值行（新主键），Inserted=1。
func TestCSVEmptyIncrementalNewPrimaryKeyInsert(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := filepath.Join(dir, "a.csv")
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n"), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	src := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}

	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}

	// 次轮新增一行空增量值行（新主键 2）。
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n2,bob,\n"), 0o644); err != nil {
		t.Fatalf("重写 CSV 失败: %v", err)
	}

	stats, err := Sync(cfg, st, []string{src.Name}, "j2")
	if err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 1 {
		t.Fatalf("次轮新增空增量值行应 Inserted=1，实际 Inserted=%d", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("次轮新增行不应产生更新，实际 Updated=%d", ts.Updated)
	}
}

// TestCSVEmptyIncrementalUnchangedSkipped 验证：已存在且内容（哈希）相同的空增量值行应跳过。
func TestCSVEmptyIncrementalUnchangedSkipped(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := filepath.Join(dir, "a.csv")
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n"), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	src := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}

	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}

	// 内容完全一致，哈希相同。
	stats, err := Sync(cfg, st, []string{src.Name}, "j2")
	if err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}
	ts := tableStat(t, stats, "t")
	if ts.Skipped != 1 {
		t.Fatalf("内容未变应 Skipped=1，实际 Skipped=%d", ts.Skipped)
	}
	if ts.Inserted != 0 || ts.Updated != 0 {
		t.Fatalf("内容未变不应插入或更新，实际 Inserted=%d Updated=%d", ts.Inserted, ts.Updated)
	}
}

// TestCSVEmptyIncrementalOtherColumnChangedUpdated 验证：空增量值行其他列变化时，哈希不同应更新。
func TestCSVEmptyIncrementalOtherColumnChangedUpdated(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := filepath.Join(dir, "a.csv")
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n"), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	src := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}

	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}

	// 主键相同，updated_at 仍为空，但 name 变化 → 哈希不同。
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice2,\n"), 0o644); err != nil {
		t.Fatalf("重写 CSV 失败: %v", err)
	}

	stats, err := Sync(cfg, st, []string{src.Name}, "j2")
	if err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}
	ts := tableStat(t, stats, "t")
	if ts.Updated != 1 {
		t.Fatalf("其他列变化应 Updated=1，实际 Updated=%d", ts.Updated)
	}
	if ts.Inserted != 0 {
		t.Fatalf("其他列变化不应插入，实际 Inserted=%d", ts.Inserted)
	}
}

// TestCSVEmptyIncrementalRowDeleted 验证：CSV 中删除某条空增量值行后的行为。
// 说明：同步采用 upsert 语义（Conflict=update），源侧删除的行不会在目标表被删除；
// 删除仅表现为该行不再出现在本轮输入，既不产生 Insert 也不产生 Update/Skipped。
// 因此目标表仍保留该行，本测试断言 Inserted/Updated/Skipped 均不因删除而变化。
func TestCSVEmptyIncrementalRowDeleted(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := filepath.Join(dir, "a.csv")
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n2,bob,\n"), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	src := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}

	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}

	// 删除主键 2 的空增量值行，仅保留主键 1（内容未变）。
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n"), 0o644); err != nil {
		t.Fatalf("重写 CSV 失败: %v", err)
	}

	stats, err := Sync(cfg, st, []string{src.Name}, "j2")
	if err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 0 {
		t.Fatalf("删除行不应导致插入，实际 Inserted=%d", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("删除行不应导致更新，实际 Updated=%d", ts.Updated)
	}
	// 主键 1 内容未变，应被跳过。
	if ts.Skipped != 1 {
		t.Fatalf("保留行内容未变应 Skipped=1，实际 Skipped=%d", ts.Skipped)
	}
}

// TestCSVEmptyFieldVsNullConsistency 验证：CSV 空字段（空串）在增量列上的一致性——
// 首轮插入空增量值行、次轮相同内容应跳过，不因空串与 NULL 的差异重复计数。
func TestCSVEmptyFieldVsNullConsistency(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p := filepath.Join(dir, "a.csv")
	// updated_at 列为空字段（空串）。
	if err := os.WriteFile(p, []byte("id,name,updated_at\n1,alice,\n"), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	src := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        p,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 100},
	}

	stats1, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("首轮同步失败: %v", err)
	}
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 1 {
		t.Fatalf("首轮空字段行应 Inserted=1，实际 Inserted=%d", ts1.Inserted)
	}

	// 次轮内容完全相同，空串语义稳定 → 跳过。
	stats2, err := Sync(cfg, st, []string{src.Name}, "j2")
	if err != nil {
		t.Fatalf("次轮同步失败: %v", err)
	}
	ts2 := tableStat(t, stats2, "t")
	if ts2.Skipped != 1 {
		t.Fatalf("空字段内容一致应 Skipped=1，实际 Skipped=%d", ts2.Skipped)
	}
	if ts2.Inserted != 0 || ts2.Updated != 0 {
		t.Fatalf("空字段内容一致不应插入或更新，实际 Inserted=%d Updated=%d", ts2.Inserted, ts2.Updated)
	}
}
