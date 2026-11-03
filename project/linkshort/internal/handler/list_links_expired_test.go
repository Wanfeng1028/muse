package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksExpiredFilterHTTP(t *testing.T) {
	st, h := newDeep3Router(t)

	past := time.Now().Add(-time.Hour)
	future := time.Now().Add(time.Hour)

	links := []model.Link{
		{Slug: "exp-en", URL: "https://exp-en.com", ExpiresAt: &past, Enabled: true},
		{Slug: "exp-dis", URL: "https://exp-dis.com", ExpiresAt: &past, Enabled: false},
		{Slug: "unexp-en", URL: "https://unexp-en.com", ExpiresAt: &future, Enabled: true},
		{Slug: "never-en", URL: "https://never-en.com", ExpiresAt: nil, Enabled: true},
	}
	for _, l := range links {
		mkLinkDeep3(t, st, &l)
	}

	t.Run("expired_true", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?expired=true", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}
		total, ok := body["total"].(float64)
		if !ok {
			t.Fatalf("total missing or not float64")
		}
		if total != 2 {
			t.Fatalf("expected total 2, got %v", total)
		}
	})

	t.Run("expired_false", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?expired=false", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}
		total, ok := body["total"].(float64)
		if !ok {
			t.Fatalf("total missing")
		}
		if total != 2 {
			t.Fatalf("expected total 2, got %v", total)
		}
	})

	t.Run("expired_maybe", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?expired=maybe", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "expired") {
			t.Fatalf("expected response body to contain expired, got %s", rec.Body.String())
		}
	})

	t.Run("expired_enabled_combo", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?expired=true&enabled=false", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}
		total, ok := body["total"].(float64)
		if !ok {
			t.Fatalf("total missing")
		}
		if total != 1 {
			t.Fatalf("expected total 1, got %v", total)
		}
		items, ok := body["items"].([]any)
		if !ok {
			t.Fatalf("items missing or not slice")
		}
		if len(items) != 1 {
			t.Fatalf("expected items length 1, got %d", len(items))
		}
		slugMap, ok := items[0].(map[string]any)
		if !ok {
			t.Fatalf("item not map")
		}
		slug, ok := slugMap["slug"].(string)
		if !ok {
			t.Fatalf("slug missing or not string")
		}
		if slug != "exp-dis" {
			t.Fatalf("expected slug exp-dis, got %s", slug)
		}
	})

	t.Run("no_expired", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}
		total, ok := body["total"].(float64)
		if !ok {
			t.Fatalf("total missing")
		}
		if total != 4 {
			t.Fatalf("expected total 4, got %v", total)
		}
	})
}
