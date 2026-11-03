// internal/push/scheduler_test.go
package push

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestNextPushTimeSameDay(t *testing.T) {
	loc := time.UTC
	now := time.Date(2025, 1, 2, 6, 0, 0, 0, loc)
	got, err := NextPushTime(now, "08:30", loc)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	want := time.Date(2025, 1, 2, 8, 30, 0, 0, loc)
	if !got.Equal(want) {
		t.Fatalf("got %v want %v", got, want)
	}
}

func TestNextPushTimeNextDay(t *testing.T) {
	loc := time.UTC
	now := time.Date(2025, 1, 2, 9, 0, 0, 0, loc)
	got, err := NextPushTime(now, "08:30", loc)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	want := time.Date(2025, 1, 3, 8, 30, 0, 0, loc)
	if !got.Equal(want) {
		t.Fatalf("got %v want %v", got, want)
	}
}

func TestNextPushTimeInvalid(t *testing.T) {
	loc := time.UTC
	now := time.Date(2025, 1, 2, 6, 0, 0, 0, loc)
	cases := []string{"", "8", "abc:30", "25:00", "08:99", "08:xx"}
	for _, c := range cases {
		if _, err := NextPushTime(now, c, loc); err == nil {
			t.Fatalf("expected error for %q", c)
		}
	}
}

func TestNextPushTimeTimezone(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Skipf("tzdata 不可用: %v", err)
	}
	// UTC 01:00 对应上海 09:00，已过 08:30，应返回次日
	now := time.Date(2025, 1, 2, 1, 0, 0, 0, time.UTC)
	got, err := NextPushTime(now, "08:30", loc)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	want := time.Date(2025, 1, 3, 8, 30, 0, 0, loc)
	if !got.Equal(want) {
		t.Fatalf("got %v want %v", got, want)
	}
}

type fakeSender struct {
	name  string
	calls int32
	err   error
}

func (f *fakeSender) Name() string { return f.name }

func (f *fakeSender) Send(ctx context.Context, msg notify.Message) error {
	atomic.AddInt32(&f.calls, 1)
	return f.err
}

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	return st
}

func TestRunPushIdempotent(t *testing.T) {
	st := newTestStore(t)
	sender := &fakeSender{name: "webhook"}
	senders := SenderSet{Webhook: sender}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}
	now := time.Date(2025, 1, 2, 10, 0, 0, 0, time.UTC)

	first := RunPush(context.Background(), st, senders, pc, now)
	if len(first) != 1 || first[0].Status != "sent" {
		t.Fatalf("first run: %+v", first)
	}
	if atomic.LoadInt32(&sender.calls) != 1 {
		t.Fatalf("expected 1 call, got %d", sender.calls)
	}

	second := RunPush(context.Background(), st, senders, pc, now)
	if len(second) != 1 || second[0].Status != "skipped" {
		t.Fatalf("second run: %+v", second)
	}
	if atomic.LoadInt32(&sender.calls) != 1 {
		t.Fatalf("expected still 1 call, got %d", sender.calls)
	}
}

func TestRunPushOneChannelFailureDoesNotAffectOther(t *testing.T) {
	st := newTestStore(t)

	var got int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&got, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	good := notify.NewWebhookSender(srv.URL, "", 5*time.Second)
	bad := &fakeSender{name: "smtp", err: errors.New("boom")}

	senders := SenderSet{SMTP: bad, Webhook: good}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}
	now := time.Date(2025, 1, 2, 10, 0, 0, 0, time.UTC)

	results := RunPush(context.Background(), st, senders, pc, now)
	var smtpStatus, whStatus string
	for _, r := range results {
		switch r.Channel {
		case "smtp":
			smtpStatus = r.Status
		case "webhook":
			whStatus = r.Status
		}
	}
	if smtpStatus != "failed" {
		t.Fatalf("smtp status = %q", smtpStatus)
	}
	if whStatus != "sent" {
		t.Fatalf("webhook status = %q", whStatus)
	}
	if atomic.LoadInt32(&got) != 1 {
		t.Fatalf("webhook receiver calls = %d", got)
	}
}
