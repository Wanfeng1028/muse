package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/passalert"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newAlertIPTestServer(t *testing.T, slugThreshold, ipThreshold int, webhookURLs []string) *httptest.Server {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open(:memory:) 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)
	cfg := &config.Config{
		AdminKey:                     testKey,
		PasswordFailAlertThreshold:   slugThreshold,
		PasswordFailAlertWindow:      time.Minute,
		PasswordFailAlertIPThreshold: ipThreshold,
		AlertWebhookURL:              strings.Join(webhookURLs, ","),
		AlertWebhookURLs:             webhookURLs,
	}
	passalert.ConfigureWithIP(slugThreshold, time.Minute, ipThreshold)
	t.Cleanup(func() { passalert.Configure(10, 5*time.Minute) })
	srv := httptest.NewServer(NewRouter(st, cfg))
	t.Cleanup(srv.Close)
	return srv
}

type hookRecorder struct {
	mu     sync.Mutex
	bodies []string
	fail   bool
}

func newHookRecorder(t *testing.T, fail bool) (*hookRecorder, *httptest.Server) {
	t.Helper()
	rec := &hookRecorder{fail: fail}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		buf, _ := io.ReadAll(r.Body)
		r.Body.Close()
		rec.mu.Lock()
		rec.bodies = append(rec.bodies, string(buf))
		rec.mu.Unlock()
		if fail {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	return rec, srv
}

func (rec *hookRecorder) count() int {
	rec.mu.Lock()
	defer rec.mu.Unlock()
	return len(rec.bodies)
}

func (rec *hookRecorder) first() string {
	rec.mu.Lock()
	defer rec.mu.Unlock()
	if len(rec.bodies) == 0 {
		return ""
	}
	return rec.bodies[0]
}

func TestPasswordAlertIP_FiresWebhook(t *testing.T) {
	oldCost := auth.BcryptCost
	auth.BcryptCost = bcrypt.MinCost
	defer func() { auth.BcryptCost = oldCost }()

	rec, hook := newHookRecorder(t, false)
	srv := newAlertIPTestServer(t, 1000, 3, []string{hook.URL})

	slugs := make([]string, 3)
	for i := range slugs {
		slugs[i] = createPasswordLink(t, srv, "https://example.com/x", "pw")
	}
	for _, slug := range slugs {
		wrongPassword(t, srv, slug)
	}

	deadline := time.Now().Add(3 * time.Second)
	for {
		if rec.count() >= 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("等待 IP 告警 webhook 超时")
		}
		time.Sleep(20 * time.Millisecond)
	}

	body := rec.first()
	var payload map[string]any
	if err := json.Unmarshal([]byte(body), &payload); err != nil {
		t.Fatalf("解析 webhook payload 失败: %v; body=%q", err, body)
	}
	if scope, ok := payload["scope"].(string); !ok || scope != "ip" {
		t.Fatalf("scope=%v，期望 ip", payload["scope"])
	}
	if slug, ok := payload["slug"].(string); !ok || slug != "" {
		t.Fatalf("slug=%v，期望空字符串", payload["slug"])
	}
	ipHash, ok := payload["ip_hash"].(string)
	if !ok {
		t.Fatalf("ip_hash=%v，期望字符串", payload["ip_hash"])
	}
	if len(ipHash) != 16 {
		t.Fatalf("ip_hash 长度=%d，期望 16", len(ipHash))
	}
	if ipHash != passalert.HashIP("127.0.0.1") {
		t.Fatalf("ip_hash=%q，期望 %q", ipHash, passalert.HashIP("127.0.0.1"))
	}
	if strings.Contains(body, `"ip":`) {
		t.Fatalf("payload 不应包含原始 IP: %q", body)
	}

	wrongPassword(t, srv, slugs[0])
	time.Sleep(300 * time.Millisecond)
	if got := rec.count(); got != 1 {
		t.Fatalf("webhook 次数=%d，期望 1", got)
	}
}

func TestPasswordAlert_MultiWebhook(t *testing.T) {
	oldCost := auth.BcryptCost
	auth.BcryptCost = bcrypt.MinCost
	defer func() { auth.BcryptCost = oldCost }()

	rec1, hook1 := newHookRecorder(t, false)
	rec2, hook2 := newHookRecorder(t, false)
	srv := newAlertIPTestServer(t, 2, 1000, []string{hook1.URL, hook2.URL})

	slug := createPasswordLink(t, srv, "https://example.com/x", "pw")
	wrongPassword(t, srv, slug)
	wrongPassword(t, srv, slug)

	deadline := time.Now().Add(3 * time.Second)
	for {
		if rec1.count() >= 1 && rec2.count() >= 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("等待多个 webhook 超时: rec1=%d, rec2=%d", rec1.count(), rec2.count())
		}
		time.Sleep(20 * time.Millisecond)
	}

	if got := rec1.count(); got != 1 {
		t.Fatalf("第一个 webhook 次数=%d，期望 1", got)
	}
	if got := rec2.count(); got != 1 {
		t.Fatalf("第二个 webhook 次数=%d，期望 1", got)
	}
}

func TestPasswordAlert_MultiWebhookOneFails(t *testing.T) {
	oldCost := auth.BcryptCost
	auth.BcryptCost = bcrypt.MinCost
	defer func() { auth.BcryptCost = oldCost }()

	rec1, hook1 := newHookRecorder(t, false)
	rec2, hook2 := newHookRecorder(t, true)
	srv := newAlertIPTestServer(t, 2, 1000, []string{hook1.URL, hook2.URL})

	slug := createPasswordLink(t, srv, "https://example.com/x", "pw")
	wrongPassword(t, srv, slug)
	wrongPassword(t, srv, slug)

	deadline := time.Now().Add(3 * time.Second)
	for {
		if rec1.count() >= 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("等待成功 webhook 超时: rec1=%d, rec2=%d", rec1.count(), rec2.count())
		}
		time.Sleep(20 * time.Millisecond)
	}

	if got := rec1.count(); got != 1 {
		t.Fatalf("成功 webhook 次数=%d，期望 1", got)
	}
}
