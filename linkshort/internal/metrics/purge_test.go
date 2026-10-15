package metrics

import (
	"strings"
	"testing"
)

func TestIncBurnPurged(t *testing.T) {
	reg := NewRegistry()
	reg.IncBurnPurged()
	out := scrape(t, reg)
	if !strings.Contains(out, "linkshort_burn_links_purged_total 1") {
		t.Fatalf("期望包含 linkshort_burn_links_purged_total 1, 实际:\n%s", out)
	}
}
