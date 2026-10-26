package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestLatencyTrendPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/latency_trend.html")
	if err != nil {
		t.Fatalf("读取 static/latency_trend.html: %v", err)
	}
	page := string(data)

	markers := []string{
		`id="months-select"`,
		`id="end-input"`,
		`id="load-btn"`,
		`id="latency-rows"`,
		`id="latency-bars"`,
		`id="export-link"`,
		`id="latency-cards"`,
		`id="latency-status"`,
		"/api/latency/trend",
		"/api/latency/trend.html",
		`href="/latency-trend" class="active"`,
		"loadSiteLatencyTrend",
		"initSiteLatencyTrend",
	}
	for _, marker := range markers {
		if !strings.Contains(page, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}

	iMonths := strings.Index(page, `id="months-select"`)
	iRows := strings.Index(page, `id="latency-rows"`)
	iBars := strings.Index(page, `id="latency-bars"`)
	if iMonths < 0 || iRows < 0 || iBars < 0 {
		return
	}
	if !(iMonths < iRows && iRows < iBars) {
		t.Errorf("页面元素顺序错误: months-select 偏移 %d, latency-rows 偏移 %d, latency-bars 偏移 %d, 期望 months-select < latency-rows < latency-bars", iMonths, iRows, iBars)
	}
}

func TestLatencyTrendPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/latency_trend.html")
	if err != nil {
		t.Fatalf("读取 static/latency_trend.html: %v", err)
	}
	page := string(data)

	const statusMarker = `const status = document.getElementById('latency-status')`
	statusPos := strings.Index(page, statusMarker)
	tryPos := strings.Index(page, "try {")

	if statusPos < 0 {
		t.Errorf("static/latency_trend.html 中未找到 status 定义: %s", statusMarker)
	}
	if tryPos < 0 {
		t.Errorf("static/latency_trend.html 中未找到 try { 块")
	}
	if statusPos < 0 || tryPos < 0 {
		return
	}

	if statusPos >= tryPos {
		t.Errorf("status 定义偏移 %d 未位于 try { 块偏移 %d 之前: 请求失败时 catch 中写 status 会命中未初始化的变量", statusPos, tryPos)
	}
}

func TestLatencyTrendNavChain(t *testing.T) {
	pages := []string{
		"static/index.html",
		"static/monitors.html",
		"static/incidents.html",
		"static/deliveries.html",
		"static/snapshots.html",
		"static/sms_log.html",
		"static/sla_report.html",
		"static/sla_trend.html",
		"static/sla_year.html",
		"static/maintenance.html",
		"static/groups.html",
		"static/group_sla.html",
		"static/group_sla_trend.html",
		"static/group_sla_year.html",
		"static/monitor_sla_trend.html",
		"static/monitor_sla_year.html",
		"static/profile.html",
	}

	for _, page := range pages {
		body, err := fs.ReadFile(FS, page)
		if err != nil {
			t.Fatalf("读取 %s 失败: %v", page, err)
		}
		if !strings.Contains(string(body), `<a href="/latency-trend">延迟趋势</a>`) {
			t.Errorf("%s 缺少延迟趋势导航链接", page)
		}
	}

	body, err := fs.ReadFile(FS, "static/latency_trend.html")
	if err != nil {
		t.Fatalf("读取 static/latency_trend.html 失败: %v", err)
	}
	if !strings.Contains(string(body), `<a href="/latency-trend" class="active">延迟趋势</a>`) {
		t.Errorf("static/latency_trend.html 缺少 active 延迟趋势导航链接")
	}
}
