package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestMonitorSLATrendPageMarkers(t *testing.T) {
	page, err := fs.ReadFile(FS, "static/monitor_sla_trend.html")
	if err != nil {
		t.Fatalf("读取 monitor_sla_trend.html 失败: %v", err)
	}
	content := string(page)
	markers := []string{
		`id="monitor-trend-select"`,
		`id="monitor-trend-end-input"`,
		`id="monitor-trend-months-select"`,
		`id="monitor-trend-load-btn"`,
		`id="monitor-trend-rows"`,
		`id="monitor-trend-bars"`,
		`id="monitor-trend-export-link"`,
		`id="monitor-trend-cards"`,
		`id="monitor-trend-status"`,
		"/api/monitors",
		"/sla/trend",
		"/sla/trend.html",
		`href="/monitor-sla-trend" class="active"`,
		"loadMonitorSLATrend",
		"loadMonitorSLATrendOptions",
		"initMonitorSLATrend",
	}
	for _, marker := range markers {
		if !strings.Contains(content, marker) {
			t.Errorf("页面缺少标记 %q", marker)
		}
	}
	selectPos := strings.Index(content, `id="monitor-trend-select"`)
	rowsPos := strings.Index(content, `id="monitor-trend-rows"`)
	barsPos := strings.Index(content, `id="monitor-trend-bars"`)
	if !(selectPos < rowsPos && rowsPos < barsPos) {
		t.Errorf("元素顺序错误: select(%d) < rows(%d) < bars(%d) 不成立", selectPos, rowsPos, barsPos)
	}
}

func TestMonitorSLATrendPageFailurePathOrder(t *testing.T) {
	page, err := fs.ReadFile(FS, "static/monitor_sla_trend.html")
	if err != nil {
		t.Fatalf("读取 monitor_sla_trend.html 失败: %v", err)
	}
	content := string(page)
	statusPos := strings.Index(content, "const status")
	tryPos := strings.Index(content, "try {")
	if statusPos < 0 {
		t.Errorf("页面中未找到 \"const status\"")
	}
	if tryPos < 0 {
		t.Errorf("页面中未找到 \"try {\"")
	}
	if statusPos >= tryPos {
		t.Errorf("失败路径顺序错误: \"const status\"(%d) 应位于 \"try {\"(%d) 之后", statusPos, tryPos)
	}
}

func TestMonitorSLATrendNavLinks(t *testing.T) {
	pages := []string{
		"static/index.html", "static/monitors.html", "static/incidents.html",
		"static/deliveries.html", "static/sms_log.html", "static/snapshots.html",
		"static/sla_report.html", "static/sla_trend.html", "static/profile.html",
		"static/maintenance.html", "static/groups.html", "static/group_sla.html",
		"static/group_sla_trend.html",
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, p)
		if err != nil {
			t.Errorf("读取页面 %s 失败: %v", p, err)
			continue
		}
		if !strings.Contains(string(data), `href="/monitor-sla-trend"`) {
			t.Errorf("%s 缺少单监控SLA趋势导航链", p)
		}
	}
}
