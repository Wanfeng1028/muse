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
