package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestGroupYearlySLAPageMarkers(t *testing.T) {
	b, err := fs.ReadFile(FS, "static/group_sla_year.html")
	if err != nil {
		t.Fatal(err)
	}
	for _, m := range []string{`id="group-year-select"`, `id="year-input"`, `id="year-load-btn"`, `id="year-rows"`, `id="year-bars"`, `id="year-export-link"`, `id="year-cards"`, `id="year-status"`, "/api/groups/", "/sla/year", "/sla/year.html", `href="/group-sla-year" class="active"`, "loadGroupYearlySLA", "initGroupYearlySLA"} {
		if !strings.Contains(string(b), m) {
			t.Errorf("missing %q", m)
		}
	}
	if !(strings.Index(string(b), `id="year-input"`) < strings.Index(string(b), `id="year-rows"`) && strings.Index(string(b), `id="year-rows"`) < strings.Index(string(b), `id="year-bars"`)) {
		t.Error("bad element order")
	}
}

func TestGroupYearlySLAPageFailurePathOrder(t *testing.T) {
	b, err := fs.ReadFile(FS, "static/group_sla_year.html")
	if err != nil {
		t.Fatal(err)
	}
	iStatus := strings.Index(string(b), "const status")
	iTry := strings.Index(string(b), "try {")
	if iStatus == -1 {
		t.Error("missing \"const status\"")
	}
	if iTry == -1 {
		t.Error("missing \"try {\"")
	}
	if iStatus != -1 && iTry != -1 && iStatus >= iTry {
		t.Error("const status must precede try {")
	}
}

func TestGroupYearlySLANavLinks(t *testing.T) {
	for _, p := range []string{"index.html", "monitors.html", "incidents.html", "deliveries.html", "sms_log.html", "snapshots.html", "sla_report.html", "sla_trend.html", "profile.html", "maintenance.html", "groups.html", "group_sla.html", "group_sla_trend.html", "monitor_sla_trend.html", "sla_year.html"} {
		b, err := fs.ReadFile(FS, "static/"+p)
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(b), `href="/group-sla-year"`) {
			t.Errorf("%s missing href=/group-sla-year", p)
		}
	}
}
