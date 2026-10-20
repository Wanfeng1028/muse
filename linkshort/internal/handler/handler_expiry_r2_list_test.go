package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_ExpiredStillListed(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2el1", URL: "https://example.com/l1", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items missing or wrong type: %v", body["items"])
	}
	found := false
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if s, _ := m["slug"].(string); s == "b2el1" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expired link b2el1 not found in items: %v", items)
	}
}

func TestExpiryR2_ExpiredSearchable(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2el1", URL: "https://example.com/l1", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodGet, "/api/links?search=b2el1", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "b2el1") {
		t.Fatalf("expected body to contain b2el1, got %s", rec.Body.String())
	}
}

func TestExpiryR2_ListShowsExpiresAt(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2el1", URL: "https://example.com/l1", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items missing or wrong type: %v", body["items"])
	}
	var target map[string]any
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if s, _ := m["slug"].(string); s == "b2el1" {
			target = m
			break
		}
	}
	if target == nil {
		t.Fatalf("expired link b2el1 not found in items: %v", items)
	}
	exp, ok := target["expires_at"].(string)
	if !ok || exp == "" {
		t.Fatalf("expires_at missing or not non-empty string: %v", target["expires_at"])
	}
	if _, err := time.Parse(time.RFC3339, exp); err != nil {
		t.Fatalf("expires_at not RFC3339: %v (%q)", err, exp)
	}
}

func TestExpiryR2_TotalCountsExpired(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2el1", URL: "https://example.com/l1", Enabled: true, ExpiresAt: &past})
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ok1", URL: "https://example.com/l2", Enabled: true})
	rec := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	total, ok := body["total"].(float64)
	if !ok {
		t.Fatalf("total missing or wrong type: %v", body["total"])
	}
	if total < 2 {
		t.Fatalf("expected total >= 2, got %v", total)
	}
}
