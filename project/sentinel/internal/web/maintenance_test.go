package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestMaintenancePageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/maintenance.html")
	if err != nil {
		t.Fatalf("读取 static/maintenance.html 失败: %v", err)
	}
	page := string(data)
	markers := []string{
		`id="title-input"`,
		`id="monitor-input"`,
		`id="starts-input"`,
		`id="ends-input"`,
		`id="create-btn"`,
		`id="maint-rows"`,
		`id="maint-status"`,
		"/api/maintenance",
		`href="/maintenance" class="active"`,
		"loadMaintenance",
		"deleteMaintenance",
		"createMaintenance",
		"initMaintenance",
	}
	for _, marker := range markers {
		if !strings.Contains(page, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}
}

func TestMaintenancePageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/maintenance.html")
	if err != nil {
		t.Fatalf("读取 static/maintenance.html 失败: %v", err)
	}
	page := string(data)
	statusPos := strings.Index(page, "const maintStatus")
	tryPos := strings.Index(page, "try {")
	if statusPos < 0 {
		t.Errorf("static/maintenance.html 中未找到 maintStatus 定义")
	}
	if tryPos < 0 {
		t.Errorf("static/maintenance.html 中未找到 try { 块")
	}
	if statusPos >= 0 && tryPos >= 0 && !(statusPos < tryPos) {
		t.Errorf("失败路径顺序错误: maintStatus 定义位置 %d 应小于 try { 位置 %d", statusPos, tryPos)
	}
}

func TestMaintenanceNavLinks(t *testing.T) {
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
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, p)
		if err != nil {
			t.Fatalf("读取 %s 失败: %v", p, err)
		}
		if !strings.Contains(string(data), `href="/maintenance"`) {
			t.Errorf("%s 缺少维护窗口导航链", p)
		}
	}
}
