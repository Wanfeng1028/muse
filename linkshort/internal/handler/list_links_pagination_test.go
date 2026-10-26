package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksPaginationValidationHTTP(t *testing.T) {
	st, h := newDeep3Router(t)

	seeds := []model.Link{
		{Slug: "pg1", URL: "https://pg1.com", Enabled: true},
		{Slug: "pg2", URL: "https://pg2.com", Enabled: true},
		{Slug: "pg3", URL: "https://pg3.com", Enabled: true},
	}
	for i := range seeds {
		l := seeds[i]
		mkLinkDeep3(t, st, &l)
	}

	t.Run("page_zero", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?page=0", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "page") {
			t.Fatalf("expected body to contain %q, got %q", "page", rec.Body.String())
		}
	})

	t.Run("page_abc", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?page=abc", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "page") {
			t.Fatalf("expected body to contain %q, got %q", "page", rec.Body.String())
		}
	})

	t.Run("page_negative", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?page=-1", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "page") {
			t.Fatalf("expected body to contain %q, got %q", "page", rec.Body.String())
		}
	})

	t.Run("per_page_zero", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?per_page=0", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "per_page") {
			t.Fatalf("expected body to contain %q, got %q", "per_page", rec.Body.String())
		}
	})

	t.Run("per_page_over", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?per_page=201", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "per_page") {
			t.Fatalf("expected body to contain %q, got %q", "per_page", rec.Body.String())
		}
	})

	t.Run("per_page_abc", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?per_page=abc", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "per_page") {
			t.Fatalf("expected body to contain %q, got %q", "per_page", rec.Body.String())
		}
	})

	t.Run("valid_pagination", func(t *testing.T) {
		rec1 := doDeep3(t, h, http.MethodGet, "/api/links?page=1&per_page=2", nil, "")
		if rec1.Code != http.StatusOK {
			t.Fatalf("page=1: expected status 200, got %d", rec1.Code)
		}
		var body1 map[string]any
		if err := json.NewDecoder(rec1.Body).Decode(&body1); err != nil {
			t.Fatalf("page=1: failed to decode body: %v", err)
		}
		total1, ok := body1["total"].(float64)
		if !ok {
			t.Fatalf("page=1: expected total to be number, got %#v", body1["total"])
		}
		if total1 != 3 {
			t.Fatalf("page=1: expected total 3, got %v", total1)
		}
		items1, ok := body1["items"].([]any)
		if !ok {
			t.Fatalf("page=1: expected items to be array, got %#v", body1["items"])
		}
		if len(items1) != 2 {
			t.Fatalf("page=1: expected 2 items, got %d", len(items1))
		}
		slugs1 := make(map[string]bool, len(items1))
		for _, it := range items1 {
			m, ok := it.(map[string]any)
			if !ok {
				t.Fatalf("page=1: expected item to be object, got %#v", it)
			}
			s, ok := m["slug"].(string)
			if !ok {
				t.Fatalf("page=1: expected slug to be string, got %#v", m["slug"])
			}
			slugs1[s] = true
		}

		rec2 := doDeep3(t, h, http.MethodGet, "/api/links?page=2&per_page=2", nil, "")
		if rec2.Code != http.StatusOK {
			t.Fatalf("page=2: expected status 200, got %d", rec2.Code)
		}
		var body2 map[string]any
		if err := json.NewDecoder(rec2.Body).Decode(&body2); err != nil {
			t.Fatalf("page=2: failed to decode body: %v", err)
		}
		total2, ok := body2["total"].(float64)
		if !ok {
			t.Fatalf("page=2: expected total to be number, got %#v", body2["total"])
		}
		if total2 != 3 {
			t.Fatalf("page=2: expected total 3, got %v", total2)
		}
		items2, ok := body2["items"].([]any)
		if !ok {
			t.Fatalf("page=2: expected items to be array, got %#v", body2["items"])
		}
		if len(items2) != 1 {
			t.Fatalf("page=2: expected 1 item, got %d", len(items2))
		}
		slugs2 := make(map[string]bool, len(items2))
		for _, it := range items2 {
			m, ok := it.(map[string]any)
			if !ok {
				t.Fatalf("page=2: expected item to be object, got %#v", it)
			}
			s, ok := m["slug"].(string)
			if !ok {
				t.Fatalf("page=2: expected slug to be string, got %#v", m["slug"])
			}
			slugs2[s] = true
		}

		for s := range slugs2 {
			if slugs1[s] {
				t.Fatalf("expected no overlapping slugs between pages, found %q in both", s)
			}
		}
		union := make(map[string]bool, len(slugs1)+len(slugs2))
		for s := range slugs1 {
			union[s] = true
		}
		for s := range slugs2 {
			union[s] = true
		}
		if len(union) != 3 {
			t.Fatalf("expected union of slugs to be 3, got %d", len(union))
		}
	})

	t.Run("defaults", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("expected status 200, got %d", rec.Code)
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("failed to decode body: %v", err)
		}
		total, ok := body["total"].(float64)
		if !ok {
			t.Fatalf("expected total to be number, got %#v", body["total"])
		}
		if total != 3 {
			t.Fatalf("expected total 3, got %v", total)
		}
		page, ok := body["page"].(float64)
		if !ok {
			t.Fatalf("expected page to be number, got %#v", body["page"])
		}
		if page != 1 {
			t.Fatalf("expected page 1, got %v", page)
		}
		perPage, ok := body["per_page"].(float64)
		if !ok {
			t.Fatalf("expected per_page to be number, got %#v", body["per_page"])
		}
		if perPage != 20 {
			t.Fatalf("expected per_page 20, got %v", perPage)
		}
	})
}
