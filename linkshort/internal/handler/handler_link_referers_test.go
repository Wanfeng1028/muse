package handler

import (
	"encoding/json"
	"net/http"
	"testing"
)

// TestHandleLinkReferersOK 验证合法请求返回 {"items":[{"name","clicks"}]} 形状。
func TestHandleLinkReferersOK(t *testing.T) {
	srv := newTestServer(t)
	cfg := newTestConfig(t)
	cfg.AdminKey = testKey

	created := createLink(t, srv, cfg, map[string]any{
		"url": "https://example.com/referers-ok",
	})

	resp, data := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+itoa(int64(created["id"].(float64)))+"/referers?n=8", testKey, nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", resp.StatusCode, string(data))
	}

	var body struct {
		Items []struct {
			Name   string `json:"name"`
			Clicks int64  `json:"clicks"`
		} `json:"items"`
	}
	if err := json.Unmarshal(data, &body); err != nil {
		t.Fatalf("decode body: %v; raw=%s", err, string(data))
	}
	if body.Items == nil {
		t.Fatalf("expected items array present, got nil; raw=%s", string(data))
	}
	if len(body.Items) != 0 {
		t.Fatalf("expected empty items for new link, got %+v", body.Items)
	}
}

// TestHandleLinkReferersInvalidID 验证非法 id 返回 400。
func TestHandleLinkReferersInvalidID(t *testing.T) {
	srv := newTestServer(t)

	resp, data := doJSON(t, http.MethodGet, srv.URL+"/api/links/not-a-number/referers", testKey, nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", resp.StatusCode, string(data))
	}
}

// TestHandleLinkReferersNoVisits 验证无访问时返回 items 为空数组。
func TestHandleLinkReferersNoVisits(t *testing.T) {
	srv := newTestServer(t)
	cfg := newTestConfig(t)
	cfg.AdminKey = testKey

	created := createLink(t, srv, cfg, map[string]any{
		"url": "https://example.com/referers-novisits",
	})

	resp, data := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+itoa(int64(created["id"].(float64)))+"/referers", testKey, nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", resp.StatusCode, string(data))
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("decode body: %v; raw=%s", err, string(data))
	}
	itemsRaw, ok := raw["items"]
	if !ok {
		t.Fatalf("expected items key present; raw=%s", string(data))
	}
	if string(itemsRaw) != "[]" {
		t.Fatalf("expected empty items array, got %s", string(itemsRaw))
	}
}
