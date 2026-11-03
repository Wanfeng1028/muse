package handler

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksEnabledFilterHTTP(t *testing.T) {
	st, h := newDeep3Router(t)

	mkLinkDeep3(t, st, &model.Link{Slug: "en1", URL: "https://en1.com", Enabled: true})
	mkLinkDeep3(t, st, &model.Link{Slug: "dis1", URL: "https://dis1.com", Enabled: false})

	t.Run("enabled_true", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?enabled=true", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("want 200 got %d", rec.Code)
		}
		var body map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if body["total"].(float64) != 1 {
			t.Fatalf("want total=1 got %v", body["total"])
		}
		items := body["items"].([]any)
		if len(items) != 1 {
			t.Fatalf("want 1 item got %d", len(items))
		}
		slug := items[0].(map[string]any)["slug"].(string)
		if slug != "en1" {
			t.Fatalf("want slug en1 got %s", slug)
		}
	})

	t.Run("enabled_false", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?enabled=false", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("want 200 got %d", rec.Code)
		}
		var body map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if body["total"].(float64) != 1 {
			t.Fatalf("want total=1 got %v", body["total"])
		}
		items := body["items"].([]any)
		if len(items) != 1 {
			t.Fatalf("want 1 item got %d", len(items))
		}
		slug := items[0].(map[string]any)["slug"].(string)
		if slug != "dis1" {
			t.Fatalf("want slug dis1 got %s", slug)
		}
	})

	t.Run("enabled_maybe", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?enabled=maybe", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("want 400 got %d", rec.Code)
		}
	})

	t.Run("no_enabled", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("want 200 got %d", rec.Code)
		}
		var body map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if body["total"].(float64) != 2 {
			t.Fatalf("want total=2 got %v", body["total"])
		}
		items := body["items"].([]any)
		if len(items) != 2 {
			t.Fatalf("want 2 items got %d", len(items))
		}
		slugs := map[string]bool{}
		for _, item := range items {
			slug := item.(map[string]any)["slug"].(string)
			slugs[slug] = true
		}
		if !slugs["en1"] {
			t.Fatal("missing en1 in items")
		}
		if !slugs["dis1"] {
			t.Fatal("missing dis1 in items")
		}
	})
}
