package handler

import (
	"encoding/json"
	"testing"
)

func TestStatsGeoEmpty(t *testing.T) {
	srv := newTestServer(t)
	resp, data := doJSON(t, "GET", srv.URL+"/api/stats/geo", testKey, nil)
	if resp.StatusCode != 200 {
		t.Fatalf("want 200, got %d", resp.StatusCode)
	}
	var body map[string]any
	if err := json.Unmarshal(data, &body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items not array: %T", body["items"])
	}
	if len(items) != 0 {
		t.Fatalf("want empty items, got %d", len(items))
	}
	pct, ok := body["unknown_pct"].(float64)
	if !ok {
		t.Fatalf("unknown_pct not number: %T", body["unknown_pct"])
	}
	if pct != 0 {
		t.Fatalf("want 0, got %v", pct)
	}
}

func TestStatsGeoBadN(t *testing.T) {
	srv := newTestServer(t)
	resp, _ := doJSON(t, "GET", srv.URL+"/api/stats/geo?n=999", testKey, nil)
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("want 200, got %d", resp.StatusCode)
	}
}

func TestStatsGeoDaysFallback(t *testing.T) {
	srv := newTestServer(t)
	respBad, dataBad := doJSON(t, "GET", srv.URL+"/api/stats/geo?days=abc", testKey, nil)
	defer respBad.Body.Close()
	if respBad.StatusCode != 200 {
		t.Fatalf("days=abc want 200, got %d", respBad.StatusCode)
	}
	var bodyBad map[string]any
	if err := json.Unmarshal(dataBad, &bodyBad); err != nil {
		t.Fatalf("decode days=abc: %v", err)
	}
	if d, ok := bodyBad["days"].(float64); !ok || int(d) != 30 {
		t.Fatalf("days=abc want body days=30, got %v", bodyBad["days"])
	}
	resp7, data7 := doJSON(t, "GET", srv.URL+"/api/stats/geo?days=7", testKey, nil)
	defer resp7.Body.Close()
	if resp7.StatusCode != 200 {
		t.Fatalf("days=7 want 200, got %d", resp7.StatusCode)
	}
	var body7 map[string]any
	if err := json.Unmarshal(data7, &body7); err != nil {
		t.Fatalf("decode days=7: %v", err)
	}
	if d, ok := body7["days"].(float64); !ok || int(d) != 7 {
		t.Fatalf("days=7 want body days=7, got %v", body7["days"])
	}
}
