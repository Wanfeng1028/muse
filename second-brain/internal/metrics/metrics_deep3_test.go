package metrics

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestEscapeLabelValue_AllThreeKinds(t *testing.T) {
	reg := New()
	reg.IncHTTPRequest("GET", "a\\b\"c\nd", 200)
	body := renderBody(t, reg)
	want := `route="a\\b\"c\nd"`
	if !strings.Contains(body, want) {
		t.Fatalf("expected body to contain %q, got:\n%s", want, body)
	}
}

func TestPushSent_ChannelEscaped(t *testing.T) {
	reg := New()
	reg.IncPushSent("we\"ird", "sent")
	body := renderBody(t, reg)
	want := `push_sent_total{channel="we\"ird",status="sent"} 1`
	if !strings.Contains(body, want) {
		t.Fatalf("expected body to contain %q, got:\n%s", want, body)
	}
}

func TestGaugeVec_MultiUserSortedAndEscaped(t *testing.T) {
	reg := New()
	reg.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		return map[string]float64{"bob": 2, "alice": 5, "a\"b": 1}
	})
	body := renderBody(t, reg)

	first := `{user="a\"b"} 1`
	second := `{user="alice"} 5`
	third := `{user="bob"} 2`

	i1 := strings.Index(body, first)
	i2 := strings.Index(body, second)
	i3 := strings.Index(body, third)

	if i1 < 0 {
		t.Fatalf("expected body to contain %q, got:\n%s", first, body)
	}
	if i2 < 0 {
		t.Fatalf("expected body to contain %q, got:\n%s", second, body)
	}
	if i3 < 0 {
		t.Fatalf("expected body to contain %q, got:\n%s", third, body)
	}
	if !(i1 < i2 && i2 < i3) {
		t.Fatalf("expected order a\\\"b < alice < bob, got indexes %d, %d, %d in:\n%s", i1, i2, i3, body)
	}
}

func TestGaugeVec_PanicFn_NoSamples(t *testing.T) {
	reg := New()
	reg.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		panic("boom")
	})
	body := renderBody(t, reg)
	if !strings.Contains(body, "# TYPE reviews_due_by_user") {
		t.Fatalf("expected TYPE header for reviews_due_by_user, got:\n%s", body)
	}
	if strings.Contains(body, "reviews_due_by_user{") {
		t.Fatalf("expected no sample lines for reviews_due_by_user, got:\n%s", body)
	}
}

func TestGauge_Panic_NaN(t *testing.T) {
	reg := New()
	reg.SetGaugeFunc("notes_total", func() float64 {
		panic("boom")
	})
	body := renderBody(t, reg)
	want := "notes_total NaN"
	if !strings.Contains(body, want) {
		t.Fatalf("expected body to contain %q, got:\n%s", want, body)
	}
}

func TestGauge_UnknownName_Ignored(t *testing.T) {
	reg := New()
	reg.SetGaugeFunc("bogus_metric", func() float64 { return 1 })
	body := renderBody(t, reg)
	if strings.Contains(body, "bogus_metric") {
		t.Fatalf("expected body NOT to contain bogus_metric, got:\n%s", body)
	}
}

func TestGauge_NilFn_Deletes(t *testing.T) {
	reg := New()
	reg.SetGaugeFunc("notes_total", func() float64 { return 42 })
	body1 := renderBody(t, reg)
	if !strings.Contains(body1, "notes_total 42") {
		t.Fatalf("expected body1 to contain notes_total 42, got:\n%s", body1)
	}
	reg.SetGaugeFunc("notes_total", nil)
	body2 := renderBody(t, reg)
	if strings.Contains(body2, "notes_total ") {
		t.Fatalf("expected body2 NOT to contain notes_total sample, got:\n%s", body2)
	}
}

func TestHistogram_CumulativeBucketsExact(t *testing.T) {
	reg := New()
	reg.ObserveHTTPDuration("GET", "/x", 0.03)
	body := renderBody(t, reg)

	cases := []string{
		`http_request_duration_seconds_bucket{method="GET",route="/x",le="0.025"} 0`,
		`http_request_duration_seconds_bucket{method="GET",route="/x",le="0.05"} 1`,
		`http_request_duration_seconds_bucket{method="GET",route="/x",le="+Inf"} 1`,
		`http_request_duration_seconds_count{method="GET",route="/x"} 1`,
		`http_request_duration_seconds_sum{method="GET",route="/x"} 0.03`,
	}
	for _, want := range cases {
		if !strings.Contains(body, want) {
			t.Fatalf("expected body to contain %q, got:\n%s", want, body)
		}
	}
}

func TestMiddleware_SkipsMetricsPath(t *testing.T) {
	reg := New()
	mw := reg.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	req := httptest.NewRequest("GET", "/metrics", nil)
	rec := httptest.NewRecorder()
	mw.ServeHTTP(rec, req)
	body := renderBody(t, reg)
	if strings.Contains(body, "http_requests_total{") {
		t.Fatalf("expected /metrics to not be recorded, got:\n%s", body)
	}
}

func TestMiddleware_RouteFromPatternField(t *testing.T) {
	reg := New()
	mw := reg.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r.Pattern = "GET /api/notes/{id}"
	}))
	req := httptest.NewRequest("GET", "/api/notes/42", nil)
	rec := httptest.NewRecorder()
	mw.ServeHTTP(rec, req)
	body := renderBody(t, reg)

	want := `route="/api/notes/{id}"`
	if !strings.Contains(body, want) {
		t.Fatalf("expected body to contain %q, got:\n%s", want, body)
	}
	if strings.Contains(body, `route="/api/notes/42"`) {
		t.Fatalf("expected numeric route not present, got:\n%s", body)
	}
}

func TestReviewGraded_NumericSortOrder(t *testing.T) {
	reg := New()
	reg.IncReviewGraded(10)
	reg.IncReviewGraded(3)
	reg.IncReviewGraded(5)
	body := renderBody(t, reg)

	i3 := strings.Index(body, `grade="3"`)
	i5 := strings.Index(body, `grade="5"`)
	i10 := strings.Index(body, `grade="10"`)

	if i3 < 0 || i5 < 0 || i10 < 0 {
		t.Fatalf("expected all grades present, got indexes %d %d %d in:\n%s", i3, i5, i10, body)
	}
	if !(i3 < i5 && i5 < i10) {
		t.Fatalf("expected numeric order 3 < 5 < 10, got indexes %d, %d, %d in:\n%s", i3, i5, i10, body)
	}
}

func TestIncPushSent_CountsExact(t *testing.T) {
	reg := New()
	reg.IncPushSent("smtp", "sent")
	reg.IncPushSent("smtp", "sent")
	reg.IncPushSent("smtp", "failed")
	body := renderBody(t, reg)

	sentLine := `push_sent_total{channel="smtp",status="sent"} 2`
	failedLine := `push_sent_total{channel="smtp",status="failed"} 1`
	if !strings.Contains(body, sentLine) {
		t.Fatalf("expected body to contain %q, got:\n%s", sentLine, body)
	}
	if !strings.Contains(body, failedLine) {
		t.Fatalf("expected body to contain %q, got:\n%s", failedLine, body)
	}
}

func TestRender_StableAcrossCalls(t *testing.T) {
	reg := New()
	reg.IncHTTPRequest("GET", "/a", 200)
	reg.IncHTTPRequest("POST", "/b", 500)
	reg.ObserveHTTPDuration("GET", "/a", 0.012)
	reg.ObserveHTTPDuration("POST", "/b", 1.5)
	reg.IncPushSent("smtp", "sent")
	reg.IncReviewGraded(4)
	reg.SetGaugeFunc("notes_total", func() float64 { return 7 })
	reg.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		return map[string]float64{"bob": 2, "alice": 5}
	})

	body1 := renderBody(t, reg)
	body2 := renderBody(t, reg)

	if body1 != body2 {
		t.Fatalf("expected stable exposition across calls.\nfirst:\n%s\nsecond:\n%s", body1, body2)
	}
}
