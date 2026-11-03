package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestMonitorLatencyTrendPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/monitor_latency_trend.html")
	if err != nil {
		t.Fatalf("读取 static/monitor_latency_trend.html 失败: %v", err)
	}
	html := string(data)

	markers := []string{
		`id="monitor-latency-select"`,
		`id="monitor-latency-end-input"`,
		`id="monitor-latency-months-select"`,
		`id="monitor-latency-load-btn"`,
		`id="monitor-latency-rows"`,
		`id="monitor-latency-bars"`,
		`id="monitor-latency-export-link"`,
		`id="monitor-latency-cards"`,
		`id="monitor-latency-status"`,
		"/api/monitors/",
		"/latency/trend",
		"/latency/trend.html",
		`href="/monitor-latency-trend" class="active"`,
		"loadMonitorLatencyTrend",
		"initMonitorLatencyTrend",
		"loadMonitorLatencyTrendOptions",
	}
	for _, marker := range markers {
		if !strings.Contains(html, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}

	monthsOffset := strings.Index(html, `id="monitor-latency-months-select"`)
	rowsOffset := strings.Index(html, `id="monitor-latency-rows"`)
	barsOffset := strings.Index(html, `id="monitor-latency-bars"`)
	if monthsOffset == -1 || rowsOffset == -1 || barsOffset == -1 {
		t.Errorf("顺序检查所需标记缺失: months-select 偏移 %d, rows 偏移 %d, bars 偏移 %d", monthsOffset, rowsOffset, barsOffset)
		return
	}
	if !(monthsOffset < rowsOffset && rowsOffset < barsOffset) {
		t.Errorf("页面标记顺序错误: months-select 偏移 %d, rows 偏移 %d, bars 偏移 %d, 期望 months-select < rows < bars", monthsOffset, rowsOffset, barsOffset)
	}
}

func TestMonitorLatencyTrendPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/monitor_latency_trend.html")
	if err != nil {
		t.Fatalf("读取 static/monitor_latency_trend.html 失败: %v", err)
	}
	html := string(data)

	statusMarker := "const status = document.getElementById('monitor-latency-status')"
	tryMarker := "try {"

	statusOffset := strings.Index(html, statusMarker)
	if statusOffset == -1 {
		t.Errorf("缺少标记: %s", statusMarker)
		return
	}
	tryOffset := strings.Index(html, tryMarker)
	if tryOffset == -1 {
		t.Errorf("缺少标记: %s", tryMarker)
		return
	}
	if statusOffset > tryOffset {
		t.Errorf("static/monitor_latency_trend.html 中 status 定义偏移 %d 应在 try { 偏移 %d 之前", statusOffset, tryOffset)
	}
}

func TestMonitorLatencyTrendNavChain(t *testing.T) {
	pages := []string{
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
		"static/latency_trend.html",
		"static/group_latency_trend.html",
	}
	for _, page := range pages {
		data, err := fs.ReadFile(FS, page)
		if err != nil {
			t.Errorf("读取 %s 失败: %v", page, err)
			continue
		}
		if !strings.Contains(string(data), `<a href="/monitor-latency-trend">单监控延迟趋势</a>`) {
			t.Errorf("%s 缺少监控延迟趋势导航链接", page)
		}
	}

	data, err := fs.ReadFile(FS, "static/monitor_latency_trend.html")
	if err != nil {
		t.Fatalf("读取 static/monitor_latency_trend.html 失败: %v", err)
	}
	if !strings.Contains(string(data), `<a href="/monitor-latency-trend" class="active">单监控延迟趋势</a>`) {
		t.Errorf("static/monitor_latency_trend.html 缺少 active 监控延迟趋势导航链接")
	}
}
