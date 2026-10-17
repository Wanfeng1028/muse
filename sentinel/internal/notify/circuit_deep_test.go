package notify

import (
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestBreakerStateString(t *testing.T) {
	cases := []struct {
		name string
		in   BreakerState
		want string
	}{
		{"closed", BreakerClosed, "closed"},
		{"open", BreakerOpen, "open"},
		{"half-open", BreakerHalfOpen, "half-open"},
		{"unknown", BreakerState(99), "unknown"},
		{"negative", BreakerState(-1), "unknown"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := tc.in.String()
			if got != tc.want {
				t.Fatalf("String() = %q, want %q", got, tc.want)
			}
			if len(got) == 0 {
				t.Fatalf("String() returned empty string for state %d", int(tc.in))
			}
		})
	}
}

func TestNewCircuitBreakerDefaults(t *testing.T) {
	cases := []struct {
		name       string
		threshold  int
		timeout    time.Duration
		wantThresh int
		wantTO     time.Duration
	}{
		{"both valid", 3, 2 * time.Second, 3, 2 * time.Second},
		{"zero threshold", 0, time.Second, 5, time.Second},
		{"negative threshold", -7, time.Second, 5, time.Second},
		{"zero timeout", 4, 0, 4, 5 * time.Minute},
		{"negative timeout", 4, -3 * time.Second, 4, 5 * time.Minute},
		{"both invalid", -1, -1, 5, 5 * time.Minute},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cb := NewCircuitBreaker(tc.threshold, tc.timeout)
			if cb.failureThreshold != tc.wantThresh {
				t.Fatalf("failureThreshold = %d, want %d", cb.failureThreshold, tc.wantThresh)
			}
			if cb.openTimeout != tc.wantTO {
				t.Fatalf("openTimeout = %v, want %v", cb.openTimeout, tc.wantTO)
			}
			if cb.state != BreakerClosed {
				t.Fatalf("initial state = %v, want closed", cb.state)
			}
			if cb.failures != 0 {
				t.Fatalf("initial failures = %d, want 0", cb.failures)
			}
			if cb.probeInFlight {
				t.Fatalf("initial probeInFlight = true, want false")
			}
		})
	}
}

func TestCircuitBreakerTripAtThreshold(t *testing.T) {
	cb := NewCircuitBreaker(3, time.Minute)
	for i := 0; i < 2; i++ {
		if !cb.BeforeRequest() {
			t.Fatalf("BeforeRequest #%d = false, want true while closed", i)
		}
		cb.AfterRequest(false)
		if cb.State() != BreakerClosed {
			t.Fatalf("state after %d failures = %v, want closed", i+1, cb.State())
		}
	}
	if !cb.BeforeRequest() {
		t.Fatalf("BeforeRequest before third failure = false, want true")
	}
	cb.AfterRequest(false)
	if cb.State() != BreakerOpen {
		t.Fatalf("state after threshold failures = %v, want open", cb.State())
	}
	if cb.BeforeRequest() {
		t.Fatalf("BeforeRequest while open = true, want false")
	}
}

func TestCircuitBreakerSuccessResetsFailures(t *testing.T) {
	cb := NewCircuitBreaker(3, time.Minute)
	cb.AfterRequest(false)
	cb.AfterRequest(false)
	if cb.failures != 2 {
		t.Fatalf("failures = %d, want 2", cb.failures)
	}
	cb.AfterRequest(true)
	if cb.failures != 0 {
		t.Fatalf("failures after success = %d, want 0", cb.failures)
	}
	cb.AfterRequest(false)
	cb.AfterRequest(false)
	if cb.State() != BreakerClosed {
		t.Fatalf("state = %v, want closed (below threshold)", cb.State())
	}
	if cb.failures != 2 {
		t.Fatalf("failures = %d, want 2", cb.failures)
	}
}

func TestCircuitBreakerHalfOpenTransition(t *testing.T) {
	cb := NewCircuitBreaker(1, 30*time.Millisecond)
	cb.AfterRequest(false)
	if cb.State() != BreakerOpen {
		t.Fatalf("state = %v, want open", cb.State())
	}
	if cb.BeforeRequest() {
		t.Fatalf("BeforeRequest immediately after open = true, want false")
	}
	time.Sleep(50 * time.Millisecond)
	if !cb.BeforeRequest() {
		t.Fatalf("BeforeRequest after timeout = false, want true (probe allowed)")
	}
	if cb.State() != BreakerHalfOpen {
		t.Fatalf("state = %v, want half-open", cb.State())
	}
	if cb.BeforeRequest() {
		t.Fatalf("second concurrent probe = true, want false")
	}
	cb.AfterRequest(true)
	if cb.State() != BreakerClosed {
		t.Fatalf("state after successful probe = %v, want closed", cb.State())
	}
	if cb.failures != 0 {
		t.Fatalf("failures = %d, want 0", cb.failures)
	}
}

func TestCircuitBreakerHalfOpenProbeFailure(t *testing.T) {
	cb := NewCircuitBreaker(1, 30*time.Millisecond)
	cb.AfterRequest(false)
	time.Sleep(50 * time.Millisecond)
	if !cb.BeforeRequest() {
		t.Fatalf("probe before request = false, want true")
	}
	if cb.State() != BreakerHalfOpen {
		t.Fatalf("state = %v, want half-open", cb.State())
	}
	cb.AfterRequest(false)
	if cb.State() != BreakerOpen {
		t.Fatalf("state after failed probe = %v, want open", cb.State())
	}
	if cb.BeforeRequest() {
		t.Fatalf("BeforeRequest right after reopen = true, want false")
	}
}

func TestCircuitBreakerAfterRequestInOpenIgnored(t *testing.T) {
	cb := NewCircuitBreaker(1, time.Minute)
	cb.AfterRequest(false)
	if cb.State() != BreakerOpen {
		t.Fatalf("state = %v, want open", cb.State())
	}
	openedAt := cb.openedAt
	cb.AfterRequest(false)
	cb.AfterRequest(true)
	if cb.State() != BreakerOpen {
		t.Fatalf("state after callbacks in open = %v, want open", cb.State())
	}
	if !cb.openedAt.Equal(openedAt) {
		t.Fatalf("openedAt changed from %v to %v while open", openedAt, cb.openedAt)
	}
}

func TestBreakerRegistryGetKeying(t *testing.T) {
	cases := []struct {
		name     string
		first    string
		second   string
		same     bool
		wantKeys []string
	}{
		{
			name:     "same host different path",
			first:    "https://Example.com/a",
			second:   "https://example.com/b",
			same:     true,
			wantKeys: []string{"example.com"},
		},
		{
			name:     "same host with port and scheme",
			first:    "http://api.example.com:8080/x",
			second:   "https://API.example.com:9090/y",
			same:     true,
			wantKeys: []string{"api.example.com"},
		},
		{
			name:     "different hosts",
			first:    "https://a.example.com/x",
			second:   "https://b.example.com/y",
			same:     false,
			wantKeys: []string{"a.example.com", "b.example.com"},
		},
		{
			name:     "invalid url falls back to raw string",
			first:    "://not a url",
			second:   "://not a url",
			same:     true,
			wantKeys: []string{"://not a url"},
		},
		{
			name:     "empty string key",
			first:    "",
			second:   "",
			same:     true,
			wantKeys: []string{""},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := NewBreakerRegistry(5, time.Minute)
			a := r.Get(tc.first)
			b := r.Get(tc.second)
			if a == nil || b == nil {
				t.Fatalf("Get returned nil breaker")
			}
			if tc.same && a != b {
				t.Fatalf("expected same breaker for %q and %q", tc.first, tc.second)
			}
			if !tc.same && a == b {
				t.Fatalf("expected different breakers for %q and %q", tc.first, tc.second)
			}
			snap := r.Snapshot()
			if len(snap) != len(tc.wantKeys) {
				t.Fatalf("snapshot size = %d, want %d (keys=%v)", len(snap), len(tc.wantKeys), snap)
			}
			for _, k := range tc.wantKeys {
				if _, ok := snap[k]; !ok {
					t.Fatalf("snapshot missing key %q, got %v", k, snap)
				}
			}
		})
	}
}

func TestBreakerRegistryDefaults(t *testing.T) {
	r := NewBreakerRegistry(0, 0)
	if r.failureThreshold != 5 {
		t.Fatalf("failureThreshold = %d, want 5", r.failureThreshold)
	}
	if r.openTimeout != 5*time.Minute {
		t.Fatalf("openTimeout = %v, want 5m", r.openTimeout)
	}
	if r.breakers == nil {
		t.Fatalf("breakers map is nil")
	}
	br := r.Get("https://x.example.com/y")
	if br.failureThreshold != 5 {
		t.Fatalf("breaker failureThreshold = %d, want 5", br.failureThreshold)
	}
	if br.openTimeout != 5*time.Minute {
		t.Fatalf("breaker openTimeout = %v, want 5m", br.openTimeout)
	}
}

func TestBreakerRegistryInvalidAndLongURL(t *testing.T) {
	r := NewBreakerRegistry(2, time.Minute)

	long := "https://example.com/" + strings.Repeat("a", 4096)
	brLong := r.Get(long)
	if brLong == nil {
		t.Fatalf("Get long URL returned nil")
	}
	brLong.AfterRequest(false)
	brLong.AfterRequest(false)
	if brLong.State() != BreakerOpen {
		t.Fatalf("long URL breaker state = %v, want open", brLong.State())
	}

	invalid := "http://[::1"
	brInvalid := r.Get(invalid)
	if brInvalid == nil {
		t.Fatalf("Get invalid URL returned nil")
	}
	brInvalid.AfterRequest(false)
	brInvalid.AfterRequest(false)
	if brInvalid.State() != BreakerOpen {
		t.Fatalf("invalid URL breaker state = %v, want open", brInvalid.State())
	}

	if _, err := url.Parse(invalid); err == nil {
		t.Fatalf("expected url.Parse(%q) to fail, but it succeeded", invalid)
	}
	if _, err := url.Parse(long); err != nil {
		t.Fatalf("expected url.Parse(long) to succeed, got %v", err)
	}

	snap := r.Snapshot()
	if len(snap) != 2 {
		t.Fatalf("snapshot size = %d, want 2 (keys=%v)", len(snap), snap)
	}
	if snap[invalid] != BreakerOpen {
		t.Fatalf("snapshot[%q] = %v, want open", invalid, snap[invalid])
	}
	if snap["example.com"] != BreakerOpen {
		t.Fatalf("snapshot[example.com] = %v, want open", snap["example.com"])
	}
}

func TestCircuitBreakerConcurrentGoroutines(t *testing.T) {
	const goroutines = 64
	const perGoroutine = 100
	cb := NewCircuitBreaker(5, time.Hour)

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			for j := 0; j < perGoroutine; j++ {
				cb.BeforeRequest()
				cb.AfterRequest(true)
			}
		}()
	}
	wg.Wait()

	if cb.State() != BreakerClosed {
		t.Fatalf("state after concurrent successes = %v, want closed", cb.State())
	}
	if cb.failures != 0 {
		t.Fatalf("failures after concurrent successes = %d, want 0", cb.failures)
	}
	if cb.probeInFlight {
		t.Fatalf("probeInFlight = true, want false")
	}
}

func TestCircuitBreakerConcurrentFailureTripsOnce(t *testing.T) {
	const goroutines = 32
	const threshold = 8
	cb := NewCircuitBreaker(threshold, time.Hour)

	var wg sync.WaitGroup
	start := make(chan struct{})
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < 50; j++ {
				if cb.BeforeRequest() {
					cb.AfterRequest(false)
				} else {
					cb.AfterRequest(false)
				}
			}
		}()
	}
	close(start)
	wg.Wait()

	if cb.State() != BreakerOpen {
		t.Fatalf("state after concurrent failures = %v, want open", cb.State())
	}
	if cb.failures < threshold {
		t.Fatalf("failures = %d, want >= %d", cb.failures, threshold)
	}
	if cb.probeInFlight {
		t.Fatalf("probeInFlight = true, want false after open")
	}
}

func TestCircuitBreakerHalfOpenSingleProbeConcurrent(t *testing.T) {
	cb := NewCircuitBreaker(1, 20*time.Millisecond)
	cb.AfterRequest(false)
	if cb.State() != BreakerOpen {
		t.Fatalf("state = %v, want open", cb.State())
	}
	time.Sleep(40 * time.Millisecond)

	const goroutines = 16
	var wg sync.WaitGroup
	allowed := make(chan struct{}, goroutines)
	wg.Add(goroutines)
	start := make(chan struct{})
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			<-start
			if cb.BeforeRequest() {
				allowed <- struct{}{}
			}
		}()
	}
	close(start)
	wg.Wait()
	close(allowed)

	count := 0
	for range allowed {
		count++
	}
	if count != 1 {
		t.Fatalf("half-open allowed %d probes, want exactly 1", count)
	}
	if cb.State() != BreakerHalfOpen {
		t.Fatalf("state = %v, want half-open", cb.State())
	}
	if !cb.probeInFlight {
		t.Fatalf("probeInFlight = false, want true after allowing probe")
	}
}

func TestBreakerRegistryConcurrentGet(t *testing.T) {
	const goroutines = 64
	r := NewBreakerRegistry(3, time.Minute)
	urls := []string{
		"https://a.example.com/x",
		"https://b.example.com/y",
		"https://A.example.com/z",
		"://bad-url",
		"",
	}

	var wg sync.WaitGroup
	results := make([]*CircuitBreaker, goroutines*len(urls))
	wg.Add(goroutines)
	for g := 0; g < goroutines; g++ {
		go func(g int) {
			defer wg.Done()
			for i, u := range urls {
				results[g*len(urls)+i] = r.Get(u)
			}
		}(g)
	}
	wg.Wait()

	first := results[0]
	for i, br := range results {
		if br == nil {
			t.Fatalf("results[%d] is nil", i)
		}
		if br != first {
			t.Fatalf("results[%d] differs from results[0]; registry returned different breakers for same key", i)
		}
	}

	snap := r.Snapshot()
	if len(snap) != 3 {
		t.Fatalf("snapshot size = %d, want 3 (keys=%v)", len(snap), snap)
	}
	for _, k := range []string{"a.example.com", "b.example.com", "://bad-url"} {
		if _, ok := snap[k]; !ok {
			t.Fatalf("snapshot missing key %q, got %v", k, snap)
		}
	}
}

func TestBreakerRegistrySnapshotIsolation(t *testing.T) {
	r := NewBreakerRegistry(1, time.Minute)
	br := r.Get("https://iso.example.com/path")

	snap := r.Snapshot()
	if len(snap) != 1 {
		t.Fatalf("snapshot size = %d, want 1", len(snap))
	}
	if snap["iso.example.com"] != BreakerClosed {
		t.Fatalf("snapshot value = %v, want closed", snap["iso.example.com"])
	}

	br.AfterRequest(false)
	if br.State() != BreakerOpen {
		t.Fatalf("breaker state = %v, want open", br.State())
	}

	snap2 := r.Snapshot()
	if snap2["iso.example.com"] != BreakerOpen {
		t.Fatalf("second snapshot value = %v, want open", snap2["iso.example.com"])
	}
	if snap["iso.example.com"] != BreakerClosed {
		t.Fatalf("first snapshot mutated to %v, want closed (snapshot must be isolated)", snap["iso.example.com"])
	}
}

func TestCircuitBreakerIdempotentProbeAccounting(t *testing.T) {
	cb := NewCircuitBreaker(2, 20*time.Millisecond)
	cb.AfterRequest(false)
	cb.AfterRequest(false)
	if cb.State() != BreakerOpen {
		t.Fatalf("state = %v, want open", cb.State())
	}
	time.Sleep(40 * time.Millisecond)
	if !cb.BeforeRequest() {
		t.Fatalf("first probe = false, want true")
	}
	if cb.BeforeRequest() {
		t.Fatalf("second probe = true, want false")
	}
	if cb.BeforeRequest() {
		t.Fatalf("third probe = true, want false")
	}
	if cb.State() != BreakerHalfOpen {
		t.Fatalf("state = %v, want half-open", cb.State())
	}
	cb.AfterRequest(true)
	if cb.State() != BreakerClosed {
		t.Fatalf("state after probe success = %v, want closed", cb.State())
	}
	if cb.failures != 0 {
		t.Fatalf("failures = %d, want 0", cb.failures)
	}
	if cb.probeInFlight {
		t.Fatalf("probeInFlight = true, want false")
	}
	if !cb.BeforeRequest() {
		t.Fatalf("BeforeRequest after recovery = false, want true")
	}
}