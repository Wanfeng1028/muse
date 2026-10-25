package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestSmsLogMonitorFilter 是 v0.20.0 短信记录关联监控功能的页面静态标记测试：
// 校验 static/sms_log.html 包含监控筛选输入框、表格监控列头、monitor_id 参数拼接
// 与 r.monitor_id 渲染取值四处标记，并校验监控筛选输入框位于 main 容器开标签之后、
// 表格之前（即筛选区在容器内）。
func TestSmsLogMonitorFilter(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/sms_log.html")
	if err != nil {
		t.Fatalf("读取 static/sms_log.html 失败: %v", err)
	}
	page := string(data)

	if !strings.Contains(page, `id="filter-monitor"`) {
		t.Errorf("页面缺少监控筛选输入框标记 id=%q", "filter-monitor")
	}
	if !strings.Contains(page, "监控</th>") {
		t.Errorf("页面缺少表格监控列头标记 监控</th>")
	}
	if !strings.Contains(page, "monitor_id=") {
		t.Errorf("页面缺少 monitor_id= 参数拼接标记")
	}
	if !strings.Contains(page, "r.monitor_id") {
		t.Errorf("页面缺少 r.monitor_id 渲染取值标记")
	}

	mainIdx := strings.Index(page, "<main")
	filterIdx := strings.Index(page, `id="filter-monitor"`)
	tableIdx := strings.Index(page, "<table")
	if mainIdx == -1 {
		t.Errorf("页面缺少 main 容器开标记 <main，无法校验筛选区顺序")
		return
	}
	if filterIdx == -1 || tableIdx == -1 {
		// 对应标记缺失已由上方 Contains 断言报告
		return
	}
	if filterIdx < mainIdx {
		t.Errorf("监控筛选输入框应位于 main 容器开标签之后: filter=%d, main=%d", filterIdx, mainIdx)
	}
	if filterIdx > tableIdx {
		t.Errorf("监控筛选输入框应位于表格之前: filter=%d, table=%d", filterIdx, tableIdx)
	}
}
