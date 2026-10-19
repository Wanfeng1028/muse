package push

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// TestSendWebPushDigest_EmptyDue 无到期复习时仍推送空 digest（P2-5 回归）。
func TestSendWebPushDigest_EmptyDue(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "1")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")
	installInsecureTransport(t)

	mux := http.NewServeMux()
	mux.HandleFunc("/ok", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	})
	srv := httptest.NewTLSServer(mux)
	t.Cleanup(srv.Close)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	t.Cleanup(func() { st.Close() })
	newSubscription(t, st, "local", srv.URL+"/ok")

	wp := newTestWebPushSender(t)

	res := sendWebPushDigest(context.Background(), st, wp, "2026-10-23", "local", 0)
	if res.Status != "sent" {
		t.Fatalf("空 digest 期望 Status=sent，得到 %q（detail=%q）", res.Status, res.Detail)
	}

	logStatus, ok := st.PushLogStatus("2026-10-23", "webpush", "local")
	if !ok {
		t.Fatalf("PushLogStatus 未找到 webpush 记录")
	}
	if logStatus != "sent" {
		t.Fatalf("PushLogStatus 期望 sent，得到 %q", logStatus)
	}

	subs, err := st.ListSubscriptionsForUser("local")
	if err != nil {
		t.Fatalf("ListSubscriptionsForUser 失败：%v", err)
	}
	if len(subs) != 1 {
		t.Fatalf("订阅数期望 1，得到 %d", len(subs))
	}
}
