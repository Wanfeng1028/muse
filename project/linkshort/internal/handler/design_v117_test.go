package handler

import (
	"os"
	"strings"
	"testing"
)

func v117Read(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(b)
}

func TestV117DesignLayer(t *testing.T) {
	css := v117Read(t, "web/assets/css/design-v117.css")
	for _, want := range []string{".topbar-title", ".panel-head h2", ".table thead th", ".sidebar nav a.active", ".btn.primary:focus-visible"} {
		if !strings.Contains(css, want) {
			t.Fatalf("design layer missing %s", want)
		}
	}
	for _, banned := range []string{"linear-gradient", "font-weight: 700", "text-transform: uppercase"} {
		if strings.Contains(css, banned) {
			t.Fatalf("design layer must not contain %q", banned)
		}
	}
	if strings.Contains(css, "Inter") {
		t.Fatalf("design layer must not name Inter as UI font")
	}
	for _, page := range []string{"web/bulk.html", "web/index.html", "web/links.html", "web/new.html", "web/geo.html", "web/detail.html"} {
		html := v117Read(t, page)
		if !strings.Contains(html, "assets/css/design-v117.css") {
			t.Fatalf("%s must link design-v117.css after style.css", page)
		}
		base := strings.Index(html, "assets/css/style.css")
		layer := strings.Index(html, "assets/css/design-v117.css")
		if base < 0 || layer < 0 || layer < base {
			t.Fatalf("%s: design layer must load after style.css", page)
		}
	}
}

func TestV117BulkSharedPassword(t *testing.T) {
	html := v117Read(t, "web/bulk.html")
	if !strings.Contains(html, `id="bulk-password"`) {
		t.Fatalf("bulk page must have a shared password input")
	}
	if !strings.Contains(html, `<th>密码</th>`) {
		t.Fatalf("bulk result table must have a password column")
	}
	js := v117Read(t, "web/assets/js/bulk.js")
	if !strings.Contains(js, "item.password = sharedPassword") {
		t.Fatalf("bulk.js must send the shared password per item")
	}
	if !strings.Contains(js, `"已设"`) {
		t.Fatalf("bulk.js must render a set marker, never the password itself")
	}
	if strings.Contains(js, "textContent = sharedPassword") || strings.Contains(js, "innerHTML = sharedPassword") {
		t.Fatalf("bulk.js must never echo the password into the DOM")
	}
}
