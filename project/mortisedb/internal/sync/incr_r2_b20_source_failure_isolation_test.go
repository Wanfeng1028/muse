package sync

import (
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestIncrR2B20BadSourceDoesNotBlockGood(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	goodPath := writeCSVStr(t, dir, "good.csv", "id,name\n1,a\n2,b\n")

	bad := config.SourceConfig{Type: "csv", Name: "bad", Path: "/nonexistent-dir-xyz/nope.csv", Table: "t", PrimaryKey: "id"}
	good := config.SourceConfig{Type: "csv", Name: "good", Path: goodPath, Table: "t", PrimaryKey: "id"}
	cfg := &config.Config{Sources: []config.SourceConfig{bad, good}, Sync: config.SyncPolicy{Conflict: "update", BatchSize: 100}}

	stats, err := Sync(cfg, st, []string{"bad", "good"}, "j1")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "bad") {
		t.Fatalf("期望错误信息包含 bad，实际为 %q", err.Error())
	}
	if len(stats) != 2 {
		t.Fatalf("期望 stats 长度为 2，实际为 %d", len(stats))
	}

	var goodStats, badStats *SourceStats
	for i := range stats {
		switch stats[i].Source {
		case "good":
			goodStats = &stats[i]
		case "bad":
			badStats = &stats[i]
		}
	}
	if goodStats == nil {
		t.Fatal("未找到 good 源的 stats")
	}
	if badStats == nil {
		t.Fatal("未找到 bad 源的 stats")
	}
	if len(goodStats.Tables) != 1 {
		t.Fatalf("good 源期望 1 个表，实际为 %d", len(goodStats.Tables))
	}
	if goodStats.Tables[0].Inserted != 2 {
		t.Fatalf("good 源期望插入 2 行，实际为 %d", goodStats.Tables[0].Inserted)
	}
	if len(badStats.Tables) != 0 {
		t.Fatalf("bad 源期望 Tables 为空，实际为 %d", len(badStats.Tables))
	}
}

func TestIncrR2B20FailedRunRecorded(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	goodPath := writeCSVStr(t, dir, "good.csv", "id,name\n1,a\n2,b\n")

	bad := config.SourceConfig{Type: "csv", Name: "bad", Path: "/nonexistent-dir-xyz/nope.csv", Table: "t", PrimaryKey: "id"}
	good := config.SourceConfig{Type: "csv", Name: "good", Path: goodPath, Table: "t", PrimaryKey: "id"}
	cfg := &config.Config{Sources: []config.SourceConfig{bad, good}, Sync: config.SyncPolicy{Conflict: "update", BatchSize: 100}}

	_, err = Sync(cfg, st, []string{"bad", "good"}, "j1")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}

	runs, err := st.ListRuns(10)
	if err != nil {
		t.Fatalf("ListRuns 失败: %v", err)
	}

	var badRun, goodRun *store.RunRecord
	for i := range runs {
		switch runs[i].Job {
		case "j1:bad":
			badRun = &runs[i]
		case "j1:good":
			goodRun = &runs[i]
		}
	}
	if badRun == nil {
		t.Fatal("未找到 Job 为 j1:bad 的 run 记录")
	}
	if badRun.Error == "" {
		t.Fatal("期望 bad run 的 Error 非空")
	}
	if !strings.Contains(badRun.Error, "bad") {
		t.Fatalf("期望 bad run 的 Error 包含 bad，实际为 %q", badRun.Error)
	}
	if goodRun == nil {
		t.Fatal("未找到 Job 为 j1:good 的 run 记录")
	}
	if goodRun.Error != "" {
		t.Fatalf("期望 good run 的 Error 为空，实际为 %q", goodRun.Error)
	}
	if goodRun.Inserted != 2 {
		t.Fatalf("期望 good run 插入 2 行，实际为 %d", goodRun.Inserted)
	}
}
