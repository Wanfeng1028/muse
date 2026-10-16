
package passalert

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestNotify_EmptyURL(t *testing.T) {
	// 不应 panic
	NotifyPasswordFailAlert("", "h", "s", 3, time.Minute, 10)
}

func TestNotify_SendsJSON(t *testing.T) {
	var mu sync.Mutex
	var bodies []string
	contentTypes := []string{}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		buf := make([]byte, 0)
		tmp := make([]byte, 1024)
		for {
			n, err := r.Body.Read(tmp)
			if n > 0 {
				buf = append(buf, tmp[:n]...)
			}
			if err != nil {
				break
			}
		}
		mu.Lock()
		bodies = append(bodies, string(buf))
		contentTypes = append(contentTypes, r.Header.Get("Content-Type"))
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	NotifyPasswordFailAlert(srv.URL, "host1", "s1", 7, 5*time.Minute, 10)

	mu.Lock()
	defer mu.Unlock()
	if len(bodies) != 1 {
		t.Fatalf("期望收到 1 条请求，实际 %d", len(bodies))
	}
	if !strings.Contains(contentTypes[0], "application/json") {
		t.Fatalf("Content-Type 期望包含 application/json，实际 %q", contentTypes[0])
	}

	var payload AlertPayload
	if err := json.Unmarshal([]byte(bodies[0]), &payload); err != nil {
		t.Fatalf("解析 JSON 失败: %v body=%s", err, bodies[0])
	}
	if payload.Source != "linkshort" {
		t.Errorf("source 期望 linkshort，实际 %q", payload.Source)
	}
	if payload.Event != "password_fail_alert" {
		t.Errorf("event 期望 password_fail_alert，实际 %q", payload.Event)
	}
	if payload.Slug != "s1" {
		t.Errorf("slug 期望 s1，实际 %q", payload.Slug)
	}
	if payload.FailCount != 7 {
		t.Errorf("fail_count 期望 7，实际 %d", payload.FailCount)
	}
	if payload.Threshold != 10 {
		t.Errorf("threshold 期望 10，实际 %d", payload.Threshold)
	}
	if payload.WindowSeconds != 300 {
		t.Errorf("window_seconds 期望 300，实际 %d", payload.WindowSeconds)
	}
}

func TestNotify_ServerErrorNoPanic(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	// 不应 panic
	NotifyPasswordFailAlert(srv.URL, "h", "s", 1, time.Minute, 10)
}
