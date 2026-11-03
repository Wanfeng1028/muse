package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestSiteYearlySLAPageMarkers(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/sla_year.html")
	if err != nil {
		t.Fatalf("read static/sla_year.html: %v", err)
	}
	page := string(data)
	markers := []string{
		`id="year-input"`,
		`id="year-load-btn"`,
		`id="year-rows"`,
		`id="year-bars"`,
		`id="year-export-link"`,
		`id="year-cards"`,
		`id="year-status"`,
		"/api/sla/year",
		"/api/sla/year.html",
		`href="/sla-year" class="active"`,
		"loadSiteYearlySLA",
		"initSiteYearlySLA",
	}
	for _, m := range markers {
		if !strings.Contains(page, m) {
			t.Errorf("static/sla_year.html missing marker %q", m)
		}
	}
	iInput := strings.Index(page, `id="year-input"`)
	iRows := strings.Index(page, `id="year-rows"`)
	iBars := strings.Index(page, `id="year-bars"`)
	if iInput == -1 || iRows == -1 || iBars == -1 {
		t.Errorf("static/sla_year.html missing order markers, cannot verify order")
		return
	}
	if !(iInput < iRows && iRows < iBars) {
		t.Errorf("static/sla_year.html bad order: id=\"year-input\" at %d, id=\"year-rows\" at %d, id=\"year-bars\" at %d", iInput, iRows, iBars)
	}
}

func TestSiteYearlySLAPageFailurePathOrder(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/sla_year.html")
	if err != nil {
		t.Fatalf("read static/sla_year.html: %v", err)
	}
	page := string(data)
	iStatus := strings.Index(page, "const status")
	iTry := strings.Index(page, "try {")
	if iStatus == -1 {
		t.Errorf("static/sla_year.html missing \"const status\"")
	}
	if iTry == -1 {
		t.Errorf("static/sla_year.html missing \"try {\"")
	}
	if iStatus == -1 || iTry == -1 {
		return
	}
	if iStatus >= iTry {
		t.Errorf("static/sla_year.html: \"const status\" at %d should appear before \"try {\" at %d", iStatus, iTry)
	}
}

func TestSiteYearlySLANavLinks(t *testing.T) {
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
		"static/group_sla_trend.html",
		"static/monitor_sla_trend.html",
	}
	for _, name := range pages {
		data, err := fs.ReadFile(FS, name)
		if err != nil {
			t.Errorf("read %s: %v", name, err)
			continue
		}
		if !strings.Contains(string(data), `href="/sla-year"`) {
			t.Errorf("%s missing href=\"/sla-year\"", name)
		}
	}
}
