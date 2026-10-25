package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestIncidentsDetail_StaticMarkers asserts that the incidents page contains
// all required static HTML/JS markers for the "click row to expand detail"
// feature (v0.13.0). This test only verifies that the static markers are
// present in the embedded file; it does not test browser-side click behavior.

func TestIncidentsDetail_StaticMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	s := string(data)
	markers := []string{
		"incident-row",
		"incident-detail",
		"tabindex",
		"aria-expanded",
		"colSpan = 6",
		"点击查看详情",
	}
	for _, m := range markers {
		if !strings.Contains(s, m) {
			t.Errorf("missing marker: %s", m)
		}
	}
}

// TestIncidentsDetail_Fields asserts that all seven detail field labels are
// present. This test only verifies static markers; it does not test
// browser-side rendering or interaction.

func TestIncidentsDetail_Fields(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	s := string(data)
	labels := []string{
		"事件 ID",
		"监控",
		"开始时间",
		"恢复时间",
		"持续",
		"状态",
		"触发原因",
	}
	for _, l := range labels {
		if !strings.Contains(s, l) {
			t.Errorf("missing field label: %s", l)
		}
	}
}

// TestIncidentsDetail_SingleOpenAndKeyboard asserts that the single-open
// logic variables and keyboard toggle branches exist. This test only
// verifies static markers; it does not test browser-side JS execution.

func TestIncidentsDetail_SingleOpenAndKeyboard(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	s := string(data)
	markers := []string{
		"expandedRow",
		"expandedDetail",
		"key === \"Enter\"",
		"key === \" \"",
	}
	for _, m := range markers {
		if !strings.Contains(s, m) {
			t.Errorf("missing marker: %s", m)
		}
	}
}

// TestIncidentsDetail_SubtitleHint asserts that the subtitle hint text is
// present. This test only verifies static markers; it does not test
// browser-side display.

func TestIncidentsDetail_SubtitleHint(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	s := string(data)
	hint := "点击一行可展开详情。"
	if !strings.Contains(s, hint) {
		t.Errorf("missing marker: %s", hint)
	}
}
// TestIncidentsDetail_V014Markers asserts v0.14.0 detail additions are present:
// the detail fetch and the two new field labels. Static markers only;
// browser-side fetch behavior is covered by the real-service smoke test.
func TestIncidentsDetail_V014Markers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	s := string(data)
	for _, m := range []string{"fetch(\"/api/incidents/\"", "恢复检查", "通知记录", "暂无通知记录"} {
		if !strings.Contains(s, m) {
			t.Errorf("missing marker: %s", m)
		}
	}
}
