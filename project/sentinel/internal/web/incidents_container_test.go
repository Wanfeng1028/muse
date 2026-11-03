package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestIncidentsContainer closes the v0.15.0 known limitation that the
// incidents page had no .container/.page wrapper: its content sat against
// the viewport edge and the filter bar stretched full width. The page now
// wraps its body in <main class="container">, the same wrapper index.html
// and snapshots.html already use; the topbar stays outside it and no JS
// changes. Marker lines are model output (GLM-5.3 via BotsRouter), adapted
// to this package's t.Errorf style.
func TestIncidentsContainer(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	h := string(data)
	for _, m := range []string{
		`<main class="container">`,
		`<table class="table">`,
		`id="monitor-filter"`,
	} {
		if !strings.Contains(h, m) {
			t.Errorf("incidents.html: missing marker: %s", m)
		}
	}
	mainOpen := strings.Index(h, `<main class="container">`)
	mainClose := strings.Index(h, `</main>`)
	table := strings.Index(h, `<table class="table">`)
	if !(mainOpen > 0 && table > mainOpen && mainClose > table) {
		t.Errorf("incidents.html: table not inside main container (open=%d table=%d close=%d)", mainOpen, table, mainClose)
	}
	script := strings.Index(h, `<script>`)
	if !(mainClose > 0 && mainClose < script) {
		t.Errorf("incidents.html: main container not closed before script (close=%d script=%d)", mainClose, script)
	}
	topbar := strings.Index(h, `<div class="topbar">`)
	if !(topbar > 0 && mainOpen > topbar) {
		t.Errorf("incidents.html: main container must start after topbar (topbar=%d open=%d)", topbar, mainOpen)
	}
}
