package store

import "testing"

func TestCreateGroupAndList(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateGroup("核心业务")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	if id <= 0 {
		t.Fatalf("期望正 id，得到 %d", id)
	}
	list, err := st.ListGroups()
	if err != nil {
		t.Fatalf("ListGroups: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("期望 1 条，得到 %d", len(list))
	}
	got := list[0]
	if got.ID != id || got.Name != "核心业务" || got.MonitorCount != 0 {
		t.Fatalf("列表内容不符: %+v", got)
	}
}

func TestCreateGroupRejects(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateGroup("   "); err == nil {
		t.Fatalf("期望空名被拒")
	}
	if _, err := st.CreateGroup("同名"); err != nil {
		t.Fatalf("首次创建: %v", err)
	}
	if _, err := st.CreateGroup("同名"); err == nil {
		t.Fatalf("期望重名被拒")
	}
}

func TestGroupMembers(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	gid, err := st.CreateGroup("组A")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	if err := st.AddMonitorToGroup(gid, mid); err != nil {
		t.Fatalf("AddMonitorToGroup: %v", err)
	}
	if err := st.AddMonitorToGroup(gid, mid); err != nil {
		t.Fatalf("重复加入应幂等: %v", err)
	}
	members, err := st.ListGroupMonitors(gid)
	if err != nil {
		t.Fatalf("ListGroupMonitors: %v", err)
	}
	if len(members) != 1 || members[0].ID != mid {
		t.Fatalf("期望成员 1 条且为该监控，得到 %+v", members)
	}
	if err := st.AddMonitorToGroup(999999, mid); err == nil {
		t.Fatalf("期望不存在的分组被拒")
	}
	if err := st.AddMonitorToGroup(gid, 999999); err == nil {
		t.Fatalf("期望不存在的监控被拒")
	}
	if err := st.RemoveMonitorFromGroup(gid, mid); err != nil {
		t.Fatalf("RemoveMonitorFromGroup: %v", err)
	}
	members, err = st.ListGroupMonitors(gid)
	if err != nil {
		t.Fatalf("ListGroupMonitors: %v", err)
	}
	if len(members) != 0 {
		t.Fatalf("移出后期望 0 条，得到 %d", len(members))
	}
	if err := st.AddMonitorToGroup(gid, mid); err != nil {
		t.Fatalf("重新加入: %v", err)
	}
	if err := st.DeleteGroup(gid); err != nil {
		t.Fatalf("DeleteGroup: %v", err)
	}
	members, err = st.ListGroupMonitors(gid)
	if err != nil {
		t.Fatalf("删组后 ListGroupMonitors: %v", err)
	}
	if len(members) != 0 {
		t.Fatalf("删组后期望成员 0 条，得到 %d", len(members))
	}
}
