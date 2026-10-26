package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestListLinksSortValidationHTTP(t *testing.T) {
	st, h := newDeep3Router(t)
	_ = st

	t.Run("sort_bogus", func(t *testing.T) {
		w := doDeep3(t, h, http.MethodGet, "/api/links?sort=bogus", nil, "")
		if w.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", w.Code)
		}
		if !strings.Contains(w.Body.String(), "sort 非法") {
			t.Fatalf("expected body to contain 'sort 非法', got %q", w.Body.String())
		}
	})

	t.Run("sort_empty", func(t *testing.T) {
		w := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
		if w.Code != http.StatusOK {
			t.Fatalf("expected status 200, got %d", w.Code)
		}
	})

	t.Run("sort_clicks", func(t *testing.T) {
		w := doDeep3(t, h, http.MethodGet, "/api/links?sort=clicks", nil, "")
		if w.Code != http.StatusOK {
			t.Fatalf("expected status 200, got %d", w.Code)
		}
	})

	t.Run("sort_created_at", func(t *testing.T) {
		w := doDeep3(t, h, http.MethodGet, "/api/links?sort=created_at", nil, "")
		if w.Code != http.StatusOK {
			t.Fatalf("expected status 200, got %d", w.Code)
		}
	})

	t.Run("sort_expires_at", func(t *testing.T) {
		w := doDeep3(t, h, http.MethodGet, "/api/links?sort=expires_at", nil, "")
		if w.Code != http.StatusOK {
			t.Fatalf("expected status 200, got %d", w.Code)
		}
	})
}
