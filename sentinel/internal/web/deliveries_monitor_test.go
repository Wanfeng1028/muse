package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestDeliveriesMonitorFilter 检查 v0.20.1 投递记录页监控筛选的页面部分：
// 筛选栏内 id="monitorFilter" 的监控筛选输入框、monitor_id= 参数拼接以及
// monitorFilter 的 change 监听。接口层的 monitor_id 参数此前已落地
// （delivery_deep2_test.go 已覆盖），本轮只补页面。
func TestDeliveriesMonitorFilter(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/deliveries.html")
	if err != nil {
		t.Fatalf("读取 static/deliveries.html 失败: %v", err)
	}
	page := string(data)

	for _, m := range []struct {
		name   string
		marker string
	}{
		{"监控筛选输入框", `id="monitorFilter"`},
		{"monitor_id 参数拼接", "monitor_id="},
		{"statusFilter 输入框（顺序基准）", `id="statusFilter"`},
		{"refreshBtn 按钮（顺序基准）", `id="refreshBtn"`},
	} {
		if !strings.Contains(page, m.marker) {
			t.Errorf("deliveries.html 缺少标记：%s %q", m.name, m.marker)
		}
	}

	if !hasMonitorChangeListener(page) {
		t.Errorf("deliveries.html 缺少 monitorFilter 的 change 监听")
	}

	statusIdx := strings.Index(page, `id="statusFilter"`)
	monitorIdx := strings.Index(page, `id="monitorFilter"`)
	refreshIdx := strings.Index(page, `id="refreshBtn"`)
	if statusIdx >= 0 && monitorIdx >= 0 && refreshIdx >= 0 &&
		!(statusIdx < monitorIdx && monitorIdx < refreshIdx) {
		t.Errorf("监控筛选输入框应位于筛选栏内：期望 statusFilter(%d) < monitorFilter(%d) < refreshBtn(%d)",
			statusIdx, monitorIdx, refreshIdx)
	}
}

// hasMonitorChangeListener 判断页面中某处 monitorFilter 的紧邻代码是否绑定
// change 监听，兼容 addEventListener("change")、on("change")、onchange 等写法。
func hasMonitorChangeListener(page string) bool {
	const window = 200
	off := 0
	for {
		i := strings.Index(page[off:], "monitorFilter")
		if i < 0 {
			return false
		}
		start := off + i + len("monitorFilter")
		end := start + window
		if end > len(page) {
			end = len(page)
		}
		if strings.Contains(page[start:end], "change") {
			return true
		}
		off = start
	}
}
