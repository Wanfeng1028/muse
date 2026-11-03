package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestDesignV015_Layer asserts v0.15.0 design layer markers: the layer file
// exists, contains the ledger rules, carries no banned patterns, and is
// referenced after style.css on every style.css page. Static markers only;
// browser rendering is covered by the real-service screenshot check.
func TestDesignV015_Layer(t *testing.T) {
	css, err := fs.ReadFile(FS, "static/design-v015.css")
	if err != nil {
		t.Fatalf("read design-v015.css: %v", err)
	}
	s := string(css)
	for _, m := range []string{".incident-detail td", "border-left: 3px solid #f59e0b", ".table thead th", "text-transform: none", ".stat-card .stat-value", "值班日志本"} {
		if !strings.Contains(s, m) {
			t.Errorf("missing design marker: %s", m)
		}
	}
	for _, banned := range []string{"gradient", "Inter", "${"} {
		if strings.Contains(s, banned) {
			t.Errorf("banned pattern in design layer: %s", banned)
		}
	}
	pages := []string{"index.html", "incidents.html", "profile.html", "sms_log.html", "snapshots.html", "status.html"}
	for _, p := range []string{"incidents.html", "sms_log.html"} {
		data, err := fs.ReadFile(FS, "static/"+p)
		if err != nil {
			t.Fatalf("read %s: %v", p, err)
		}
		if !strings.Contains(string(data), `<nav class="nav">`) {
			t.Errorf("%s: nav must carry class nav for the shared topbar rules", p)
		}
	}
	for _, p := range pages {
		data, err := fs.ReadFile(FS, "static/"+p)
		if err != nil {
			t.Fatalf("read %s: %v", p, err)
		}
		h := string(data)
		base := strings.Index(h, "/static/style.css")
		layer := strings.Index(h, "/static/design-v015.css")
		if base < 0 || layer < 0 || layer < base {
			t.Errorf("%s: design layer must be referenced after style.css", p)
		}
	}
}
