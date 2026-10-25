package handler

import (
	"os"
	"strings"
	"testing"
)

// v1.17.1: docs page joins the v1.17.0 design layer. The docs page carries its
// own inline style block, so the design link must sit after that block,
// otherwise the inline rules win and the layer has no effect.
func TestDocsPageDesignLayer(t *testing.T) {
	html, err := os.ReadFile("web/docs.html")
	if err != nil {
		t.Fatalf("read web/docs.html: %v", err)
	}
	css, err := os.ReadFile("web/assets/css/design-v117.css")
	if err != nil {
		t.Fatalf("read design layer: %v", err)
	}
	for _, want := range []string{"h1.docs-title", "h2.docs-h2", ".docs-wrap .table th"} {
		if !strings.Contains(string(css), want) {
			t.Fatalf("design layer missing %s", want)
		}
	}
	link := strings.Index(string(html), "/ui/assets/css/design-v117.css")
	styleEnd := strings.Index(string(html), "</style>")
	if link < 0 {
		t.Fatalf("docs.html must link design-v117.css")
	}
	if styleEnd < 0 || link < styleEnd {
		t.Fatalf("docs.html: design link must come after the inline style block")
	}
	styleLink := strings.Index(string(html), "/ui/assets/css/style.css")
	if styleLink < 0 || link < styleLink {
		t.Fatalf("docs.html: design layer must load after style.css")
	}
}
