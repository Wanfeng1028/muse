package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestDesignV018_TopbarUnified asserts the v0.18.0 topbar structure
// unification: monitors.html and deliveries.html share the same three-slot
// header (logo-area / nav-links / user-area). The deliveries page must no
// longer carry its old topbar-left / topbar-right / badge header, and its
// nav must keep its own links with the deliveries link active. Static
// markers only; browser rendering is covered by the real-service
// screenshot check.
func TestDesignV018_TopbarUnified(t *testing.T) {
	for _, p := range []string{"monitors.html", "deliveries.html"} {
		data, err := fs.ReadFile(FS, "static/"+p)
		if err != nil {
			t.Fatalf("read %s: %v", p, err)
		}
		h := string(data)
		for _, m := range []string{
			`<header class="topbar">`,
			`<div class="logo-area">`,
			`<span class="logo-icon">S</span>`,
			`<nav class="nav-links">`,
			`<div class="user-area">`,
		} {
			if !strings.Contains(h, m) {
				t.Errorf("%s: missing unified topbar marker: %s", p, m)
			}
		}
		// The three slots must appear in header order: logo, nav, user.
		logo := strings.Index(h, `<div class="logo-area">`)
		nav := strings.Index(h, `<nav class="nav-links">`)
		user := strings.Index(h, `<div class="user-area">`)
		if !(logo > 0 && nav > logo && user > nav) {
			t.Errorf("%s: topbar slots out of order (logo=%d nav=%d user=%d)", p, logo, nav, user)
		}
	}
	del, err := fs.ReadFile(FS, "static/deliveries.html")
	if err != nil {
		t.Fatalf("read deliveries.html: %v", err)
	}
	d := string(del)
	for _, old := range []string{
		`class="topbar-left"`,
		`class="topbar-right"`,
		`<span class="badge">监控</span>`,
		"\n.badge {",
	} {
		if strings.Contains(d, old) {
			t.Errorf("deliveries.html: old topbar remnant still present: %q", old)
		}
	}
	// Deliveries keeps its own nav targets; only the structure is unified.
	for _, link := range []string{
		`<a href="/">仪表盘</a>`,
		`<a href="/incidents">事件</a>`,
		`<a href="/deliveries" class="active">投递队列</a>`,
		`<a href="/settings">设置</a>`,
	} {
		if !strings.Contains(d, link) {
			t.Errorf("deliveries.html: missing own nav link: %s", link)
		}
	}
	// The unified inline topbar CSS must be present on deliveries.
	for _, rule := range []string{
		".topbar {",
		"height: 64px;",
		".logo-area {",
		".nav-links {",
		".user-area {",
		".avatar {",
	} {
		if !strings.Contains(d, rule) {
			t.Errorf("deliveries.html: missing unified topbar CSS: %s", rule)
		}
	}
}
