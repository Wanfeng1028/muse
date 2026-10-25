package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestSmsLogContainer closes the remainder of the v0.15.0 known limitation
// left by v0.19.0: the sms-log page still had no .container/.page wrapper,
// so its filter bar and table stretched full width. The profile page is
// not touched here: it already has its own .wrap container. Marker lines
// are model output (GLM-5.3 via BotsRouter), adapted to this package's
// t.Errorf style; the HTML wrap itself is a mechanical insertion.
func TestSmsLogContainer(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/sms_log.html")
	if err != nil {
		t.Fatalf("read sms_log.html: %v", err)
	}
	h := string(data)
	for _, m := range []string{
		`<main class="container">`,
		`<table class="data-table">`,
		`id="filter-phone"`,
	} {
		if !strings.Contains(h, m) {
			t.Errorf("sms_log.html: missing marker: %s", m)
		}
	}
	mainOpen := strings.Index(h, `<main class="container">`)
	mainClose := strings.Index(h, `</main>`)
	table := strings.Index(h, `<table class="data-table">`)
	filter := strings.Index(h, `id="filter-phone"`)
	if !(mainOpen > 0 && table > mainOpen && filter > mainOpen && mainClose > table && mainClose > filter) {
		t.Errorf("sms_log.html: table/filter not inside main container (open=%d table=%d filter=%d close=%d)", mainOpen, table, filter, mainClose)
	}
	script := strings.Index(h, `<script>`)
	if !(mainClose > 0 && mainClose < script) {
		t.Errorf("sms_log.html: main container not closed before script (close=%d script=%d)", mainClose, script)
	}
	topbar := strings.Index(h, `<div class="topbar">`)
	if !(topbar > 0 && mainOpen > topbar) {
		t.Errorf("sms_log.html: main container must start after topbar (topbar=%d open=%d)", topbar, mainOpen)
	}
}
