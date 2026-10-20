package push

import (
	"context"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestRunPushForUser_BatchDueSingleDigestDedup(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()

	reviewAt := time.Date(2026, 10, 15, 0, 0, 0, 0, time.UTC)
	for _, title := range []string{"N1", "N2", "N3"} {
		n, err := st.CreateNoteFor(ctx, store.Note{Title: title, Body: "body"}, "local")
		if err != nil {
			t.Fatalf("CreateNoteFor(%q): expected no error, got %v", title, err)
		}
		if _, err := st.RecordReview(ctx, n.ID, 5, reviewAt, "local"); err != nil {
			t.Fatalf("RecordReview(%q): expected no error, got %v", title, err)
		}
	}

	sender := &fakeSender{name: "webhook"}
	senders := SenderSet{Webhook: sender}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}
	now := time.Date(2026, 10, 20, 10, 0, 0, 0, time.UTC)

	res := RunPushForUser(ctx, st, senders, pc, now, "local")
	if len(res) != 1 {
		t.Fatalf("first run: expected len(res)==1, got %d (%+v)", len(res), res)
	}
	if res[0].Status != "sent" {
		t.Fatalf("first run: expected status %q, got %q (detail=%q)", "sent", res[0].Status, res[0].Detail)
	}
	if got := atomic.LoadInt32(&sender.calls); got != 1 {
		t.Fatalf("first run: expected sender.calls==1 (3 due notes aggregated into 1 digest), got %d", got)
	}

	res2 := RunPushForUser(ctx, st, senders, pc, now, "local")
	if len(res2) != 1 {
		t.Fatalf("second run: expected len(res2)==1, got %d (%+v)", len(res2), res2)
	}
	if res2[0].Status != "skipped" {
		t.Fatalf("second run: expected status %q (same-day dedup), got %q (detail=%q)", "skipped", res2[0].Status, res2[0].Detail)
	}
	if got := atomic.LoadInt32(&sender.calls); got != 1 {
		t.Fatalf("second run: expected sender.calls still==1 (dedup suppressed send), got %d", got)
	}
}