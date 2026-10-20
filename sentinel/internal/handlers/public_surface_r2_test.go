package handlers

import (
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func newPublicProbeMonitor(t *testing.T, st *store.Store, name string) int64 {
	t.Helper()
	mid, err := st.CreateMonitor(store.Monitor{
		Name:           name,
		Kind:           "http",
		Target:         "http://127.0.0.1:9/x",
		WebhookURL:     "https://hooks.example.com/secret-token-xyz",
		SMSPhones:      "13800001111",
		NotifyChannels: "webhook,sms",
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}
	return mid
}

func newPublicPage(t *testing.T, st *store.Store, slug string, mids ...int64) {
	t.Helper()
	pid, err := st.CreateStatusPage(1, slug, "title-"+slug)
	if err != nil {
		t.Fatalf("CreateStatusPage failed: %v", err)
	}
	for _, mid := range mids {
		if err := st.AddMonitorToPage(pid, mid); err != nil {
			t.Fatalf("AddMonitorToPage failed: %v", err)
		}
	}
}

func TestR2_PublicStatusHidesSensitiveFields(t *testing.T) {
	srv, st := newTestServer(t)
	mid := newPublicProbeMonitor(t, st, "secret-probe")
	newPublicPage(t, st, "pub-r2a", mid)

	req := httptest.NewRequest("GET", "/api/status/pub-r2a", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	s := rec.Body.String()
	for _, bad := range []string{"secret-token-xyz", "13800001111", "webhook_url", "sms_phones", "notify_channels", "tenant_id"} {
		if strings.Contains(s, bad) {
			t.Fatalf("public response leaks %q", bad)
		}
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	topWant := map[string]bool{"slug": true, "title": true, "theme": true, "accent_color": true, "updated_at": true, "monitors": true}
	for k := range body {
		if !topWant[k] {
			t.Fatalf("unexpected top-level key %q", k)
		}
	}
	mons, _ := body["monitors"].([]any)
	if len(mons) != 1 {
		t.Fatalf("monitors len=%d want 1", len(mons))
	}
	m0, _ := mons[0].(map[string]any)
	monWant := map[string]bool{"id": true, "name": true, "kind": true, "status": true, "uptime_30d": true, "last_checked_at": true, "latency_ms": true}
	for k := range m0 {
		if !monWant[k] {
			t.Fatalf("unexpected monitor key %q", k)
		}
	}
	for k := range monWant {
		if _, ok := m0[k]; !ok {
			t.Fatalf("missing monitor key %q", k)
		}
	}
	if m0["name"] != "secret-probe" {
		t.Fatalf("monitor name=%v want secret-probe", m0["name"])
	}
}

func TestR2_PublicStatusUnknownSlug404(t *testing.T) {
	srv, _ := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/status/no-such-page-zzz", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != 404 {
		t.Fatalf("code=%d want 404", rec.Code)
	}
}

func TestR2_StatusPageManageRequiresAuth(t *testing.T) {
	srv, _ := newTestServer(t)
	cases := []struct {
		method string
		path   string
		body   string
	}{
		{"POST", "/api/status-pages", `{"slug":"x","title":"x"}`},
		{"PUT", "/api/status-pages/1/theme", `{"theme":"dark"}`},
		{"POST", "/api/status-pages/1/snapshot", ``},
	}
	for _, c := range cases {
		var rdr *strings.Reader
		if c.body != "" {
			rdr = strings.NewReader(c.body)
		} else {
			rdr = strings.NewReader("")
		}
		req := httptest.NewRequest(c.method, c.path, rdr)
		if c.body != "" {
			req.Header.Set("Content-Type", "application/json")
		}
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec, req)
		if rec.Code != 401 {
			t.Fatalf("%s %s: code=%d want 401", c.method, c.path, rec.Code)
		}
	}
}

func TestR2_PublicSubscribeStaysPublic(t *testing.T) {
	srv, st := newTestServer(t)
	newPublicPage(t, st, "pub-r2b")
	req := httptest.NewRequest("POST", "/api/status/pub-r2b/subscribe", strings.NewReader(`{"email":"not-an-email"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code == 401 {
		t.Fatalf("subscribe endpoint returned 401: it is public by design")
	}
}

func TestR2_PublicStatusOnlyOwnPageMonitors(t *testing.T) {
	srv, st := newTestServer(t)
	mid := newPublicProbeMonitor(t, st, "only-in-c1")
	newPublicPage(t, st, "pub-r2c1", mid)
	newPublicPage(t, st, "pub-r2c2")

	for _, tc := range []struct {
		slug     string
		contains bool
	}{
		{"pub-r2c1", true},
		{"pub-r2c2", false},
	} {
		req := httptest.NewRequest("GET", "/api/status/"+tc.slug, nil)
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec, req)
		if rec.Code != 200 {
			t.Fatalf("GET %s: code=%d", tc.slug, rec.Code)
		}
		has := strings.Contains(rec.Body.String(), "only-in-c1")
		if has != tc.contains {
			t.Fatalf("GET %s: contains monitor=%v want %v", tc.slug, has, tc.contains)
		}
	}
}
