package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestDesignV016_Layer asserts v0.16.0 design layer markers: the layer file
// exists, contains the ledger rules for monitors/deliveries, carries no
// banned patterns, and is referenced after each page's inline <style> block.
// Static markers only; browser rendering is covered by the real-service
// screenshot check.
func TestDesignV016_Layer(t *testing.T) {
	css, err := fs.ReadFile(FS, "static/design-v016.css")
	if err != nil {
		t.Fatalf("read design-v016.css: %v", err)
	}
	s := string(css)
	for _, m := range []string{
		"#monitor-table thead th",
		"#monitor-table tbody td",
		".card",
		".page-header h1",
		".table-wrapper table thead th",
		"text-transform: none",
		"box-shadow: none",
		"值班日志本",
	} {
		if !strings.Contains(s, m) {
			t.Errorf("missing design marker: %s", m)
		}
	}
	for _, banned := range []string{"gradient", "Inter", "${", "!important"} {
		if strings.Contains(s, banned) {
			t.Errorf("banned pattern in design layer: %s", banned)
		}
	}
	for _, p := range []string{"monitors.html", "deliveries.html"} {
		data, err := fs.ReadFile(FS, "static/"+p)
		if err != nil {
			t.Fatalf("read %s: %v", p, err)
		}
		h := string(data)
		style := strings.Index(h, "</style>")
		layer := strings.Index(h, "/static/design-v016.css")
		if style < 0 || layer < 0 || layer < style {
			t.Errorf("%s: design layer must be referenced after inline <style> block", p)
		}
	}
	mon, err := fs.ReadFile(FS, "static/monitors.html")
	if err != nil {
		t.Fatalf("read monitors.html: %v", err)
	}
	for _, sel := range []string{`id="monitor-table"`, `class="card"`} {
		if !strings.Contains(string(mon), sel) {
			t.Errorf("monitors.html: missing selector anchor %s", sel)
		}
	}
	del, err := fs.ReadFile(FS, "static/deliveries.html")
	if err != nil {
		t.Fatalf("read deliveries.html: %v", err)
	}
	for _, sel := range []string{`class="page-header"`, `class="table-wrapper"`} {
		if !strings.Contains(string(del), sel) {
			t.Errorf("deliveries.html: missing selector anchor %s", sel)
		}
	}
	// app.js must load synchronously before the inline script: with defer,
	// the inline script's first loadDeliveries() call runs while api is still
	// undefined and the page sticks on its loading row until Refresh.
	if strings.Contains(string(del), `<script src="/static/app.js" defer>`) {
		t.Errorf("deliveries.html: app.js must not be deferred before the inline script")
	}
}
