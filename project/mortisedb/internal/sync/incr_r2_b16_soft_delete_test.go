package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestIncrR2B16SoftDeleteAndRevive(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,name\n1,a\n2,b\n")
	p2 := writeCSVStr(t, dir, "r2.csv", "id,name\n1,a\n")
	p3 := writeCSVStr(t, dir, "r3.csv", "id,name\n1,a\n2,b\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := config.SourceConfig{
		Name:        "t",
		Type:        "csv",
		Path:        p1,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "",
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: true, BatchSize: 100},
	}

	// round1：全量写入两行
	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	n, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if n != 2 {
		t.Fatalf("round1 TableCount = %d, 期望 2", n)
	}

	// round2：id=2 消失，应被软删除
	cfg.Sources[0].Path = p2
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var ts *TableStats
	for i := range stats[0].Tables {
		if stats[0].Tables[i].Table == "t" {
			ts = &stats[0].Tables[i]
			break
		}
	}
	if ts == nil {
		t.Fatalf("未找到表统计 t")
	}
	if ts.Deleted != 1 {
		t.Fatalf("round2 Deleted = %d, 期望 1", ts.Deleted)
	}
	n, err = st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("round2 TableCount = %d, 期望 1", n)
	}
	_, _, deleted, found, err := st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("GetHash 失败: %v", err)
	}
	if !found {
		t.Fatalf("软删除后行应仍存在, found = false")
	}
	if !deleted {
		t.Fatalf("软删除后 deleted = false, 期望 true")
	}

	// round3：id=2 回来，应复活
	cfg.Sources[0].Path = p3
	stats, err = Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	ts = nil
	for i := range stats[0].Tables {
		if stats[0].Tables[i].Table == "t" {
			ts = &stats[0].Tables[i]
			break
		}
	}
	if ts == nil {
		t.Fatalf("未找到表统计 t")
	}
	if ts.Updated != 1 {
		t.Fatalf("round3 Updated = %d, 期望 1", ts.Updated)
	}
	n, err = st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if n != 2 {
		t.Fatalf("round3 TableCount = %d, 期望 2", n)
	}
	_, _, deleted, found, err = st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("GetHash 失败: %v", err)
	}
	if !found {
		t.Fatalf("复活后 found = false")
	}
	if deleted {
		t.Fatalf("复活后 deleted = true, 期望 false")
	}
}

func TestIncrR2B16SoftDeletedRowStillInDB(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,name\n1,a\n2,b\n")
	p2 := writeCSVStr(t, dir, "r2.csv", "id,name\n1,a\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := config.SourceConfig{
		Name:        "t",
		Type:        "csv",
		Path:        p1,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "",
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: true, BatchSize: 100},
	}

	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	cfg.Sources[0].Path = p2
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var ts *TableStats
	for i := range stats[0].Tables {
		if stats[0].Tables[i].Table == "t" {
			ts = &stats[0].Tables[i]
			break
		}
	}
	if ts == nil {
		t.Fatalf("未找到表统计 t")
	}
	if ts.Deleted != 1 {
		t.Fatalf("Deleted = %d, 期望 1", ts.Deleted)
	}

	var n int
	if err := st.DB.QueryRow("SELECT COUNT(*) FROM \"t\" WHERE \"_m_deleted\"=1").Scan(&n); err != nil {
		t.Fatalf("查询软删除行失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("物理软删除行数 = %d, 期望 1", n)
	}

	var name string
	if err := st.DB.QueryRow("SELECT \"name\" FROM \"t\" WHERE \"id\"='2'").Scan(&name); err != nil {
		t.Fatalf("查询 id=2 失败: %v", err)
	}
	if name != "b" {
		t.Fatalf("软删除行 name = %q, 期望 b", name)
	}
}
