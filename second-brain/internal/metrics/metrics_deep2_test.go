package metrics

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestNormalizePath_Deep2(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"", "/"},
		{"/", "/"},
		{"/api/notes/42", "/api/notes/{id}"},
		{"/a/1/b/22", "/a/{id}/b/{id}"},
		{"/api/notes/abc", "/api/notes/abc"},
		{"/api/notes/12x", "/api/notes/12x"},
		{"/api/notes/007", "/api/notes/{id}"},
	}
	for _, c := range cases {
		if got := normalizePath(c.in); got != c.want {
			t.Errorf("normalizePath(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestIsAllDigits_Deep2(t *testing.T) {
	cases := []struct {
		in   string
		want bool
	}{
		{"", false},
		{"0", true},
		{"123", true},
		{"12a", false},
		{" 12", false},
		{"１２３", false},
	}
	for _, c := range cases {
		if got := isAllDigits(c.in); got != c.want {
			t.Errorf("isAllDigits(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestRouteFromRequest_Deep2(t *testing.T) {
	req1 := httptest.NewRequest(http.MethodGet, "/api/notes/5", nil)
	req1.Pattern = "GET /api/notes/{id}"
	if got := routeFromRequest(req1); got != "/api/notes/{id}" {
		t.Errorf("routeFromRequest with Pattern method prefix = %q, want %q", got, "/api/notes/{id}")
	}

	req2 := httptest.NewRequest(http.MethodGet, "/plain", nil)
	req2.Pattern = "/plain"
	if got := routeFromRequest(req2); got != "/plain" {
		t.Errorf("routeFromRequest with Pattern no space = %q, want %q", got, "/plain")
	}

	req3 := httptest.NewRequest(http.MethodGet, "/api/x/7", nil)
	if got := routeFromRequest(req3); got != "/api/x/{id}" {
		t.Errorf("routeFromRequest fallback = %q, want %q", got, "/api/x/{id}")
	}
}

func TestStatusRecorder_Deep2(t *testing.T) {
	base := httptest.NewRecorder()
	sr := &statusRecorder{ResponseWriter: base}
	sr.WriteHeader(404)
	sr.WriteHeader(200)
	if sr.status != 404 {
		t.Errorf("statusRecorder status after two WriteHeader = %d, want 404", sr.status)
	}
	if !sr.wroteHeader {
		t.Errorf("statusRecorder wroteHeader = false, want true")
	}

	base2 := httptest.NewRecorder()
	sr2 := &statusRecorder{ResponseWriter: base2}
	if _, err := sr2.Write([]byte("x")); err != nil {
		t.Fatalf("statusRecorder Write error: %v", err)
	}
	if sr2.status != 200 {
		t.Errorf("statusRecorder status after Write = %d, want 200", sr2.status)
	}
	if !sr2.wroteHeader {
		t.Errorf("statusRecorder wroteHeader after Write = false, want true")
	}
}

func TestMiddleware_RecordsDurationCount_Deep2(t *testing.T) {
	reg := New()
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := reg.Middleware(next)

	for i := 0; i < 3; i++ {
		req := httptest.NewRequest(http.MethodGet, "/api/ping", nil)
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
	}

	rec := httptest.NewRecorder()
	reg.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	body := rec.Body.String()

	wantCount := `http_request_duration_seconds_count{method="GET",route="/api/ping"} 3`
	if !strings.Contains(body, wantCount) {
		t.Errorf("output missing %q\nbody:\n%s", wantCount, body)
	}
	wantReq := `http_requests_total{method="GET",route="/api/ping",status="200"} 3`
	if !strings.Contains(body, wantReq) {
		t.Errorf("output missing %q\nbody:\n%s", wantReq, body)
	}
}

func TestGauge_Order_Deep2(t *testing.T) {
	reg := New()
	reg.SetGaugeFunc("reviews_due", func() float64 { return 7 })
	reg.SetGaugeFunc("notes_total", func() float64 { return 42 })

	rec := httptest.NewRecorder()
	reg.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	body := rec.Body.String()

	lines := strings.Split(body, "\n")
	notesLine := -1
	reviewsLine := -1
	for i, ln := range lines {
		if strings.HasPrefix(ln, "notes_total ") {
			notesLine = i
		}
		if strings.HasPrefix(ln, "reviews_due ") {
			reviewsLine = i
		}
	}
	if notesLine == -1 {
		t.Fatalf("notes_total sample line not found\nbody:\n%s", body)
	}
	if reviewsLine == -1 {
		t.Fatalf("reviews_due sample line not found\nbody:\n%s", body)
	}
	if notesLine >= reviewsLine {
		t.Errorf("expected notes_total line (%d) before reviews_due line (%d)\nbody:\n%s", notesLine, reviewsLine, body)
	}
}

func TestHistogram_ExactLeLabels_Deep2(t *testing.T) {
	reg := New()
	reg.ObserveHTTPDuration("GET", "/x", 0.1)

	rec := httptest.NewRecorder()
	reg.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	body := rec.Body.String()

	wantBucket := `http_request_duration_seconds_bucket{method="GET",route="/x",le="0.1"} 1`
	if !strings.Contains(body, wantBucket) {
		t.Errorf("output missing %q\nbody:\n%s", wantBucket, body)
	}
	wantInf := `http_request_duration_seconds_bucket{method="GET",route="/x",le="+Inf"} 1`
	if !strings.Contains(body, wantInf) {
		t.Errorf("output missing %q\nbody:\n%s", wantInf, body)
	}
}

func TestLabelEscaping_Newline_Deep2(t *testing.T) {
	reg := New()
	reg.IncHTTPRequest("GET", "/a\nb", 200)

	rec := httptest.NewRecorder()
	reg.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	body := rec.Body.String()

	want := `route="/a\nb"`
	if !strings.Contains(body, want) {
		t.Errorf("output missing escaped label %q\nbody:\n%s", want, body)
	}
	for _, ln := range strings.Split(body, "\n") {
		if strings.Contains(ln, "route=\"/a") && !strings.Contains(ln, `route="/a\nb"`) {
			t.Errorf("label value was split across raw newline: %q", ln)
		}
	}
}

func TestDefault_Singleton_Deep2(t *testing.T) {
	a := Default()
	b := Default()
	if a != b {
		t.Errorf("Default() returned different instances: %p vs %p", a, b)
	}
}

func TestIncReviewGraded_NegativeGrade_Deep2(t *testing.T) {
	reg := New()
	reg.IncReviewGraded(-1)

	rec := httptest.NewRecorder()
	reg.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	body := rec.Body.String()

	want := `reviews_graded_total{grade="-1"} 1`
	if !strings.Contains(body, want) {
		t.Errorf("output missing %q\nbody:\n%s", want, body)
	}
}
