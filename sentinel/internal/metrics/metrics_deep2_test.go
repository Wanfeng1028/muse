package metrics

import (
	"strings"
	"sync"
	"testing"
)

func TestNormalizePathEmptyDeep2(t *testing.T) {
	if got := normalizePath(""); got != "/" {
		t.Fatalf("normalizePath(\"\") = %q, want %q", got, "/")
	}
}

func TestNormalizePathMissingLeadingSlashDeep2(t *testing.T) {
	if got := normalizePath("api/monitors"); got != "/api/monitors" {
		t.Fatalf("normalizePath(\"api/monitors\") = %q, want %q", got, "/api/monitors")
	}
}

func TestNormalizePathNumericSegmentDeep2(t *testing.T) {
	if got := normalizePath("/api/monitors/123"); got != "/api/monitors/:id" {
		t.Fatalf("normalizePath(\"/api/monitors/123\") = %q, want %q", got, "/api/monitors/:id")
	}
}

func TestNormalizePathNonNumericSegmentDeep2(t *testing.T) {
	if got := normalizePath("/api/monitors/abc"); got != "/api/monitors/abc" {
		t.Fatalf("normalizePath(\"/api/monitors/abc\") = %q, want %q", got, "/api/monitors/abc")
	}
}

func TestNormalizePathStripsQueryDeep2(t *testing.T) {
	if got := normalizePath("/api/monitors/123?foo=bar"); got != "/api/monitors/:id" {
		t.Fatalf("normalizePath(\"/api/monitors/123?foo=bar\") = %q, want %q", got, "/api/monitors/:id")
	}
}

func TestNormalizePathDoubleSlashDeep2(t *testing.T) {
	got := normalizePath("/api//monitors")
	if strings.Contains(got, "?") {
		t.Fatalf("normalizePath result %q must not contain query", got)
	}
	if !strings.HasPrefix(got, "/") {
		t.Fatalf("normalizePath result %q must start with /", got)
	}
	if got != "/api//monitors" && got != "/api/monitors" {
		t.Fatalf("normalizePath(\"/api//monitors\") = %q, want either %q or %q", got, "/api//monitors", "/api/monitors")
	}
}

func TestRecordHTTPNormalizesNumericIDDeep2(t *testing.T) {
	r := New()
	r.RecordHTTP("GET", "/api/monitors/123", 200, 10)
	r.RecordHTTP("GET", "/api/monitors/456", 200, 20)
	r.RecordHTTP("GET", "/api/monitors/:id", 200, 30)

	snap := r.Snapshot()
	found := false
	if httpMap, ok := snap["http_requests"].(map[string]int64); ok {
		for k, n := range httpMap {
			if strings.Contains(k, "api/monitors/:id") {
				found = true
				if n != 3 {
					t.Fatalf("counter %q = %d, want 3", k, n)
				}
			}
		}
	} else {
		t.Fatalf("http_requests 不是 map[string]int64，实际 %T", snap["http_requests"])
	}
	if !found {
		t.Fatalf("expected an http counter key containing \"api/monitors/:id\", snapshot=%v", snap)
	}
}

func TestSnapshotCountersAfterRecordsDeep2(t *testing.T) {
	r := New()
	r.RecordCheck(true, 5, false)
	r.RecordCheck(false, 7, true)
	r.RecordWebhook(true)
	r.RecordWebhook(false)
	r.RecordEnqueueRejected()

	snap := r.Snapshot()

	checksTotal := toInt64(t, snap["checks_total"])
	if checksTotal != 2 {
		t.Fatalf("checks_total = %d, want 2", checksTotal)
	}
	checkFailures := toInt64(t, snap["check_failures"])
	if checkFailures != 1 {
		t.Fatalf("check_failures = %d, want 1", checkFailures)
	}
	checkRetries := toInt64(t, snap["check_retries"])
	if checkRetries != 1 {
		t.Fatalf("check_retries = %d, want 1", checkRetries)
	}
	webhooksSent := toInt64(t, snap["webhooks_sent"])
	if webhooksSent != 2 {
		t.Fatalf("webhooks_sent = %d, want 2", webhooksSent)
	}
	webhookFailures := toInt64(t, snap["webhook_failures"])
	if webhookFailures != 1 {
		t.Fatalf("webhook_failures = %d, want 1", webhookFailures)
	}
}

func toInt64(t *testing.T, v interface{}) int64 {
	t.Helper()
	switch n := v.(type) {
	case int64:
		return n
	case int:
		return int64(n)
	case uint64:
		return int64(n)
	case float64:
		return int64(n)
	default:
		t.Fatalf("unexpected counter type %T", v)
		return 0
	}
}

func TestRecordHTTPConcurrentDeep2(t *testing.T) {
	r := New()
	const goroutines = 50
	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			r.RecordHTTP("POST", "/api/monitors/1", 201, 3)
		}()
	}
	wg.Wait()

	snap := r.Snapshot()
	total := int64(0)
	if httpMap, ok := snap["http_requests"].(map[string]int64); ok {
		for k, v := range httpMap {
			if strings.Contains(k, "api/monitors/:id") {
				total += v
			}
		}
	} else {
		t.Fatalf("http_requests 不是 map[string]int64，实际 %T", snap["http_requests"])
	}
	if total != goroutines {
		t.Fatalf("total http counter for normalized path = %d, want %d (snapshot=%v)", total, goroutines, snap)
	}
}

func TestRenderQueueBacklogLargeValuesDeep2(t *testing.T) {
	out := RenderQueueBacklog(1234567890123, 9876543210987)
	if !strings.Contains(out, "# HELP sentinel_webhook_queue_backlog") {
		t.Fatalf("output missing HELP line: %q", out)
	}
	if !strings.Contains(out, "# TYPE sentinel_webhook_queue_backlog gauge") {
		t.Fatalf("output missing TYPE line: %q", out)
	}
	if !strings.Contains(out, `sentinel_webhook_queue_backlog{status="pending"} 1234567890123`) {
		t.Fatalf("output missing pending line: %q", out)
	}
	if !strings.Contains(out, `sentinel_webhook_queue_backlog{status="retrying"} 9876543210987`) {
		t.Fatalf("output missing retrying line: %q", out)
	}
}

func TestRenderPrometheusNonEmptyDeep2(t *testing.T) {
	r := New()
	r.RecordCheck(true, 1, false)
	out := r.RenderPrometheus()
	if strings.TrimSpace(out) == "" {
		t.Fatal("RenderPrometheus returned empty output")
	}
	if !strings.Contains(out, "sentinel_") {
		t.Fatalf("RenderPrometheus output missing sentinel_ prefix: %q", out)
	}
}

func TestRenderBreakerStatesContainsKeysDeep2(t *testing.T) {
	states := map[string]int{
		"webhook_sender": 2,
		"api_upstream":   0,
	}
	out := RenderBreakerStates(states)
	for k := range states {
		if !strings.Contains(out, k) {
			t.Fatalf("RenderBreakerStates output %q missing key %q", out, k)
		}
	}
}
