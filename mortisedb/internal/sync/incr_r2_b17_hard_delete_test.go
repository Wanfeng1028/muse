package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestIncrR2B17HardDeleteRemovesPhysically(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,name\n1,a\n2,b\n3,c\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: false, BatchSize: 100},
	}
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	var ts *TableStats
	for i := range stats {
		for j := range stats[i].Tables {
			if stats[i].Tables[j].Table == "t" {
				ts = &stats[i].Tables[j]
			}
		}
	}
	if ts == nil {
		t.Fatalf("未找到表 t 的统计")
	}
	if ts.Inserted != 3 {
		t.Fatalf("首轮 Inserted 期望 3，实际 %d", ts.Inserted)
	}

	cnt1, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt1 != 3 {
		t.Fatalf("首轮 TableCount 期望 3，实际 %d", cnt1)
	}

	p2 := writeCSVStr(t, dir, "r2.csv", "id,name\n1,a\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg2 := &config.Config{
		Sources: []config.SourceConfig{src2},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: false, BatchSize: 100},
	}
	stats2, err := Sync(cfg2, st, []string{"s1"}, "j2")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	var ts2 *TableStats
	for i := range stats2 {
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				ts2 = &stats2[i].Tables[j]
			}
		}
	}
	if ts2 == nil {
		t.Fatalf("未找到表 t 的统计")
	}
	if ts2.Deleted != 2 {
		t.Fatalf("第二轮 Deleted 期望 2，实际 %d", ts2.Deleted)
	}

	cnt2, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt2 != 1 {
		t.Fatalf("第二轮 TableCount 期望 1，实际 %d", cnt2)
	}

	_, _, _, found2, err := st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("GetHash 失败: %v", err)
	}
	if found2 {
		t.Fatalf("主键 2 应被物理删除，found 期望 false，实际 true")
	}

	_, _, _, found3, err := st.GetHash(st.DB, "t", "id", "3")
	if err != nil {
		t.Fatalf("GetHash 失败: %v", err)
	}
	if found3 {
		t.Fatalf("主键 3 应被物理删除，found 期望 false，实际 true")
	}
}

func TestIncrR2B17HardDeleteThenReinsert(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,name\n1,a\n2,b\n3,c\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: false, BatchSize: 100},
	}
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	var ts *TableStats
	for i := range stats {
		for j := range stats[i].Tables {
			if stats[i].Tables[j].Table == "t" {
				ts = &stats[i].Tables[j]
			}
		}
	}
	if ts == nil {
		t.Fatalf("未找到表 t 的统计")
	}

	cnt1, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt1 != 3 {
		t.Fatalf("首轮 TableCount 期望 3，实际 %d", cnt1)
	}

	p2 := writeCSVStr(t, dir, "r2.csv", "id,name\n1,a\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg2 := &config.Config{
		Sources: []config.SourceConfig{src2},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: false, BatchSize: 100},
	}
	stats2, err := Sync(cfg2, st, []string{"s1"}, "j2")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	var ts2 *TableStats
	for i := range stats2 {
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				ts2 = &stats2[i].Tables[j]
			}
		}
	}
	if ts2 == nil {
		t.Fatalf("未找到表 t 的统计")
	}
	if ts2.Deleted != 2 {
		t.Fatalf("第二轮 Deleted 期望 2，实际 %d", ts2.Deleted)
	}

	p3 := writeCSVStr(t, dir, "r3.csv", "id,name\n1,a\n2,b2\n")
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: p3, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg3 := &config.Config{
		Sources: []config.SourceConfig{src3},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: false, BatchSize: 100},
	}
	stats3, err := Sync(cfg3, st, []string{"s1"}, "j3")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	var ts3 *TableStats
	for i := range stats3 {
		for j := range stats3[i].Tables {
			if stats3[i].Tables[j].Table == "t" {
				ts3 = &stats3[i].Tables[j]
			}
		}
	}
	if ts3 == nil {
		t.Fatalf("未找到表 t 的统计")
	}
	if ts3.Inserted != 1 {
		t.Fatalf("第三轮 Inserted 期望 1，实际 %d", ts3.Inserted)
	}

	var name string
	if err := st.DB.QueryRow("SELECT \"name\" FROM \"t\" WHERE \"id\"='2'").Scan(&name); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if name != "b2" {
		t.Fatalf("主键 2 的 name 期望 b2，实际 %s", name)
	}
}
