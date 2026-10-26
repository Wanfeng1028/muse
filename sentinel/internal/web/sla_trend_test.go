package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestSLATrendPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/sla_trend.html")
	if err != nil {
		t.Fatalf("读取 static/sla_trend.html 失败: %v", err)
	}
	page := string(data)

	markers := []string{
		`id="months-select"`,
		`id="end-input"`,
		`id="load-btn"`,
		`id="trend-rows"`,
		`id="trend-bars"`,
		`id="export-link"`,
		"/api/sla/trend",
		"/api/sla/trend.html",
		`href="/sla-trend" class="active"`,
	}
	for _, marker := range markers {
		if !strings.Contains(page, marker) {
			t.Errorf("缺少标记: %s", marker)
		}
	}

	iMonths := strings.Index(page, `id="months-select"`)
	iRows := strings.Index(page, `id="trend-rows"`)
	iBars := strings.Index(page, `id="trend-bars"`)
	if iMonths == -1 || iRows == -1 || iBars == -1 {
		return
	}
	if !(iMonths < iRows && iRows < iBars) {
		t.Errorf("标记顺序错误: months-select 位置 %d 应小于 trend-rows 位置 %d，trend-rows 位置 %d 应小于 trend-bars 位置 %d", iMonths, iRows, iRows, iBars)
	}
}

func TestSLATrendPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/sla_trend.html")
	page := string(data)
	if err != nil {
		t.Fatalf("读取 static/sla_trend.html 失败: %v", err)
	}

	const statusMarker = `const status = document.getElementById('trend-status')`
	statusPos := strings.Index(page, statusMarker)
	tryPos := strings.Index(page, "try {")

	if statusPos < 0 {
		t.Errorf("static/sla_trend.html 中未找到 status 定义: %s", statusMarker)
	}
	if tryPos < 0 {
		t.Errorf("static/sla_trend.html 中未找到 try { 块")
	}
	if statusPos < 0 || tryPos < 0 {
		return
	}

	if statusPos >= tryPos {
		t.Errorf("static/sla_trend.html: const status 定义(偏移 %d) 必须位于 try 块(偏移 %d) 之前; 否则请求失败时 catch 中写 status 会命中未初始化的变量", statusPos, tryPos)
	}
}
