package passalert

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestNotifyPasswordFailAlertIP_Payload(t *testing.T) {
	var body string
	hook := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var received strings.Builder
		buf := make([]byte, 1024)
		for {
			n, err := r.Body.Read(buf)
			if n > 0 {
				received.Write(buf[:n])
			}
			if err != nil {
				break
			}
		}
		body = received.String()
		w.WriteHeader(http.StatusOK)
	}))
	defer hook.Close()

	NotifyPasswordFailAlertIP(hook.URL, "example.com", "192.0.2.9", 5, time.Minute, 3)

	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(body), &payload); err != nil {
		t.Fatalf("decode webhook body: %v (body=%q)", err, body)
	}

	if payload["scope"] != "ip" {
		t.Errorf("scope = %v, want %q", payload["scope"], "ip")
	}
	if payload["slug"] != "" {
		t.Errorf("slug = %v, want empty string", payload["slug"])
	}

	ipHash, ok := payload["ip_hash"].(string)
	if !ok {
		t.Fatalf("ip_hash = %v, want string", payload["ip_hash"])
	}
	if ipHash != HashIP("192.0.2.9") {
		t.Errorf("ip_hash = %q, want %q", ipHash, HashIP("192.0.2.9"))
	}
	if len(ipHash) != 16 {
		t.Errorf("len(ip_hash) = %d, want 16", len(ipHash))
	}
	if strings.Contains(body, `"ip":`) {
		t.Errorf("body contains an ip field: %s", body)
	}
}

func TestNotifyPasswordFailAlert_ScopeSlug(t *testing.T) {
	var body string
	hook := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var received strings.Builder
		buf := make([]byte, 1024)
		for {
			n, err := r.Body.Read(buf)
			if n > 0 {
				received.Write(buf[:n])
			}
			if err != nil {
				break
			}
		}
		body = received.String()
		w.WriteHeader(http.StatusOK)
	}))
	defer hook.Close()

	NotifyPasswordFailAlert(hook.URL, "example.com", "abc", 10, time.Minute, 10)

	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(body), &payload); err != nil {
		t.Fatalf("decode webhook body: %v (body=%q)", err, body)
	}

	if payload["scope"] != "slug" {
		t.Errorf("scope = %v, want %q", payload["scope"], "slug")
	}
	if payload["slug"] != "abc" {
		t.Errorf("slug = %v, want %q", payload["slug"], "abc")
	}
	if strings.Contains(body, "ip_hash") {
		t.Errorf("body contains ip_hash: %s", body)
	}
}

func TestNotifyPasswordFailAlert_EmptyURL(t *testing.T) {
	defer func() {
		if recovered := recover(); recovered != nil {
			t.Fatalf("unexpected panic: %v", recovered)
		}
	}()

	NotifyPasswordFailAlert("", "h", "s", 1, time.Minute, 1)
	NotifyPasswordFailAlertIP("", "h", "1.1.1.1", 1, time.Minute, 1)
}

func TestHashIP(t *testing.T) {
	body := HashIP("192.0.2.9")
	second := HashIP("192.0.2.9")

	if body != second {
		t.Errorf("HashIP is not deterministic: %q != %q", body, second)
	}
	if len(body) != 16 {
		t.Errorf("len(HashIP) = %d, want 16", len(body))
	}
	if strings.Trim(body, "0123456789abcdef") != "" {
		t.Errorf("HashIP returned a non-lowercase-hex value: %q", body)
	}
	if HashIP("") != "" {
		t.Errorf("HashIP(\"\") = %q, want empty string", HashIP(""))
	}
}
