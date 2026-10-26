package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestMonitorYearlySLAPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/monitor_sla_year.html")
	if err != nil {
		t.Fatalf("read monitor_sla_year.html: %v", err)
	}
	page := string(data)

	markers := []string{
		`id="monitor-year-select"`,
		`id="year-input"`,
		`id="year-load-btn"`,
		`id="year-rows"`,
		`id="year-bars"`,
		`id="year-export-link"`,
		`id="year-cards"`,
		`id="year-status"`,
		`/api/monitors/`,
		`/sla/year`,
		`/sla/year.html`,
		`href="/monitor-sla-year" class="active"`,
		`loadMonitorYearlySLA`,
		`initMonitorYearlySLA`,
	}
	for _, m := range markers {
		if !strings.Contains(page, m) {
			t.Errorf("monitor_sla_year.html missing marker %q", m)
		}
	}

	i := strings.Index(page, `id="year-input"`)
	j := strings.Index(page, `id="year-rows"`)
	k := strings.Index(page, `id="year-bars"`)
	if i < 0 || j < 0 || k < 0 {
		t.Fatalf("monitor_sla_year.html missing year markers")
	}
	if i > j {
		t.Errorf(`id="year-input" should appear before id="year-rows"`)
	}
	if j > k {
		t.Errorf(`id="year-rows" should appear before id="year-bars"`)
	}
}

func TestMonitorYearlySLAPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/monitor_sla_year.html")
	if err != nil {
		t.Fatalf("read monitor_sla_year.html: %v", err)
	}
	page := string(data)

	statusIdx := strings.Index(page, "const status")
	if statusIdx < 0 {
		t.Fatalf("monitor_sla_year.html missing `const status`")
	}
	tryIdx := strings.Index(page, "try {")
	if tryIdx < 0 {
		t.Fatalf("monitor_sla_year.html missing `try {`")
	}
	if statusIdx > tryIdx {
		t.Errorf("`const status` should appear before `try {`")
	}
}

func TestMonitorYearlySLANavLinks(t *testing.T) {
	pages := []string{
		"index.html",
		"monitors.html",
		"incidents.html",
		"deliveries.html",
		"sms_log.html",
		"snapshots.html",
		"sla_report.html",
		"sla_trend.html",
		"profile.html",
		"maintenance.html",
		"groups.html",
		"group_sla.html",
		"group_sla_trend.html",
		"monitor_sla_trend.html",
		"sla_year.html",
		"group_sla_year.html",
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, "static/"+p)
		if err != nil {
			t.Fatalf("read %s: %v", p, err)
		}
		if !strings.Contains(string(data), `href="/monitor-sla-year"`) {
			t.Errorf("%s missing href=\"/monitor-sla-year\"", p)
		}
	}
}