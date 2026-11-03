package notify

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	mlog "github.com/Wanfeng1028/muse/mortisedb/internal/log"
)

func newDeep2Notifier(t *testing.T, url string, timeout string) *Notifier {
	t.Helper()
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = url
	cfg.Notify.ConflictWebhookTimeout = timeout
	logger := mlog.New(io.Discard, "info")
	n := FromConfig(cfg, logger)
	if n == nil {
		t.Fatalf("FromConfig returned nil for url %q", url)
	}
	return n
}

func TestDeep2Attempt_BackoffJitterBounds(t *testing.T) {
	for a := 0; a <= 6; a++ {
		base := time.Second * time.Duration(1<<uint(a))
		lo := time.Duration(float64(base) * 0.75)
		hi := time.Duration(float64(base) * 1.25)
		for i := 0; i < 200; i++ {
			d := backoffDelay(a)
			if d < lo || d > hi {
				t.Fatalf("attempt=%d sample=%d delay=%v out of [%v,%v]", a, i, d, lo, hi)
			}
		}
		if a == 0 {
			for i := 0; i < 200; i++ {
				if d := backoffDelay(0); d >= 1300*time.Millisecond {
					t.Fatalf("attempt=0 delay=%v not < 1.3s", d)
				}
			}
		}
	}
}

func TestDeep2Attempt_BackoffGrows(t *testing.T) {
	medians := make([]time.Duration, 6)
	for a := 0; a <= 5; a++ {
		samples := make([]time.Duration, 0, 200)
		for i := 0; i < 200; i++ {
			samples = append(samples, backoffDelay(a))
		}
		sort.Slice(samples, func(i, j int) bool { return samples[i] < samples[j] })
		medians[a] = samples[len(samples)/2]
	}
	for a := 1; a <= 5; a++ {
		if medians[a] <= medians[a-1] {
			t.Fatalf("median not strictly increasing: a=%d med=%v <= a=%d med=%v", a, medians[a], a-1, medians[a-1])
		}
	}
}

func TestDeep2Attempt_StatusClassification(t *testing.T) {
	statusByPath := map[string]int{
		"/s200": 200,
		"/s201": 201,
		"/s204": 204,
		"/s301": 301,
		"/s400": 400,
		"/s404": 404,
		"/s422": 422,
		"/s429": 429,
		"/s500": 500,
		"/s503": 503,
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if code, ok := statusByPath[r.URL.Path]; ok {
			if code == 301 {
				w.Header().Set("Location", "/s200")
			}
			w.WriteHeader(code)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cases := []struct {
		path string
		want deliverResult
	}{
		{"/s200", resultDelivered},
		{"/s201", resultDelivered},
		{"/s204", resultDelivered},
		{"/s301", resultRetry},
		{"/s400", resultDropped},
		{"/s404", resultDropped},
		{"/s422", resultDropped},
		{"/s429", resultRetry},
		{"/s500", resultRetry},
		{"/s503", resultRetry},
	}
	for _, tc := range cases {
		n := newDeep2Notifier(t, srv.URL+tc.path, "5s")
		got, msg := n.attempt(n.client(), EventPending, "did", "sha256=x", []byte(`{}`))
		if got != tc.want {
			t.Fatalf("path=%s got=%v want=%v msg=%q", tc.path, got, tc.want, msg)
		}
	}
}

func TestDeep2Attempt_NetworkErrorRetries(t *testing.T) {
	n := newDeep2Notifier(t, "http://127.0.0.1:1/hook", "2s")
	got, msg := n.attempt(n.client(), EventPending, "did", "sha256=x", []byte(`{}`))
	if got != resultRetry {
		t.Fatalf("network error got=%v want=%v", got, resultRetry)
	}
	if msg == "" {
		t.Fatalf("network error expected non-empty errMsg")
	}
}

func TestDeep2Attempt_TimeoutRetries(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(3 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := newDeep2Notifier(t, srv.URL+"/hook", "100ms")
	got, _ := n.attempt(n.client(), EventPending, "did", "sha256=x", []byte(`{}`))
	if got != resultRetry {
		t.Fatalf("timeout got=%v want=%v", got, resultRetry)
	}
}

func TestDeep2Attempt_HeadersSent(t *testing.T) {
	var mu sync.Mutex
	var gotHeaders http.Header
	var gotBody []byte
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		gotHeaders = r.Header.Clone()
		b, _ := io.ReadAll(r.Body)
		gotBody = b
		mu.Unlock()
		atomic.AddInt32(&hits, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	body := []byte(`{"event":"pending","n":1}`)
	n := newDeep2Notifier(t, srv.URL+"/hook", "5s")
	got, _ := n.attempt(n.client(), EventPending, "did-123", "sha256=abc", body)
	if got != resultDelivered {
		t.Fatalf("got=%v want=%v", got, resultDelivered)
	}
	if atomic.LoadInt32(&hits) != 1 {
		t.Fatalf("expected 1 request, got %d", hits)
	}
	mu.Lock()
	defer mu.Unlock()
	if ct := gotHeaders.Get("Content-Type"); ct != "application/json" {
		t.Fatalf("Content-Type=%q want application/json", ct)
	}
	for _, h := range []string{"X-Mortise-Signature", "X-Mortise-Event", "X-Mortise-Delivery-Id"} {
		if gotHeaders.Get(h) == "" {
			t.Fatalf("header %s is empty", h)
		}
	}
	if !bytes.Equal(gotBody, body) {
		t.Fatalf("body mismatch got=%q want=%q", gotBody, body)
	}
}

func TestDeep2Attempt_3xxNoFollow(t *testing.T) {
	var targetHits int32
	mux := http.NewServeMux()
	mux.HandleFunc("/redir", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Location", "/target")
		w.WriteHeader(http.StatusFound)
	})
	mux.HandleFunc("/target", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&targetHits, 1)
		w.WriteHeader(http.StatusOK)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	n := newDeep2Notifier(t, srv.URL+"/redir", "5s")
	got, _ := n.attempt(n.client(), EventPending, "did", "sha256=x", []byte(`{}`))
	if got != resultRetry {
		t.Fatalf("3xx got=%v want=%v", got, resultRetry)
	}
	if atomic.LoadInt32(&targetHits) != 0 {
		t.Fatalf("redirect target was followed, hits=%d", targetHits)
	}
}
