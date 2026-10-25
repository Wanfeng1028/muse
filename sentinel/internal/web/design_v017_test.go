package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestDesignV017_Layer asserts v0.17.0 design layer markers: the layer file
// exists, unifies the monitors/deliveries nav active state, removes the
// topbar/filter-bar shadows, carries no banned patterns, and is referenced
// after design-v016.css on both pages. The deliveries active link must use
// class="active" instead of the old inline style, so the stylesheet can
// actually reach it. Static markers only; browser rendering is covered by
// the real-service screenshot check.
func TestDesignV017_Layer(t *testing.T) {
	css, err := fs.ReadFile(FS, "static/design-v017.css")
	if err != nil {
		t.Fatalf("read design-v017.css: %v", err)
	}
	s := string(css)
	for _, m := range []string{
		".nav-links a.active",
		".nav-links .active::after",
		".topbar-right a.active",
		".topbar",
		".filter-bar",
		"#1f2937",
		"#10b981",
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
		v016 := strings.Index(h, "/static/design-v016.css")
		v017 := strings.Index(h, "/static/design-v017.css")
		if v016 < 0 || v017 < 0 || v017 < v016 {
			t.Errorf("%s: design-v017.css must be referenced after design-v016.css", p)
		}
	}
	del, err := fs.ReadFile(FS, "static/deliveries.html")
	if err != nil {
		t.Fatalf("read deliveries.html: %v", err)
	}
	d := string(del)
	if !strings.Contains(d, `<a href="/deliveries" class="active">`) {
		t.Errorf("deliveries.html: active link must use class=\"active\"")
	}
	if strings.Contains(d, `style="background:#eaeef2; color:#0969da;"`) {
		t.Errorf("deliveries.html: active link must not keep the old inline style")
	}
	mon, err := fs.ReadFile(FS, "static/monitors.html")
	if err != nil {
		t.Fatalf("read monitors.html: %v", err)
	}
	if !strings.Contains(string(mon), `class="active">监控管理</a>`) {
		t.Errorf("monitors.html: missing active nav anchor")
	}
}
