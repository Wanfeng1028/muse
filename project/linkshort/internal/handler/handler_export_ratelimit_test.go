package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func exportGet(t *testing.T, ts *httptest.Server, path string) *http.Response {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, ts.URL+path, nil)
	if err != nil {
		t.Fatalf("building request: %v", err)
	}
	req.Header.Set("X-API-Key", "test-admin-key")
	resp, err := ts.Client().Do(req)
	if err != nil {
		t.Fatalf("making request: %v", err)
	}
	return resp
}

func newExportTestServer(t *testing.T, perMinute int, globalEnabled bool) *httptest.Server {
	t.Helper()
	st := newTestStore(t)
	cfg := newTestConfig(t)
	cfg.RateLimitEnabled = globalEnabled
	cfg.RateLimitRPS = 1000
	cfg.RateLimitBurst = 1000
	cfg.ExportRateLimitPerMinute = perMinute
	r := NewRouter(st, cfg)
	srv := httptest.NewServer(r)
	t.Cleanup(srv.Close)
	return srv
}

func TestExportRateLimitBlocksThirdRequest(t *testing.T) {
	ts := newExportTestServer(t, 2, true)

	resp1 := exportGet(t, ts, "/api/export.csv")
	if resp1.StatusCode != http.StatusOK {
		t.Fatalf("first request: got %d, want 200", resp1.StatusCode)
	}
	resp1.Body.Close()

	resp2 := exportGet(t, ts, "/api/export.csv")
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("second request: got %d, want 200", resp2.StatusCode)
	}
	resp2.Body.Close()

	resp3 := exportGet(t, ts, "/api/export.csv")
	if resp3.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("third request: got %d, want 429", resp3.StatusCode)
	}
	defer resp3.Body.Close()

	ra := resp3.Header.Get("Retry-After")
	if ra != "30" {
		t.Errorf("Retry-After: got %q, want %q", ra, "30")
	}

	var body map[string]any
	if err := json.NewDecoder(resp3.Body).Decode(&body); err != nil {
		t.Fatalf("decode 429 body: %v", err)
	}
	if errMsg, _ := body["error"].(string); errMsg != "rate limit exceeded" {
		t.Errorf("error message: got %q, want %q", errMsg, "rate limit exceeded")
	}
}

func TestExportGeoCSVSharesExportBucket(t *testing.T) {
	ts := newExportTestServer(t, 2, true)

	resp1 := exportGet(t, ts, "/api/export.csv")
	if resp1.StatusCode != http.StatusOK {
		t.Fatalf("first export.csv: got %d, want 200", resp1.StatusCode)
	}
	resp1.Body.Close()

	resp2 := exportGet(t, ts, "/api/export.csv")
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("second export.csv: got %d, want 200", resp2.StatusCode)
	}
	resp2.Body.Close()

	resp3 := exportGet(t, ts, "/api/stats/geo.csv")
	if resp3.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("geo.csv after bucket drained: got %d, want 429", resp3.StatusCode)
	}
	resp3.Body.Close()
}

func TestExportRateLimitDisabledWhenZero(t *testing.T) {
	ts := newExportTestServer(t, 0, true)

	for i := 1; i <= 3; i++ {
		resp := exportGet(t, ts, "/api/export.csv")
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("request %d: got %d, want 200", i, resp.StatusCode)
		}
		resp.Body.Close()
	}
}

func TestExportRateLimitDisabledWhenGlobalOff(t *testing.T) {
	ts := newExportTestServer(t, 1, false)

	for i := 1; i <= 3; i++ {
		resp := exportGet(t, ts, "/api/export.csv")
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("request %d: got %d, want 200", i, resp.StatusCode)
		}
		resp.Body.Close()
	}
}

func TestExportRateLimitDoesNotBlockOtherEndpoints(t *testing.T) {
	ts := newExportTestServer(t, 1, true)

	resp1 := exportGet(t, ts, "/api/export.csv")
	if resp1.StatusCode != http.StatusOK {
		t.Fatalf("export.csv: got %d, want 200", resp1.StatusCode)
	}
	resp1.Body.Close()

	resp2 := exportGet(t, ts, "/api/links")
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("links: got %d, want 200", resp2.StatusCode)
	}
	resp2.Body.Close()

	resp3 := exportGet(t, ts, "/api/meta")
	if resp3.StatusCode != http.StatusOK {
		t.Fatalf("meta: got %d, want 200", resp3.StatusCode)
	}
	resp3.Body.Close()
}

func TestMetaReportsExportRateLimit(t *testing.T) {
	ts := newExportTestServer(t, 7, true)

	resp := exportGet(t, ts, "/api/meta")
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("meta: got %d, want 200", resp.StatusCode)
	}
	defer resp.Body.Close()

	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode meta body: %v", err)
	}

	val, ok := body["export_rate_limit_per_minute"]
	if !ok {
		t.Fatal("missing field export_rate_limit_per_minute")
	}
	if val != float64(7) {
		t.Errorf("export_rate_limit_per_minute: got %v, want %v", val, float64(7))
	}
}
