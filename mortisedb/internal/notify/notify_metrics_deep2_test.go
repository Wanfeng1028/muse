package notify

import (
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	mlog "github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func deep2MetricDelta(t *testing.T, event, status string) float64 {
	t.Helper()
	before := deep2MetricValue(t, event, status)
	deep2MetricBefore = before
	return before
}

var deep2MetricBefore float64

func deep2MetricValue(t *testing.T, event, status string) float64 {
	t.Helper()
	text := metrics.Default().Render()
	prefix := MetricDeliveries + `{event="` + event + `",status="` + status + `"}`
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, prefix) {
			rest := strings.TrimSpace(strings.TrimPrefix(line, prefix))
			if rest == "" {
				continue
			}
			fields := strings.Fields(rest)
			if len(fields) == 0 {
				continue
			}
			return parseFloat(fields[0])
		}
	}
	return 0
}

func parseFloat(s string) float64 {
	var f float64
	var neg bool
	i := 0
	if i < len(s) && (s[i] == '-' || s[i] == '+') {
		neg = s[i] == '-'
		i++
	}
	for ; i < len(s); i++ {
		c := s[i]
		if c == '.' {
			frac := 0.1
			i++
			for ; i < len(s); i++ {
				c = s[i]
				if c < '0' || c > '9' {
					break
				}
				f += float64(c-'0') * frac
				frac /= 10
			}
			break
		}
		if c < '0' || c > '9' {
			break
		}
		f = f*10 + float64(c-'0')
	}
	if neg {
		return -f
	}
	return f
}

func deep2Delta(t *testing.T, before, event, status string) float64 {
	t.Helper()
	return deep2MetricValue(t, event, status) - parseFloat(before)
}

func deep2Snapshot(t *testing.T, event, status string) string {
	t.Helper()
	return floatToString(deep2MetricValue(t, event, status))
}

func floatToString(f float64) string {
	if f == float64(int64(f)) {
		return itoa(int64(f))
	}
	return "0"
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

func deep2WaitMetric(t *testing.T, event, status string, before string, want float64) {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for {
		got := deep2Delta(t, before, event, status)
		if got == want {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("metric %s{event=%q,status=%q} delta = %v, want %v", MetricDeliveries, event, status, got, want)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func deep2NewNotifier(t *testing.T, url string, events []string, maxRetries int) *Notifier {
	t.Helper()
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = url
	cfg.Notify.ConflictWebhookSecret = "deep2-secret"
	cfg.Notify.ConflictEvents = events
	cfg.Notify.ConflictWebhookMaxRetries = maxRetries
	return FromConfig(cfg, mlog.New(io.Discard, "info"))
}

func deep2OpenStore(t *testing.T) *store.Store {
	t.Helper()
	path := filepath.Join(t.TempDir(), "test.db")
	st, err := store.Open(path)
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("store.Migrate: %v", err)
	}
	t.Cleanup(func() { st.Close() })
	return st
}

func TestDeep2Metric_DeliveredCounted(t *testing.T) {
	var count int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := deep2NewNotifier(t, srv.URL, []string{EventPending}, 2)

	beforeDelivered := deep2Snapshot(t, EventPending, "delivered")
	beforeFailed := deep2Snapshot(t, EventPending, "failed")
	beforeDropped := deep2Snapshot(t, EventPending, "dropped")

	n.NotifyAsync(EventPending, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventPending, "delivered", beforeDelivered, 1)
	if d := deep2Delta(t, beforeFailed, EventPending, "failed"); d != 0 {
		t.Fatalf("failed delta = %v, want 0", d)
	}
	if d := deep2Delta(t, beforeDropped, EventPending, "dropped"); d != 0 {
		t.Fatalf("dropped delta = %v, want 0", d)
	}
}

func TestDeep2Metric_FailedAfterRetriesExhausted(t *testing.T) {
	var count int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	n := deep2NewNotifier(t, srv.URL, []string{EventPending}, 2)

	beforeFailed := deep2Snapshot(t, EventPending, "failed")
	beforeDelivered := deep2Snapshot(t, EventPending, "delivered")

	n.NotifyAsync(EventPending, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventPending, "failed", beforeFailed, 1)
	if d := deep2Delta(t, beforeDelivered, EventPending, "delivered"); d != 0 {
		t.Fatalf("delivered delta = %v, want 0", d)
	}

	deadline := time.Now().Add(10 * time.Second)
	for {
		if atomic.LoadInt64(&count) == 3 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("requests = %d, want 3", atomic.LoadInt64(&count))
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func TestDeep2Metric_DroppedOn400(t *testing.T) {
	var count int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	n := deep2NewNotifier(t, srv.URL, []string{EventPending}, 2)

	beforeDropped := deep2Snapshot(t, EventPending, "dropped")

	n.NotifyAsync(EventPending, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventPending, "dropped", beforeDropped, 1)

	deadline := time.Now().Add(10 * time.Second)
	for {
		if atomic.LoadInt64(&count) == 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("requests = %d, want 1", atomic.LoadInt64(&count))
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func TestDeep2Metric_DroppedWhenDisabled(t *testing.T) {
	beforeDropped := deep2Snapshot(t, EventPending, "dropped")

	n := deep2NewNotifier(t, "", []string{EventPending}, 2)
	n.NotifyAsync(EventPending, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventPending, "dropped", beforeDropped, 1)
}

func TestDeep2Metric_DroppedWhenUnsubscribed(t *testing.T) {
	var count int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := deep2NewNotifier(t, srv.URL, []string{EventPending}, 2)

	beforeDropped := deep2Snapshot(t, EventResolved, "dropped")

	n.NotifyAsync(EventResolved, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventResolved, "dropped", beforeDropped, 1)

	if c := atomic.LoadInt64(&count); c != 0 {
		t.Fatalf("requests = %d, want 0", c)
	}
}

func TestDeep2Metric_DroppedOn429ThenFailed(t *testing.T) {
	var count int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	n := deep2NewNotifier(t, srv.URL, []string{EventPending}, 1)

	beforeFailed := deep2Snapshot(t, EventPending, "failed")

	n.NotifyAsync(EventPending, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventPending, "failed", beforeFailed, 1)

	deadline := time.Now().Add(10 * time.Second)
	for {
		if atomic.LoadInt64(&count) == 2 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("requests = %d, want 2", atomic.LoadInt64(&count))
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func TestDeep2Metric_EventsLabeledSeparately(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := deep2NewNotifier(t, srv.URL, []string{EventPending, EventResolved}, 2)

	beforePending := deep2Snapshot(t, EventPending, "delivered")
	beforeResolved := deep2Snapshot(t, EventResolved, "delivered")

	n.NotifyAsync(EventPending, store.Conflict{TableName: "t", PK: "1", SourceA: "a", SourceB: "b", Status: "pending"})
	n.NotifyAsync(EventResolved, store.Conflict{TableName: "t", PK: "2", SourceA: "a", SourceB: "b", Status: "pending"})

	deep2WaitMetric(t, EventPending, "delivered", beforePending, 1)
	deep2WaitMetric(t, EventResolved, "delivered", beforeResolved, 1)
}

func TestDeep2Metric_FireAfterCommitDisabledDrops(t *testing.T) {
	st := deep2OpenStore(t)

	beforePending := deep2Snapshot(t, EventPending, "dropped")
	beforeResolved := deep2Snapshot(t, EventResolved, "dropped")

	n := deep2NewNotifier(t, "", []string{EventPending, EventResolved}, 2)

	n.FireAfterCommit(st, []PendingNotify{
		{Event: EventPending},
		{Event: EventResolved},
	})

	deadline := time.Now().Add(10 * time.Second)
	for {
		dp := deep2Delta(t, beforePending, EventPending, "dropped")
		dr := deep2Delta(t, beforeResolved, EventResolved, "dropped")
		if dp == 1 && dr == 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("dropped deltas pending=%v resolved=%v, want 1 and 1", dp, dr)
		}
		time.Sleep(50 * time.Millisecond)
	}
}
