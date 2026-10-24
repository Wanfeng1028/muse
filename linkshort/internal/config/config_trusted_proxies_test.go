package config

import (
	"net"
	"testing"
)

func contains(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

func TestParseTrustedProxies_Empty(t *testing.T) {
	nets, err := ParseTrustedProxies("")
	if nets != nil || err != nil {
		t.Fatalf("expected nil, nil for empty string, got %v, %v", nets, err)
	}
	nets, err = ParseTrustedProxies("   ")
	if nets != nil || err != nil {
		t.Fatalf("expected nil, nil for whitespace string, got %v, %v", nets, err)
	}
}

func TestParseTrustedProxies_Mixed(t *testing.T) {
	nets, err := ParseTrustedProxies("10.0.0.1, 192.168.0.0/16, ::1, 2001:db8::/32")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 4 {
		t.Fatalf("expected 4 nets, got %d", len(nets))
	}
	cfg := &Config{TrustedProxies: nets}
	if !cfg.IsTrustedProxy(net.ParseIP("10.0.0.1")) {
		t.Fatalf("expected 10.0.0.1 to be trusted")
	}
	if cfg.IsTrustedProxy(net.ParseIP("10.0.0.2")) {
		t.Fatalf("expected 10.0.0.2 to not be trusted")
	}
	if !cfg.IsTrustedProxy(net.ParseIP("192.168.5.5")) {
		t.Fatalf("expected 192.168.5.5 to be trusted")
	}
	if cfg.IsTrustedProxy(net.ParseIP("172.16.0.1")) {
		t.Fatalf("expected 172.16.0.1 to not be trusted")
	}
	if !cfg.IsTrustedProxy(net.ParseIP("::1")) {
		t.Fatalf("expected ::1 to be trusted")
	}
	if !cfg.IsTrustedProxy(net.ParseIP("2001:db8::9")) {
		t.Fatalf("expected 2001:db8::9 to be trusted")
	}
}

func TestParseTrustedProxies_Invalid(t *testing.T) {
	_, err := ParseTrustedProxies("10.0.0.1, not-an-ip")
	if err == nil || !contains(err.Error(), "not-an-ip") {
		t.Fatalf("expected error containing 'not-an-ip', got %v", err)
	}
	_, err = ParseTrustedProxies("10.0.0.0/33")
	if err == nil {
		t.Fatalf("expected error for invalid CIDR, got nil")
	}
}

func TestParseTrustedProxies_SkipsEmptyItems(t *testing.T) {
	nets, err := ParseTrustedProxies("10.0.0.1,, , 10.0.0.2")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 2 {
		t.Fatalf("expected 2 nets, got %d", len(nets))
	}
}

func TestIsTrustedProxy_NilList(t *testing.T) {
	cfg := &Config{}
	if cfg.IsTrustedProxy(net.ParseIP("10.0.0.1")) {
		t.Fatalf("expected false for nil list")
	}
	if cfg.IsTrustedProxy(nil) {
		t.Fatalf("expected false for nil IP")
	}
}

func TestFromEnv_TrustedProxiesDefault(t *testing.T) {
	t.Setenv(envTrustedProxies, "")
	cfg := FromEnv()
	if cfg.TrustedProxies != nil {
		t.Fatalf("expected nil TrustedProxies, got %v", cfg.TrustedProxies)
	}
}

func TestFromEnv_TrustedProxiesParses(t *testing.T) {
	t.Setenv(envTrustedProxies, "127.0.0.1, 10.0.0.0/8")
	cfg := FromEnv()
	if len(cfg.TrustedProxies) != 2 {
		t.Fatalf("expected 2 TrustedProxies, got %d", len(cfg.TrustedProxies))
	}
	if !cfg.IsTrustedProxy(net.ParseIP("10.9.9.9")) {
		t.Fatalf("expected 10.9.9.9 to be trusted")
	}
}
