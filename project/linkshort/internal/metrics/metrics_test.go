package metrics

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/go-chi/chi/v5"
)

func TestRegistryMiddlewareCountsRequests(t *testing.T) {
	reg := NewRegistry()
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	})
	h := reg.Middleware(next)

	req := httptest.NewRequest(http.MethodGet, "/api/links", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusCreated)
	}

	out := scrape(t, reg)
	want := `linkshort_http_requests_total{method="GET",route="unknown",status="201"} 1`
	if !strings.Contains(out, want) {
		t.Fatalf("metrics output missing %q\noutput:\n%s", want, out)
	}
}

func TestRegistryRoutePattern(t *testing.T) {
	reg := NewRegistry()
	r := chi.NewRouter()
	r.Use(reg.Middleware)
	r.Get("/items/{id}", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/items/42", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	out := scrape(t, reg)
	if !strings.Contains(out, `route="/items/{id}"`) {
		t.Fatalf("metrics output missing route pattern label\noutput:\n%s", out)
	}
	if strings.Contains(out, `route="/items/42"`) {
		t.Fatalf("metrics output contains high-cardinality route label\noutput:\n%s", out)
	}
}

func TestIncRedirectAndBurned(t *testing.T) {
	reg := NewRegistry()
	reg.IncRedirect("ok")
	reg.IncRedirect("ok")
	reg.IncRedirect("gone")
	reg.IncBurned()

	out := scrape(t, reg)
	wants := []string{
		`linkshort_redirects_total{outcome="ok"} 2`,
		`linkshort_redirects_total{outcome="gone"} 1`,
		`linkshort_burn_links_burned_total 1`,
	}
	for _, want := range wants {
		if !strings.Contains(out, want) {
			t.Fatalf("metrics output missing %q\noutput:\n%s", want, out)
		}
	}
}

func TestHandlerContentType(t *testing.T) {
	reg := NewRegistry()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rec := httptest.NewRecorder()
	reg.Handler()(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	ct := rec.Header().Get("Content-Type")
	if ct != "text/plain; version=0.0.4" {
		t.Fatalf("Content-Type = %q, want %q", ct, "text/plain; version=0.0.4")
	}
	body := rec.Body.String()
	if !strings.Contains(body, "# HELP") {
		t.Fatalf("output missing # HELP line\noutput:\n%s", body)
	}
	if !strings.Contains(body, "# TYPE") {
		t.Fatalf("output missing # TYPE line\noutput:\n%s", body)
	}
}

func TestConcurrentIncrements(t *testing.T) {
	reg := NewRegistry()
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				reg.IncRedirect("ok")
			}
		}()
	}
	wg.Wait()

	out := scrape(t, reg)
	want := `linkshort_redirects_total{outcome="ok"} 10000`
	if !strings.Contains(out, want) {
		t.Fatalf("metrics output missing %q\noutput:\n%s", want, out)
	}
}

func scrape(t *testing.T, reg *Registry) string {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rec := httptest.NewRecorder()
	reg.Handler()(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("scrape status = %d, want %d", rec.Code, http.StatusOK)
	}
	return rec.Body.String()
}
