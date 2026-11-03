package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestGroupsPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/groups.html")
	if err != nil {
		t.Fatalf("读取 static/groups.html 失败: %v", err)
	}
	page := string(data)
	markers := []string{
		`id="group-name-input"`,
		`id="group-create-btn"`,
		`id="group-rows"`,
		`id="group-status"`,
		`id="group-select"`,
		`id="member-monitor-input"`,
		`id="member-add-btn"`,
		`id="member-rows"`,
		`id="member-status"`,
		"/api/groups",
		`href="/groups" class="active"`,
		"loadGroups",
		"createGroup",
		"deleteGroup",
		"loadMembers",
		"addMember",
		"removeMember",
		"initGroups",
	}
	for _, marker := range markers {
		if !strings.Contains(page, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}
}

func TestGroupsPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/groups.html")
	if err != nil {
		t.Fatalf("读取 static/groups.html 失败: %v", err)
	}
	page := string(data)
	statusPos := strings.Index(page, "const groupStatus")
	tryPos := strings.Index(page, "try {")
	if statusPos < 0 {
		t.Errorf("static/groups.html 中未找到 groupStatus 定义")
	}
	if tryPos < 0 {
		t.Errorf("static/groups.html 中未找到 try { 块")
	}
	if statusPos >= 0 && tryPos >= 0 && !(statusPos < tryPos) {
		t.Errorf("失败路径顺序错误: groupStatus 定义位置 %d 应小于 try { 位置 %d", statusPos, tryPos)
	}
}

func TestGroupsNavLinks(t *testing.T) {
	pages := []string{
		"static/index.html",
		"static/monitors.html",
		"static/incidents.html",
		"static/deliveries.html",
		"static/sms_log.html",
		"static/snapshots.html",
		"static/sla_report.html",
		"static/sla_trend.html",
		"static/profile.html",
		"static/maintenance.html",
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, p)
		if err != nil {
			t.Fatalf("读取 %s 失败: %v", p, err)
		}
		if !strings.Contains(string(data), `href="/groups"`) {
			t.Errorf("%s 缺少监控分组导航链", p)
		}
	}
}
