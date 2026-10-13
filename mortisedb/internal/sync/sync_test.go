package sync

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/connector"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func newStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	return st
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("建目录失败: %v", err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写文件失败: %v", err)
	}
}

func TestHashRowDeterministic(t *testing.T) {
	a := HashRow("1", []string{"b", "a"}, []any{2, 1})
	b := HashRow("1", []string{"a", "b"}, []any{1, 2})
	if a != b {
		t.Fatalf("HashRow 应不依赖列顺序: %s vs %s", a, b)
	}
	if len(a) != 64 {
		t.Fatalf("sha256 hex 应为 64 字符, 实际 %d", len(a))
	}
}

func TestPriorityIndex(t *testing.T) {
	p := []string{"a", "b"}
	if PriorityIndex(p, "a") != 0 {
		t.Fatalf("a 应为 0")
	}
	if PriorityIndex(p, "b") != 1 {
		t.Fatalf("b 应为 1")
	}
	if PriorityIndex(p, "c") != 1<<30 {
		t.Fatalf("未列出应为 1<<30")
	}
}

func TestSyncBasicAndMergeAndDelete(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	csvB := filepath.Join(dir, "b.csv")
	writeFile(t, csvA, "id,name\n1,alice\n2,bob\n")
	writeFile(t, csvB, "id,name\n3,carol\n4,dave\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"a", "b"}, SoftDelete: false},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "hash"},
			{Name: "b", Type: "csv", Path: csvB, Table: "items", PrimaryKey: "id", Incremental: "hash"},
		},
	}

	st := newStore(t)
	defer st.Close()

	stats, err := Sync(cfg, st, nil, "job1")
	if err != nil {
		t.Fatalf("同步失败: %v", err)
	}
	if len(stats) != 2 {
		t.Fatalf("应有 2 个源统计, 实际 %d", len(stats))
	}
	totalIns := 0
	for _, ss := range stats {
		for _, ts := range ss.Tables {
			totalIns += ts.Inserted
		}
	}
	if totalIns != 4 {
		t.Fatalf("应插入 4 行, 实际 %d", totalIns)
	}

	// 二次同步应全 Skipped
	stats2, err := Sync(cfg, st, nil, "job1")
	if err != nil {
		t.Fatalf("二次同步失败: %v", err)
	}
	for _, ss := range stats2 {
		for _, ts := range ss.Tables {
			if ts.Inserted != 0 || ts.Updated != 0 || ts.Conflicts != 0 {
				t.Fatalf("二次同步应无变更: %+v", ts)
			}
			if ts.Skipped != 2 {
				t.Fatalf("二次同步应全 Skipped, 实际 %+v", ts)
			}
		}
	}

	// 源 a 删掉 id=2, 全量模式下应删除
	writeFile(t, csvA, "id,name\n1,alice\n")
	stats3, err := Sync(cfg, st, []string{"a"}, "job1")
	if err != nil {
		t.Fatalf("三次同步失败: %v", err)
	}
	if stats3[0].Tables[0].Deleted != 1 {
		t.Fatalf("应删除 1 行, 实际 %+v", stats3[0].Tables[0])
	}
	_, rows, err := st.Query(`SELECT "id" FROM "items" WHERE _m_deleted=0 ORDER BY "id"`)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if len(rows) != 3 {
		t.Fatalf("应剩 3 行, 实际 %d", len(rows))
	}
}

func TestSyncSoftDelete(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	writeFile(t, csvA, "id,name\n1,alice\n2,bob\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"a"}, SoftDelete: true},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "hash"},
		},
	}
	st := newStore(t)
	defer st.Close()

	if _, err := Sync(cfg, st, nil, "j"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}
	writeFile(t, csvA, "id,name\n1,alice\n")
	stats, err := Sync(cfg, st, nil, "j")
	if err != nil {
		t.Fatalf("二次同步失败: %v", err)
	}
	if stats[0].Tables[0].Deleted != 1 {
		t.Fatalf("应软删 1, 实际 %+v", stats[0].Tables[0])
	}
	var deleted int
	_, rows, err := st.Query(`SELECT "_m_deleted" FROM "items" WHERE "id"=2`)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if len(rows) == 1 {
		if v, ok := rows[0][0].(int64); ok {
			deleted = int(v)
		}
	}
	if deleted != 1 {
		t.Fatalf("_m_deleted 应为 1, 实际 %d", deleted)
	}
}

func TestSyncPriorityConflict(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	csvB := filepath.Join(dir, "b.csv")
	writeFile(t, csvA, "id,name\n1,fromA\n")
	writeFile(t, csvB, "id,name\n1,fromB\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"a", "b"}, SoftDelete: false},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "hash"},
			{Name: "b", Type: "csv", Path: csvB, Table: "items", PrimaryKey: "id", Incremental: "hash"},
		},
	}
	st := newStore(t)
	defer st.Close()

	// 先同步 a, 再同步 b -> b 优先级更低, 冲突 pending
	if _, err := Sync(cfg, st, []string{"a"}, "j"); err != nil {
		t.Fatalf("同步 a 失败: %v", err)
	}
	stats, err := Sync(cfg, st, []string{"b"}, "j")
	if err != nil {
		t.Fatalf("同步 b 失败: %v", err)
	}
	if stats[0].Tables[0].Conflicts != 1 {
		t.Fatalf("应有 1 冲突, 实际 %+v", stats[0].Tables[0])
	}
	cs, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("列冲突失败: %v", err)
	}
	if len(cs) != 1 {
		t.Fatalf("应有 1 条 pending 冲突, 实际 %d", len(cs))
	}

	// 再同步 a -> a 优先级更高, 应自动解决并记录 resolved_auto
	// 先改 a 内容制造 hash 差异
	writeFile(t, csvA, "id,name\n1,fromA2\n")
	stats2, err := Sync(cfg, st, []string{"a"}, "j")
	if err != nil {
		t.Fatalf("再次同步 a 失败: %v", err)
	}
	if stats2[0].Tables[0].Conflicts != 1 {
		t.Fatalf("a 优先应记录冲突, 实际 %+v", stats2[0].Tables[0])
	}
	all, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("列全部冲突失败: %v", err)
	}
	foundAuto := false
	for _, c := range all {
		if c.Status == "resolved_auto" {
			foundAuto = true
		}
	}
	if !foundAuto {
		t.Fatalf("应有 resolved_auto 冲突记录")
	}
}

func TestSyncManualConflict(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	csvB := filepath.Join(dir, "b.csv")
	writeFile(t, csvA, "id,name\n1,fromA\n")
	writeFile(t, csvB, "id,name\n1,fromB\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "manual", SoftDelete: false},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "hash"},
			{Name: "b", Type: "csv", Path: csvB, Table: "items", PrimaryKey: "id", Incremental: "hash"},
		},
	}
	st := newStore(t)
	defer st.Close()

	if _, err := Sync(cfg, st, []string{"a"}, "j"); err != nil {
		t.Fatalf("同步 a 失败: %v", err)
	}
	stats, err := Sync(cfg, st, []string{"b"}, "j")
	if err != nil {
		t.Fatalf("同步 b 失败: %v", err)
	}
	if stats[0].Tables[0].Conflicts != 1 {
		t.Fatalf("应有 1 冲突, 实际 %+v", stats[0].Tables[0])
	}
	// 目标表应仍保留 a 的值 (manual 跳过)
	_, rows, err := st.Query(`SELECT "name" FROM "items" WHERE "id"=1`)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if len(rows) != 1 || fmt.Sprintf("%v", rows[0][0]) != "fromA" {
		t.Fatalf("manual 模式应保留原值 fromA, 实际 %v", rows)
	}
}

func TestSyncIncrementalColumn(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	writeFile(t, csvA, "id,name,ts\n1,alice,2024-01-01T00:00:00Z\n2,bob,2024-01-02T00:00:00Z\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"a"}, SoftDelete: false},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "column:ts"},
		},
	}
	st := newStore(t)
	defer st.Close()

	stats, err := Sync(cfg, st, nil, "j")
	if err != nil {
		t.Fatalf("首次同步失败: %v", err)
	}
	if stats[0].Tables[0].Inserted != 2 {
		t.Fatalf("应插入 2 行, 实际 %+v", stats[0].Tables[0])
	}
	wm, err := st.GetWatermark("a", "items", "ts")
	if err != nil {
		t.Fatalf("取水位线失败: %v", err)
	}
	if wm != "2024-01-02T00:00:00Z" {
		t.Fatalf("水位线应为 2024-01-02T00:00:00Z, 实际 %s", wm)
	}

	// 追加一行
	writeFile(t, csvA, "id,name,ts\n1,alice,2024-01-01T00:00:00Z\n2,bob,2024-01-02T00:00:00Z\n3,carol,2024-01-03T00:00:00Z\n")
	stats2, err := Sync(cfg, st, nil, "j")
	if err != nil {
		t.Fatalf("二次同步失败: %v", err)
	}
	if stats2[0].Tables[0].Inserted != 1 {
		t.Fatalf("增量应只插入 1 行, 实际 %+v", stats2[0].Tables[0])
	}
	if stats2[0].Tables[0].Skipped != 0 {
		t.Fatalf("增量不应有 Skipped, 实际 %+v", stats2[0].Tables[0])
	}
	wm2, err := st.GetWatermark("a", "items", "ts")
	if err != nil {
		t.Fatalf("取水位线失败: %v", err)
	}
	if wm2 != "2024-01-03T00:00:00Z" {
		t.Fatalf("水位线应为 2024-01-03T00:00:00Z, 实际 %s", wm2)
	}
}

func TestSyncSQLiteSource(t *testing.T) {
	dir := t.TempDir()
	srcPath := filepath.Join(dir, "src.db")

	// 用 store 建一个 sqlite 源库并插数据
	{
		st, err := store.Open(srcPath)
		if err != nil {
			t.Fatalf("打开源库失败: %v", err)
		}
		if _, err := st.DB.Exec(`CREATE TABLE "users" ("id" INTEGER PRIMARY KEY, "name" TEXT)`); err != nil {
			t.Fatalf("建表失败: %v", err)
		}
		if _, err := st.DB.Exec(`INSERT INTO "users" ("id","name") VALUES (1,'alice'),(2,'bob')`); err != nil {
			t.Fatalf("插入失败: %v", err)
		}
		st.Close()
	}

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"src"}, SoftDelete: false},
		Sources: []config.SourceConfig{
			{
				Name: "src", Type: "sqlite", Path: srcPath, Incremental: "hash",
				Tables: []config.TableMap{{Source: "users", Target: "users_copy", PrimaryKey: "id"}},
			},
		},
	}
	st := newStore(t)
	defer st.Close()

	stats, err := Sync(cfg, st, nil, "j")
	if err != nil {
		t.Fatalf("同步失败: %v", err)
	}
	if stats[0].Tables[0].Inserted != 2 {
		t.Fatalf("应插入 2 行, 实际 %+v", stats[0].Tables[0])
	}
	_, rows, err := st.Query(`SELECT "id","name" FROM "users_copy" ORDER BY "id"`)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("应 2 行, 实际 %d", len(rows))
	}
}

func TestSyncRecordsRun(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	writeFile(t, csvA, "id,name\n1,alice\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"a"}, SoftDelete: false},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "hash"},
		},
	}
	st := newStore(t)
	defer st.Close()

	if _, err := Sync(cfg, st, nil, "myjob"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}
	runs, err := st.ListRuns(10)
	if err != nil {
		t.Fatalf("列运行失败: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("应有 1 条 run, 实际 %d", len(runs))
	}
	if runs[0].Job != "myjob:a" {
		t.Fatalf("job 应为 myjob:a, 实际 %s", runs[0].Job)
	}
	if runs[0].Inserted != 1 {
		t.Fatalf("inserted 应为 1, 实际 %d", runs[0].Inserted)
	}
	if runs[0].FinishedAt == "" {
		t.Fatalf("finished_at 不应为空")
	}
	if _, err := time.Parse(time.RFC3339, runs[0].FinishedAt); err != nil {
		t.Fatalf("finished_at 应为 RFC3339: %v", err)
	}
}

func TestSyncConflictRowJSON(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	csvB := filepath.Join(dir, "b.csv")
	writeFile(t, csvA, "id,name\n1,fromA\n")
	writeFile(t, csvB, "id,name\n1,fromB\n")

	cfg := &config.Config{
		Version: 1,
		Sync:    config.SyncPolicy{Conflict: "manual", SoftDelete: false},
		Sources: []config.SourceConfig{
			{Name: "a", Type: "csv", Path: csvA, Table: "items", PrimaryKey: "id", Incremental: "hash"},
			{Name: "b", Type: "csv", Path: csvB, Table: "items", PrimaryKey: "id", Incremental: "hash"},
		},
	}
	st := newStore(t)
	defer st.Close()

	if _, err := Sync(cfg, st, []string{"a"}, "j"); err != nil {
		t.Fatalf("同步 a 失败: %v", err)
	}
	if _, err := Sync(cfg, st, []string{"b"}, "j"); err != nil {
		t.Fatalf("同步 b 失败: %v", err)
	}
	cs, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("列冲突失败: %v", err)
	}
	if len(cs) != 1 {
		t.Fatalf("应有 1 冲突")
	}
	var m map[string]any
	if err := json.Unmarshal([]byte(cs[0].RowJSON), &m); err != nil {
		t.Fatalf("row_json 应合法 JSON: %v", err)
	}
	if fmt.Sprintf("%v", m["name"]) != "fromB" {
		t.Fatalf("row_json 应含 fromB, 实际 %v", m)
	}
	if _, ok := m["id"]; !ok {
		t.Fatalf("row_json 应含主键 id")
	}
	if cs[0].SourceA != "a" || cs[0].SourceB != "b" {
		t.Fatalf("source 字段错误: %+v", cs[0])
	}
}

// 确保 infer 与 connector 包被使用 (编译期占位)
var (
	_ = infer.Stringify
	_ = connector.Row{}
	_ = sha256.New
	_ = hex.EncodeToString
	_ = sort.Strings
	_ context.Context
)
