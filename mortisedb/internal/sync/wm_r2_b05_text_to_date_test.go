package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B05TextColumnAdvances(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,updated_at\n1,b\n2,a\n")
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	src1 := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats1 := runSync(t, st, src1, "j1")
	if got := tableStat(t, stats1, "t").Inserted; got != 2 {
		t.Fatalf("第一轮 Inserted = %d, 期望 2", got)
	}
	wm1, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm1 != "b" {
		t.Fatalf("第一轮水位线 = %q, 期望 %q", wm1, "b")
	}

	p2 := writeCSVStr(t, dir, "r2.csv", "id,updated_at\n1,b\n2,a\n3,c\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats2 := runSync(t, st, src2, "j2")
	if got := tableStat(t, stats2, "t").Inserted; got != 1 {
		t.Fatalf("第二轮 Inserted = %d, 期望 1", got)
	}
	wm2, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm2 != "c" {
		t.Fatalf("第二轮水位线 = %q, 期望 %q", wm2, "c")
	}

	// 文本水位线 "c" 无法被 infer.IsDateTime 识别，因此不进入 since，
	// 连接器侧不过滤，每轮都全量拉取，靠主键 hash 去重。
}

func TestWmR2B05DateRowSwitchesWatermarkToDate(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	p1 := writeCSVStr(t, dir, "r1.csv", "id,updated_at\n1,b\n2,a\n")
	src1 := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats1 := runSync(t, st, src1, "j1")
	if got := tableStat(t, stats1, "t").Inserted; got != 2 {
		t.Fatalf("第一轮 Inserted = %d, 期望 2", got)
	}

	p2 := writeCSVStr(t, dir, "r2.csv", "id,updated_at\n1,b\n2,a\n3,c\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats2 := runSync(t, st, src2, "j2")
	if got := tableStat(t, stats2, "t").Inserted; got != 1 {
		t.Fatalf("第二轮 Inserted = %d, 期望 1", got)
	}
	wm2, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm2 != "c" {
		t.Fatalf("第二轮水位线 = %q, 期望 %q", wm2, "c")
	}

	p3 := writeCSVStr(t, dir, "r3.csv", "id,updated_at\n1,b\n2,a\n3,c\n4,2026-10-20\n")
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: p3, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats3 := runSync(t, st, src3, "j3")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Inserted != 1 {
		t.Fatalf("第三轮 Inserted = %d, 期望 1", ts3.Inserted)
	}
	if ts3.Skipped != 3 {
		t.Fatalf("第三轮 Skipped = %d, 期望 3", ts3.Skipped)
	}
	wm3, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm3 != "2026-10-20T00:00:00Z" {
		t.Fatalf("第三轮水位线 = %q, 期望 %q", wm3, "2026-10-20T00:00:00Z")
	}

	// 文本水位线 "c" 的 IsDateTime 为 false，故 since 为空，连接器不过滤仍全量拉取；
	// 旧 3 行 hash 相同被跳过，仅新日期行插入。
	// 本批出现可解析日期后，写回水位线取日期规范化最大值，文本→日期切换不会停滞。
}
