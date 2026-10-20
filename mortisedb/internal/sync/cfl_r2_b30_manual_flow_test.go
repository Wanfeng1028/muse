package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestCflR2B30ManualFullFlow(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	pathA := writeCSVStr(t, t.TempDir(), "a.csv", "id,name\n1,a1\n")
	pathB := writeCSVStr(t, t.TempDir(), "b.csv", "id,name\n1,b1\n")

	srcA := config.SourceConfig{
		Name:       "A",
		Type:       "csv",
		Table:      "t",
		PrimaryKey: "id",
		Path:       pathA,
	}
	srcB := config.SourceConfig{
		Name:       "B",
		Type:       "csv",
		Table:      "t",
		PrimaryKey: "id",
		Path:       pathB,
	}

	cfg := &config.Config{
		Sources: []config.SourceConfig{srcA, srcB},
		Sync:    config.SyncPolicy{Conflict: "manual", BatchSize: 100},
	}

	stats1, err := Sync(cfg, st, []string{"A"}, "j1")
	if err != nil {
		t.Fatalf("round1 Sync 失败: %v", err)
	}
	var tsA *TableStats
	for i := range stats1 {
		if stats1[i].Source != "A" {
			continue
		}
		for j := range stats1[i].Tables {
			if stats1[i].Tables[j].Table == "t" {
				tsA = &stats1[i].Tables[j]
			}
		}
	}
	if tsA == nil {
		t.Fatal("round1 未找到 A 的 t 表统计")
	}
	if tsA.Inserted != 1 {
		t.Fatalf("round1 A.Inserted 期望 1，实际 %d", tsA.Inserted)
	}

	stats2, err := Sync(cfg, st, []string{"B"}, "j2")
	if err != nil {
		t.Fatalf("round2 Sync 失败: %v", err)
	}
	var tsB *TableStats
	for i := range stats2 {
		if stats2[i].Source != "B" {
			continue
		}
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				tsB = &stats2[i].Tables[j]
			}
		}
	}
	if tsB == nil {
		t.Fatal("round2 未找到 B 的 t 表统计")
	}
	if tsB.Conflicts != 1 {
		t.Fatalf("round2 B.Conflicts 期望 1，实际 %d", tsB.Conflicts)
	}
	if tsB.Updated != 0 {
		t.Fatalf("round2 B.Updated 期望 0，实际 %d", tsB.Updated)
	}
	if tsB.Inserted != 0 {
		t.Fatalf("round2 B.Inserted 期望 0，实际 %d", tsB.Inserted)
	}

	var nameVal string
	if err := st.DB.QueryRow("SELECT name FROM t WHERE id = 1").Scan(&nameVal); err != nil {
		t.Fatalf("round2 查询行失败: %v", err)
	}
	if nameVal != "a1" {
		t.Fatalf("round2 行内容期望 a1，实际 %s", nameVal)
	}

	pend, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("round2 ListConflicts 失败: %v", err)
	}
	if len(pend) != 1 {
		t.Fatalf("round2 pending 数量期望 1，实际 %d", len(pend))
	}
	if pend[0].SourceA != "A" {
		t.Fatalf("round2 SourceA 期望 A，实际 %s", pend[0].SourceA)
	}
	if pend[0].SourceB != "B" {
		t.Fatalf("round2 SourceB 期望 B，实际 %s", pend[0].SourceB)
	}
	if pend[0].Status != "pending" {
		t.Fatalf("round2 Status 期望 pending，实际 %s", pend[0].Status)
	}

	if err := st.ResolveConflict(pend[0].ID, "resolved_manual"); err != nil {
		t.Fatalf("ResolveConflict 失败: %v", err)
	}
	done, err := st.ListConflicts("resolved_manual")
	if err != nil {
		t.Fatalf("ListConflicts(resolved_manual) 失败: %v", err)
	}
	if len(done) != 1 {
		t.Fatalf("resolved_manual 数量期望 1，实际 %d", len(done))
	}
	if done[0].ResolvedAt == "" {
		t.Fatal("resolved_manual ResolvedAt 期望非空")
	}
	pendAfter, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) 失败: %v", err)
	}
	if len(pendAfter) != 0 {
		t.Fatalf("解决后 pending 期望 0，实际 %d", len(pendAfter))
	}

	pathB2 := writeCSVStr(t, t.TempDir(), "b2.csv", "id,name\n1,b2\n")
	srcB.Path = pathB2
	cfg.Sources = []config.SourceConfig{srcA, srcB}

	stats3, err := Sync(cfg, st, []string{"B"}, "j3")
	if err != nil {
		t.Fatalf("round3 Sync 失败: %v", err)
	}
	var tsB3 *TableStats
	for i := range stats3 {
		if stats3[i].Source != "B" {
			continue
		}
		for j := range stats3[i].Tables {
			if stats3[i].Tables[j].Table == "t" {
				tsB3 = &stats3[i].Tables[j]
			}
		}
	}
	if tsB3 == nil {
		t.Fatal("round3 未找到 B 的 t 表统计")
	}
	if tsB3.Conflicts != 1 {
		t.Fatalf("round3 B.Conflicts 期望 1，实际 %d", tsB3.Conflicts)
	}
	if tsB3.Updated != 0 {
		t.Fatalf("round3 B.Updated 期望 0，实际 %d", tsB3.Updated)
	}
	if tsB3.Inserted != 0 {
		t.Fatalf("round3 B.Inserted 期望 0，实际 %d", tsB3.Inserted)
	}

	var nameVal3 string
	if err := st.DB.QueryRow("SELECT name FROM t WHERE id = 1").Scan(&nameVal3); err != nil {
		t.Fatalf("round3 查询行失败: %v", err)
	}
	if nameVal3 != "a1" {
		t.Fatalf("round3 行内容期望 a1，实际 %s", nameVal3)
	}

	pend3, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("round3 ListConflicts 失败: %v", err)
	}
	if len(pend3) != 1 {
		t.Fatalf("round3 pending 数量期望 1，实际 %d", len(pend3))
	}
	if pend3[0].Status != "pending" {
		t.Fatalf("round3 Status 期望 pending，实际 %s", pend3[0].Status)
	}
}
