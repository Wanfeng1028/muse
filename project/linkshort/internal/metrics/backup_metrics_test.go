package metrics

import (
	"strings"
	"testing"
)

func TestBackupMetrics_Healthy(t *testing.T) {
	reg := NewRegistry()
	reg.SetBackupHealth(true, 1729000000)

	out := scrape(t, reg)
	if !strings.Contains(out, "linkshort_backup_last_success_timestamp 1729000000") {
		t.Fatalf("metrics output missing linkshort_backup_last_success_timestamp 1729000000:\n%s", out)
	}
	if !strings.Contains(out, "linkshort_backup_health_status 1") {
		t.Fatalf("metrics output missing linkshort_backup_health_status 1:\n%s", out)
	}
}

func TestBackupMetrics_Degraded(t *testing.T) {
	reg := NewRegistry()
	reg.SetBackupHealth(false, 0)

	out := scrape(t, reg)
	if !strings.Contains(out, "linkshort_backup_health_status 0") {
		t.Fatalf("metrics output missing linkshort_backup_health_status 0:\n%s", out)
	}
	if !strings.Contains(out, "linkshort_backup_last_success_timestamp 0") {
		t.Fatalf("metrics output missing linkshort_backup_last_success_timestamp 0:\n%s", out)
	}
}
