package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
)

func trustedProxyTestConfig(t *testing.T, cidrs ...string) *config.Config {
	t.Helper()
	s := strings.Join(cidrs, ",")
	nets, err := config.ParseTrustedProxies(s)
	if err != nil {
		t.Fatalf("failed to parse trusted proxies %q: %v", s, err)
	}
	return &config.Config{TrustedProxies: nets}
}

func TestClientIP_UntrustedPeerIgnoresXFF(t *testing.T) {
	cfg := trustedProxyTestConfig(t)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Forwarded-For", "9.9.9.9, 8.8.8.8")
	req.Header.Set("X-Real-IP", "7.7.7.7")

	got := clientIP(req, cfg)
	want := "192.0.2.1"
	if got != want {
		t.Fatalf("expected clientIP %q, got %q", want, got)
	}
}

func TestClientIP_TrustedPeerHonorsXFF(t *testing.T) {
	cfg := trustedProxyTestConfig(t, "192.0.2.1/32")
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Forwarded-For", "9.9.9.9, 8.8.8.8")

	got := clientIP(req, cfg)
	want := "9.9.9.9"
	if got != want {
		t.Fatalf("expected clientIP %q, got %q", want, got)
	}
}

func TestClientIP_TrustedPeerFallsBackToXRealIP(t *testing.T) {
	cfg := trustedProxyTestConfig(t, "192.0.2.0/24")
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Forwarded-For", "garbage")
	req.Header.Set("X-Real-IP", "7.7.7.7")

	got := clientIP(req, cfg)
	want := "7.7.7.7"
	if got != want {
		t.Fatalf("expected clientIP %q, got %q", want, got)
	}
}

func TestClientIP_TrustedPeerInvalidHeadersFallback(t *testing.T) {
	cfg := trustedProxyTestConfig(t, "192.0.2.0/24")
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Forwarded-For", "garbage")

	got := clientIP(req, cfg)
	want := "192.0.2.1"
	if got != want {
		t.Fatalf("expected clientIP %q, got %q", want, got)
	}
}

func TestTrustedPeer_NilConfig(t *testing.T) {
	if trustedPeer("192.0.2.1:1234", nil) {
		t.Fatalf("expected trustedPeer to be false for nil config")
	}
}

func TestTrustedPeer_CIDRRange(t *testing.T) {
	cfg := trustedProxyTestConfig(t, "10.0.0.0/8")

	if !trustedPeer("10.5.6.7:9999", cfg) {
		t.Fatalf("expected 10.5.6.7 to be a trusted peer")
	}
	if trustedPeer("11.0.0.1:9999", cfg) {
		t.Fatalf("expected 11.0.0.1 to be an untrusted peer")
	}
}
