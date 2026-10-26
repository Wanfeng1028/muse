package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestGroupSLAPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/group_sla.html")
	if err != nil {
		t.Fatalf("读取 group_sla.html 失败: %v", err)
	}
	page := string(data)
	markers := []string{
		`id="group-sla-select"`,
		`id="group-sla-month-input"`,
		`id="group-sla-load-btn"`,
		`id="group-sla-rows"`,
		`id="group-sla-status"`,
		`id="group-sla-cards"`,
		`id="group-sla-export-link"`,
		`/api/groups`,
		`href="/group-sla" class="active"`,
		`loadGroupSLA`,
		`loadGroupSLAOptions`,
		`renderGroupSLARows`,
		`initGroupSLA`,
	}
	for _, marker := range markers {
		if !strings.Contains(page, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}
}

func TestGroupSLAPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/group_sla.html")
	if err != nil {
		t.Fatalf("读取 group_sla.html 失败: %v", err)
	}
	page := string(data)
	statusPos := strings.Index(page, "const status")
	tryPos := strings.Index(page, "try {")
	if statusPos < 0 {
		t.Errorf("未找到 status 定义")
	}
	if tryPos < 0 {
		t.Errorf("未找到 try 块")
	}
	if statusPos >= 0 && tryPos >= 0 && !(statusPos < tryPos) {
		t.Errorf("失败路径顺序错误")
	}
}

func TestGroupSLANavLinks(t *testing.T) {
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
		"static/groups.html",
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, p)
		if err != nil {
			t.Errorf("读取 %s 失败: %v", p, err)
			continue
		}
		if !strings.Contains(string(data), `href="/group-sla"`) {
			t.Errorf("%s 缺少分组SLA导航链", p)
		}
	}
}
