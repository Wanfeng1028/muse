package push

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// newTestWebPushSender 用自生成的 VAPID 密钥构造 WebPushSender。
func newTestWebPushSender(t *testing.T) *notify.WebPushSender {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("生成 VAPID 密钥失败: %v", err)
	}
	pub := base64.RawURLEncoding.EncodeToString(
		elliptic.Marshal(elliptic.P256(), key.X, key.Y))
	privBytes := key.D.Bytes()
	if len(privBytes) < 32 {
		pad := make([]byte, 32-len(privBytes))
		privBytes = append(pad, privBytes...)
	}
	priv := base64.RawURLEncoding.EncodeToString(privBytes)
	wp, err := notify.NewWebPushSender(pub, priv, "mailto:test@example.com", 5*time.Second)
	if err != nil {
		t.Fatalf("构造 WebPushSender 失败: %v", err)
	}
	return wp
}

// genSubscriptionKeys 生成一对合法的 p256dh/auth 订阅密钥。
func genSubscriptionKeys(t *testing.T) (string, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("生成订阅密钥失败: %v", err)
	}
	p256dh := base64.RawURLEncoding.EncodeToString(
		elliptic.Marshal(elliptic.P256(), key.X, key.Y))
	authRaw := make([]byte, 16)
	if _, err := rand.Read(authRaw); err != nil {
		t.Fatalf("生成 auth 失败: %v", err)
	}
	auth := base64.RawURLEncoding.EncodeToString(authRaw)
	return p256dh, auth
}

// installInsecureTransport 把 http.DefaultTransport 换成跳过证书校验的版本。
// 返回恢复函数。若 webpush.go 自建 client 则该替换无效，测试会失败。
func installInsecureTransport(t *testing.T) {
	t.Helper()
	orig := http.DefaultTransport
	http.DefaultTransport = &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	t.Cleanup(func() { http.DefaultTransport = orig })
}

// newSubscription 构造一条订阅并写入 store。
func newSubscription(t *testing.T, st *store.Store, user, endpoint string) {
	t.Helper()
	p256dh, auth := genSubscriptionKeys(t)
	if _, err := st.UpsertSubscription(user, endpoint, p256dh, auth); err != nil {
		t.Fatalf("写入订阅 %s 失败: %v", endpoint, err)
	}
}

// newPartialFailureServer 返回三种行为的 TLS server：/gone→410、/flaky→500、/ok→201。
func newPartialFailureServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/gone", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusGone)
	})
	mux.HandleFunc("/gone2", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusGone)
	})
	mux.HandleFunc("/flaky", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	mux.HandleFunc("/ok", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	})
	srv := httptest.NewTLSServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// TestSendWebPushDigest_PartialFailure 覆盖：一条成功、一条 410、一条 500 重试耗尽。
func TestSendWebPushDigest_PartialFailure(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "1")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")
	installInsecureTransport(t)

	srv := newPartialFailureServer(t)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	defer st.Close()

	user := "local"
	goneURL := srv.URL + "/gone"
	flakyURL := srv.URL + "/flaky"
	okURL := srv.URL + "/ok"
	newSubscription(t, st, user, goneURL)
	newSubscription(t, st, user, flakyURL)
	newSubscription(t, st, user, okURL)

	wp := newTestWebPushSender(t)
	result := sendWebPushDigest(context.Background(), st, wp,
		"2026-10-20", user, 3)

	if result.Status != "sent" {
		t.Fatalf("Status = %q, want %q (Detail=%q)", result.Status, "sent", result.Detail)
	}
	if result.Detail != "成功 1 条，清理失效订阅 1 条" {
		t.Fatalf("Detail = %q, want %q", result.Detail, "成功 1 条，清理失效订阅 1 条")
	}

	subs, err := st.ListSubscriptionsForUser(user)
	if err != nil {
		t.Fatalf("ListSubscriptionsForUser 失败: %v", err)
	}
	if len(subs) != 2 {
		t.Fatalf("剩余订阅数 = %d, want 2", len(subs))
	}
	for _, s := range subs {
		if s.Endpoint == goneURL {
			t.Fatalf("/gone 订阅未被清理")
		}
	}

	status, ok := st.PushLogStatus("2026-10-20", "webpush", user)
	if !ok {
		t.Fatalf("PushLogStatus 未命中记录")
	}
	if status != "sent" {
		t.Fatalf("PushLogStatus = %q, want %q", status, "sent")
	}
}

// TestSendWebPushDigest_AllGone 覆盖：所有订阅 410，全部清理。
func TestSendWebPushDigest_AllGone(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "1")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")
	installInsecureTransport(t)

	srv := newPartialFailureServer(t)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	defer st.Close()

	user := "local"
	newSubscription(t, st, user, srv.URL+"/gone")
	newSubscription(t, st, user, srv.URL+"/gone2")

	wp := newTestWebPushSender(t)
	result := sendWebPushDigest(context.Background(), st, wp,
		"2026-10-21", user, 3)

	if result.Status != "failed" {
		t.Fatalf("Status = %q, want %q (Detail=%q)", result.Status, "failed", result.Detail)
	}
	if result.Detail != "全部订阅已失效，清理 2 条" {
		t.Fatalf("Detail = %q, want %q", result.Detail, "全部订阅已失效，清理 2 条")
	}

	subs, err := st.ListSubscriptionsForUser(user)
	if err != nil {
		t.Fatalf("ListSubscriptionsForUser 失败: %v", err)
	}
	if len(subs) != 0 {
		t.Fatalf("剩余订阅数 = %d, want 0", len(subs))
	}
}

// TestSendWebPushDigest_ExhaustedToDeadLetter 覆盖：常驻 500，重试耗尽 → 死信，
// 第二次调用幂等，push_log 仍为 failed_permanent。
func TestSendWebPushDigest_ExhaustedToDeadLetter(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "1")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")
	installInsecureTransport(t)

	srv := newPartialFailureServer(t)
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	defer st.Close()

	user := "local"
	newSubscription(t, st, user, srv.URL+"/flaky")

	wp := newTestWebPushSender(t)
	result := sendWebPushDigest(context.Background(), st, wp,
		"2026-10-22", user, 3)

	if result.Status != "failed_permanent" {
		t.Fatalf("第一次 Status = %q, want %q (Detail=%q)",
			result.Status, "failed_permanent", result.Detail)
	}

	result2 := sendWebPushDigest(context.Background(), st, wp,
		"2026-10-22", user, 3)
	if result2.Status != "failed_permanent" {
		t.Fatalf("第二次 Status = %q, want %q", result2.Status, "failed_permanent")
	}

	status, ok := st.PushLogStatus("2026-10-22", "webpush", user)
	if !ok {
		t.Fatalf("PushLogStatus 未命中记录")
	}
	if status != "failed_permanent" {
		t.Fatalf("PushLogStatus = %q, want %q", status, "failed_permanent")
	}
}
