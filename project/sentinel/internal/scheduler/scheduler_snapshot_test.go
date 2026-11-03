package scheduler

import (
	"fmt"
	"testing"

	"sentinel/internal/store"
)

func TestSweepSnapshot_OffSkips(t *testing.T) {
	st := newTestStore(t)
	count := 0
	sch := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {}, 10, 5, 2)
	_, err := st.CreateStatusPage(1, "sched-snap", "调度快照页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	sch.SetSnapshotGenerator(func(pageID int64) error {
		count++
		return nil
	})
	sch.sweepSnapshot()
	if count != 0 {
		t.Fatalf("预期生成次数为0，实际为%d", count)
	}
}

func TestSweepSnapshot_DailyGeneratesOnce(t *testing.T) {
	st := newTestStore(t)
	count := 0
	sch := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {}, 10, 5, 2)
	pageID, err := st.CreateStatusPage(1, "sched-snap", "调度快照页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	st.UpdateStatusPageSnapshotSchedule(pageID, "daily")
	sch.SetSnapshotGenerator(func(pageID int64) error {
		count++
		st.CreateStatusSnapshot(pageID, "schedule", "light", "<html>x</html>")
		return nil
	})
	sch.sweepSnapshot()
	if count != 1 {
		t.Fatalf("预期生成次数为1，实际为%d", count)
	}
	sch.sweepSnapshot()
	if count != 1 {
		t.Fatalf("预期再次sweep后生成次数仍为1，实际为%d", count)
	}
}

func TestSweepSnapshot_ErrorDoesNotBlockOthers(t *testing.T) {
	st := newTestStore(t)
	sch := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {}, 10, 5, 2)
	pageID, err := st.CreateStatusPage(1, "sched-snap", "调度快照页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	st.UpdateStatusPageSnapshotSchedule(pageID, "daily")
	page2, err := st.CreateStatusPage(1, "sched-snap-2", "调度快照页2")
	if err != nil {
		t.Fatalf("创建第二状态页失败: %v", err)
	}
	st.UpdateStatusPageSnapshotSchedule(page2, "daily")
	sch.SetSnapshotGenerator(func(pid int64) error {
		if pid == pageID {
			return fmt.Errorf("boom")
		}
		if _, err := st.CreateStatusSnapshot(pid, "schedule", "light", "<html>x</html>"); err != nil {
			t.Errorf("生成快照失败: %v", err)
		}
		return nil
	})
	sch.sweepSnapshot()
	_, found, err := st.LatestStatusSnapshotAt(page2)
	if err != nil {
		t.Fatalf("查询快照失败: %v", err)
	}
	if !found {
		t.Fatalf("预期page2存在快照，实际未找到")
	}
}

func TestSnapshotRetain_EnvParsing(t *testing.T) {
	t.Setenv("SENTINEL_SNAPSHOT_RETAIN", "2")
	if v := snapshotRetain(); v != 2 {
		t.Fatalf("预期保留天数为2，实际为%d", v)
	}
	t.Setenv("SENTINEL_SNAPSHOT_RETAIN", "bogus")
	if v := snapshotRetain(); v != 30 {
		t.Fatalf("预期无效环境变量下默认保留天数为30，实际为%d", v)
	}
}

func TestMaybeSweepSnapshots_Throttle(t *testing.T) {
	st := newTestStore(t)
	count := 0
	sch := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {}, 10, 5, 2)
	pageID, err := st.CreateStatusPage(1, "sched-snap", "调度快照页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	st.UpdateStatusPageSnapshotSchedule(pageID, "daily")
	sch.SetSnapshotGenerator(func(pageID int64) error {
		count++
		st.CreateStatusSnapshot(pageID, "schedule", "light", "<html>x</html>")
		return nil
	})
	sch.maybeSweepSnapshots()
	sch.maybeSweepSnapshots()
	if count != 1 {
		t.Fatalf("预期节流后生成次数为1，实际为%d", count)
	}
}
