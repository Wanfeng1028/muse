package store

import (
	"database/sql"
	"errors"
	"strings"
	"testing"
)

func TestCreateAndGetSnapshot(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	html := "<html>hi</html>"
	id, err := st.CreateStatusSnapshot(pageID, "manual", "dark", html)
	if err != nil {
		t.Fatalf("创建快照失败: %v", err)
	}

	snap, err := st.GetStatusSnapshot(id)
	if err != nil {
		t.Fatalf("获取快照失败: %v", err)
	}

	if snap.HTML != html {
		t.Fatalf("期望 HTML 为 %q, 实际为 %q", html, snap.HTML)
	}
	if snap.SizeBytes != int64(len(html)) {
		t.Fatalf("期望 SizeBytes 为 %d, 实际为 %d", int64(len(html)), snap.SizeBytes)
	}
	if snap.Generator != "manual" {
		t.Fatalf("期望 Generator 为 %q, 实际为 %q", "manual", snap.Generator)
	}
	if snap.Theme != "dark" {
		t.Fatalf("期望 Theme 为 %q, 实际为 %q", "dark", snap.Theme)
	}
	if snap.PageID != pageID {
		t.Fatalf("期望 PageID 为 %d, 实际为 %d", pageID, snap.PageID)
	}
	if snap.CreatedAt == "" {
		t.Fatalf("期望 CreatedAt 非空, 实际为空")
	}
}

func TestCreateSnapshotValidation(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	_, err = st.CreateStatusSnapshot(pageID, "manual", "dark", "")
	if err == nil {
		t.Fatalf("期望 html 为空时返回错误, 实际未返回错误")
	}

	_, err = st.CreateStatusSnapshot(pageID, "bogus", "dark", "<html></html>")
	if err == nil {
		t.Fatalf("期望 generator 为 bogus 时返回错误, 实际未返回错误")
	}

	id, err := st.CreateStatusSnapshot(pageID, "manual", "", "<html></html>")
	if err != nil {
		t.Fatalf("创建快照（theme 为空）失败: %v", err)
	}
	snap, err := st.GetStatusSnapshot(id)
	if err != nil {
		t.Fatalf("获取快照失败: %v", err)
	}
	if snap.Theme != "light" {
		t.Fatalf("期望 theme 空字符串默认存为 %q, 实际为 %q", "light", snap.Theme)
	}
}

func TestListSnapshotsOrderAndNoHTML(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	id1, _ := st.CreateStatusSnapshot(pageID, "manual", "light", "<html>1</html>")
	id2, _ := st.CreateStatusSnapshot(pageID, "manual", "light", "<html>2</html>")
	id3, _ := st.CreateStatusSnapshot(pageID, "manual", "light", "<html>3</html>")

	snaps, err := st.ListStatusSnapshots(pageID, 10)
	if err != nil {
		t.Fatalf("列出快照失败: %v", err)
	}
	if len(snaps) != 3 {
		t.Fatalf("期望快照数量为 3, 实际为 %d", len(snaps))
	}
	if snaps[0].ID != id3 || snaps[1].ID != id2 || snaps[2].ID != id1 {
		t.Fatalf("期望快照按 id 倒序排列, 实际顺序为 %d, %d, %d", snaps[0].ID, snaps[1].ID, snaps[2].ID)
	}
	for i, s := range snaps {
		if s.HTML != "" {
			t.Fatalf("期望第 %d 条快照 HTML 为空, 实际为 %q", i, s.HTML)
		}
		if s.SizeBytes <= 0 {
			t.Fatalf("期望第 %d 条快照 SizeBytes > 0, 实际为 %d", i, s.SizeBytes)
		}
	}
}

func TestGetSnapshotNotFound(t *testing.T) {
	st := newTestStore(t)
	_, err := st.GetStatusSnapshot(999999)
	if err == nil {
		t.Fatalf("期望获取不存在的快照返回错误, 实际未返回错误")
	}
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("期望错误为 sql.ErrNoRows, 实际为 %v", err)
	}
}

func TestDeleteSnapshotIdempotent(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	id, err := st.CreateStatusSnapshot(pageID, "manual", "light", "<html>del</html>")
	if err != nil {
		t.Fatalf("创建快照失败: %v", err)
	}

	if err := st.DeleteStatusSnapshot(id); err != nil {
		t.Fatalf("第一次删除快照期望无错误, 实际错误: %v", err)
	}
	if err := st.DeleteStatusSnapshot(id); err != nil {
		t.Fatalf("第二次删除快照期望无错误, 实际错误: %v", err)
	}

	_, err = st.GetStatusSnapshot(id)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("期望删除后获取快照返回 sql.ErrNoRows, 实际错误: %v", err)
	}
}

func TestPruneSnapshots(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	var ids []int64
	for i := 0; i < 5; i++ {
		id, err := st.CreateStatusSnapshot(pageID, "manual", "light", "<html>prune</html>")
		if err != nil {
			t.Fatalf("创建第 %d 条快照失败: %v", i+1, err)
		}
		ids = append(ids, id)
	}

	deleted, err := st.PruneStatusSnapshots(pageID, 2)
	if err != nil {
		t.Fatalf("Prune 快照失败: %v", err)
	}
	if deleted != 3 {
		t.Fatalf("期望 Prune 删除 3 条, 实际删除 %d 条", deleted)
	}

	snaps, err := st.ListStatusSnapshots(pageID, 10)
	if err != nil {
		t.Fatalf("列出快照失败: %v", err)
	}
	if len(snaps) != 2 {
		t.Fatalf("期望剩余快照数量为 2, 实际为 %d", len(snaps))
	}
	if snaps[0].ID != ids[4] || snaps[1].ID != ids[3] {
		t.Fatalf("期望剩余快照为最新的 2 条 (id=%d, %d), 实际为 (id=%d, %d)", ids[4], ids[3], snaps[0].ID, snaps[1].ID)
	}

	deleted, err = st.PruneStatusSnapshots(pageID, 0)
	if err != nil {
		t.Fatalf("Prune(keep=0) 失败: %v", err)
	}
	if deleted != 0 {
		t.Fatalf("期望 Prune(keep=0) 删除 0 条, 实际删除 %d 条", deleted)
	}
	snaps2, err := st.ListStatusSnapshots(pageID, 10)
	if err != nil {
		t.Fatalf("列出快照失败: %v", err)
	}
	if len(snaps2) != 2 {
		t.Fatalf("期望 Prune(keep=0) 后快照数量仍为 2, 实际为 %d", len(snaps2))
	}
}

func TestLatestStatusSnapshotAt(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	_, found, err := st.LatestStatusSnapshotAt(pageID)
	if err != nil {
		t.Fatalf("LatestStatusSnapshotAt 失败: %v", err)
	}
	if found {
		t.Fatalf("期望无快照时 found 为 false, 实际为 true")
	}

	_, err = st.CreateStatusSnapshot(pageID, "manual", "light", "<html>a</html>")
	if err != nil {
		t.Fatalf("创建第 1 条快照失败: %v", err)
	}
	id2, err := st.CreateStatusSnapshot(pageID, "manual", "light", "<html>b</html>")
	if err != nil {
		t.Fatalf("创建第 2 条快照失败: %v", err)
	}

	at, found, err := st.LatestStatusSnapshotAt(pageID)
	if err != nil {
		t.Fatalf("LatestStatusSnapshotAt 失败: %v", err)
	}
	if !found {
		t.Fatalf("期望有快照时 found 为 true, 实际为 false")
	}
	snap2, err := st.GetStatusSnapshot(id2)
	if err != nil {
		t.Fatalf("获取第 2 条快照失败: %v", err)
	}
	if at != snap2.CreatedAt {
		t.Fatalf("期望 at 等于最新快照的 CreatedAt %q, 实际为 %q", snap2.CreatedAt, at)
	}
}

func TestUpdateSnapshotSchedule(t *testing.T) {
	st := newTestStore(t)
	pageID, err := st.CreateStatusPage(1, "snap-test", "快照测试页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	if err := st.UpdateStatusPageSnapshotSchedule(pageID, "daily"); err != nil {
		t.Fatalf("更新快照计划为 daily 失败: %v", err)
	}

	page, err := st.GetStatusPage(pageID)
	if err != nil {
		t.Fatalf("获取状态页失败: %v", err)
	}
	if page.SnapshotSchedule != "daily" {
		t.Fatalf("期望 SnapshotSchedule 为 %q, 实际为 %q", "daily", page.SnapshotSchedule)
	}

	err = st.UpdateStatusPageSnapshotSchedule(pageID, "bogus")
	if err == nil {
		t.Fatalf("期望更新快照计划为 bogus 时返回错误, 实际未返回错误")
	}
	if !strings.Contains(err.Error(), "snapshot_schedule") {
		t.Fatalf("期望错误信息包含 %q, 实际为 %q", "snapshot_schedule", err.Error())
	}

	for _, s := range []string{"off", "daily", "hourly"} {
		if !ValidSnapshotSchedule(s) {
			t.Fatalf("期望 ValidSnapshotSchedule(%q) 为 true, 实际为 false", s)
		}
	}
	for _, s := range []string{"", "weekly"} {
		if ValidSnapshotSchedule(s) {
			t.Fatalf("期望 ValidSnapshotSchedule(%q) 为 false, 实际为 true", s)
		}
	}
}
