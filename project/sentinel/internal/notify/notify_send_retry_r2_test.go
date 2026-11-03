package notify

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestR2_SendRetryThenSuccess(t *testing.T) {
	var count atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c := count.Add(1)
		if c < 3 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{}
	start := time.Now()
	err := n.Send(srv.URL, "down", "api", "http://t/", "now", "boom")
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("Send returned error: %v", err)
	}
	if got := count.Load(); got != 3 {
		t.Fatalf("request count = %d, want 3", got)
	}
	if elapsed < 2500*time.Millisecond {
		t.Fatalf("elapsed = %v, want >= 2500ms", elapsed)
	}
	if elapsed >= 10*time.Second {
		t.Fatalf("elapsed = %v, want < 10s", elapsed)
	}
}

func TestR2_SendAllFail(t *testing.T) {
	var count atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count.Add(1)
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	n := Notifier{}
	start := time.Now()
	err := n.Send(srv.URL, "down", "api", "http://t/", "now", "boom")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("Send returned nil error, want failure")
	}
	if !strings.Contains(err.Error(), "Webhook 发送失败") {
		t.Fatalf("error = %v, want contains Webhook 发送失败", err)
	}
	if got := count.Load(); got != 3 {
		t.Fatalf("request count = %d, want 3", got)
	}
	if elapsed < 2500*time.Millisecond {
		t.Fatalf("elapsed = %v, want >= 2500ms", elapsed)
	}
}

func TestR2_SendEmptyURLFast(t *testing.T) {
	n := Notifier{}
	start := time.Now()
	err := n.Send("", "down", "n", "t", "now", "")
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("Send returned error: %v", err)
	}
	if elapsed >= 500*time.Millisecond {
		t.Fatalf("elapsed = %v, want < 500ms", elapsed)
	}
}

func TestR2_SendPayloadFields(t *testing.T) {
	var gotBody []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, err := io.ReadAll(r.Body)
		if err != nil {
			t.Errorf("read request body: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		gotBody = b
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{}
	if err := n.Send(srv.URL, "recovered", "myapi", "http://t/", "2026-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("Send returned error: %v", err)
	}

	if len(gotBody) == 0 {
		t.Fatal("request body is empty")
	}
	if !bytes.Contains(gotBody, []byte(`"service":"sentinel"`)) {
		t.Fatalf("body missing service sentinel: %s", gotBody)
	}

	var fields map[string]any
	if err := json.Unmarshal(gotBody, &fields); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	if v, ok := fields["event"].(string); !ok || v != "recovered" {
		t.Fatalf("event = %v, want recovered", fields["event"])
	}
	if v, ok := fields["name"].(string); !ok || v != "myapi" {
		t.Fatalf("name = %v, want myapi", fields["name"])
	}
	if _, ok := fields["err_msg"]; ok {
		t.Fatal("err_msg field present, want omitted")
	}
}
