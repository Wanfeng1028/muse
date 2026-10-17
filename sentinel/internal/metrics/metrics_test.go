package metrics

import (
	"strings"
	"testing"
)

func TestRenderQueueBacklog(t *testing.T) {
	got := RenderQueueBacklog(3, 7)
	want := "# HELP sentinel_webhook_queue_backlog Number of webhook deliveries waiting in the queue, by status.\n" +
		"# TYPE sentinel_webhook_queue_backlog gauge\n" +
		"sentinel_webhook_queue_backlog{status=\"pending\"} 3\n" +
		"sentinel_webhook_queue_backlog{status=\"retrying\"} 7\n"
	if got != want {
		t.Fatalf("RenderQueueBacklog(3, 7) mismatch:\n got=%q\nwant=%q", got, want)
	}
}

func TestRenderQueueBacklog_Zero(t *testing.T) {
	got := RenderQueueBacklog(0, 0)
	want := "# HELP sentinel_webhook_queue_backlog Number of webhook deliveries waiting in the queue, by status.\n" +
		"# TYPE sentinel_webhook_queue_backlog gauge\n" +
		"sentinel_webhook_queue_backlog{status=\"pending\"} 0\n" +
		"sentinel_webhook_queue_backlog{status=\"retrying\"} 0\n"
	if got != want {
		t.Fatalf("RenderQueueBacklog(0, 0) mismatch:\n got=%q\nwant=%q", got, want)
	}
	if !strings.Contains(got, "sentinel_webhook_queue_backlog{status=\"pending\"} 0") {
		t.Fatalf("expected pending gauge line to be zero, got %q", got)
	}
	if !strings.Contains(got, "sentinel_webhook_queue_backlog{status=\"retrying\"} 0") {
		t.Fatalf("expected retrying gauge line to be zero, got %q", got)
	}
}
