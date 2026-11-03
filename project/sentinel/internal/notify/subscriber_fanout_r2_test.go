package notify

import (
	"strings"
	"testing"

	"sentinel/internal/store"
)

type r2FakeSource struct {
	pages map[int64][]store.Subscriber
}

func (f *r2FakeSource) ListPageIDsForMonitor(monitorID int64) ([]int64, error) {
	return []int64{7, 8}, nil
}

func (f *r2FakeSource) ListConfirmedSubscribers(pageID int64) ([]store.Subscriber, error) {
	return f.pages[pageID], nil
}

func newR2FakeSource() *r2FakeSource {
	return &r2FakeSource{
		pages: map[int64][]store.Subscriber{
			7: {
				{Email: "a@x.com", Token: "t1", PageTitle: "页七", PageSlug: "p7"},
			},
			8: {
				{Email: "A@X.com", Token: "t2", PageTitle: "页八", PageSlug: "p8"},
				{Email: "b@x.com", Token: "t3", PageTitle: "页八", PageSlug: "p8"},
			},
		},
	}
}

func TestR2_NotifySubscribersDedup(t *testing.T) {
	src := newR2FakeSource()
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "", 99, "down", "api", "http://t/", "now", "boom")
	if err != nil {
		t.Fatalf("NotifySubscribers returned error: %v", err)
	}

	msgs := mailer.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 sent messages, got %d", len(msgs))
	}

	first := msgs[0]
	if len(first.Recipients) != 1 || first.Recipients[0] != "a@x.com" {
		t.Fatalf("unexpected first recipients: %#v", first.Recipients)
	}
	if !strings.Contains(first.Subject, "宕机") {
		t.Fatalf("first subject does not contain down text: %q", first.Subject)
	}
	if !strings.Contains(first.Body, "页七") {
		t.Fatalf("first body does not contain first page title: %q", first.Body)
	}
	if !strings.Contains(first.Body, "/api/status/p7/unsubscribe?token=t1") {
		t.Fatalf("first body does not contain relative unsubscribe link: %q", first.Body)
	}
	if strings.Contains(first.Body, "/api/status/p8/unsubscribe?token=t2") {
		t.Fatalf("first body unexpectedly contains second page link: %q", first.Body)
	}

	second := msgs[1]
	if len(second.Recipients) != 1 || second.Recipients[0] != "b@x.com" {
		t.Fatalf("unexpected second recipients: %#v", second.Recipients)
	}
}

func TestR2_NotifySubscribersBaseURL(t *testing.T) {
	src := newR2FakeSource()
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 99, "down", "api", "http://t/", "now", "boom")
	if err != nil {
		t.Fatalf("NotifySubscribers returned error: %v", err)
	}

	msgs := mailer.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 sent messages, got %d", len(msgs))
	}

	want := "https://status.example.com/api/status/p7/unsubscribe?token=t1"
	if !strings.Contains(msgs[0].Body, want) {
		t.Fatalf("first body does not contain absolute unsubscribe link %q: %q", want, msgs[0].Body)
	}
}

func TestR2_NotifySubscribersRecovered(t *testing.T) {
	src := newR2FakeSource()
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "", 99, "recovered", "api", "http://t/", "now", "ignored-error")
	if err != nil {
		t.Fatalf("NotifySubscribers returned error: %v", err)
	}

	msgs := mailer.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 sent messages, got %d", len(msgs))
	}

	first := msgs[0]
	if !strings.Contains(first.Subject, "已恢复") {
		t.Fatalf("first subject does not contain recovered text: %q", first.Subject)
	}
	if !strings.Contains(first.Body, "事件: 已恢复") {
		t.Fatalf("first body does not contain recovered event: %q", first.Body)
	}
	if strings.Contains(first.Body, "错误信息") {
		t.Fatalf("recovered body unexpectedly contains error info: %q", first.Body)
	}
}
