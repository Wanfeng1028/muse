package metrics

import (
	"strings"
	"testing"
)

func TestIncLinksPurged(t *testing.T) {
	reg := NewRegistry()
	reg.IncLinksPurged(3)

	out := scrape(t, reg)
	if !strings.Contains(out, "linkshort_links_purged_total 3") {
		t.Fatalf("metrics output missing linkshort_links_purged_total 3:\n%s", out)
	}
}
