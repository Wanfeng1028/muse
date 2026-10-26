package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestGroupSLATrendPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/group_sla_trend.html")
	if err != nil {
		t.Fatalf("读取 static/group_sla_trend.html 失败: %v", err)
	}
	page := string(data)
	markers := []string{
		`id="group-trend-select"`,
		`id="group-trend-end-input"`,
		`id="group-trend-months-select"`,
		`id="group-trend-load-btn"`,
		`id="group-trend-rows"`,
		`id="group-trend-bars"`,
		`id="group-trend-export-link"`,
		`id="group-trend-cards"`,
		`id="group-trend-status"`,
		`/api/groups`,
		`/sla/trend`,
		`/sla/trend.html`,
		`href="/group-sla-trend" class="active"`,
		`loadGroupSLATrend`,
		`loadGroupSLATrendOptions`,
		`initGroupSLATrend`,
	}
	for _, marker := range markers {
		if !strings.Contains(page, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}
	iSelect := strings.Index(page, `id="group-trend-select"`)
	iRows := strings.Index(page, `id="group-trend-rows"`)
	iBars := strings.Index(page, `id="group-trend-bars"`)
	if iSelect == -1 || iRows == -1 || iBars == -1 {
		return
	}
	if !(iSelect < iRows && iRows < iBars) {
		t.Errorf("标记顺序错误: select %d rows %d bars %d", iSelect, iRows, iBars)
	}
}

func TestGroupSLATrendPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/group_sla_trend.html")
	if err != nil {
		t.Fatalf("读取 static/group_sla_trend.html 失败: %v", err)
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

func TestGroupSLATrendNavLinks(t *testing.T) {
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
		"static/group_sla.html",
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, p)
		if err != nil {
			t.Errorf("读取 %s 失败: %v", p, err)
			continue
		}
		if !strings.Contains(string(data), `href="/group-sla-trend"`) {
			t.Errorf("%s 缺少分组SLA趋势导航链", p)
		}
	}
}
