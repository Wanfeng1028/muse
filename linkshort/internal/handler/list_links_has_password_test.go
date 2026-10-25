package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksHasPasswordFilterHTTP(t *testing.T) {
	st, h := newDeep3Router(t)

	hash := "hash-for-test"
	links := []model.Link{
		{Slug: "pw-en", URL: "https://pw-en.com", Enabled: true, PasswordHash: &hash},
		{Slug: "pw-dis", URL: "https://pw-dis.com", Enabled: false, PasswordHash: &hash},
		{Slug: "open-en", URL: "https://open-en.com", Enabled: true},
		{Slug: "open-dis", URL: "https://open-dis.com", Enabled: false},
	}
	for _, l := range links {
		mkLinkDeep3(t, st, &l)
	}

	getTotal := func(t *testing.T, target string) float64 {
		t.Helper()
		rec := doDeep3(t, h, http.MethodGet, target, nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("GET %s: expected status %d, got %d", target, http.StatusOK, rec.Code)
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}
		total, ok := body["total"].(float64)
		if !ok {
			t.Fatalf("total missing")
		}
		return total
	}

	t.Run("has_password_true", func(t *testing.T) {
		if total := getTotal(t, "/api/links?has_password=true"); total != 2 {
			t.Fatalf("expected total 2, got %v", total)
		}
	})

	t.Run("has_password_false", func(t *testing.T) {
		if total := getTotal(t, "/api/links?has_password=false"); total != 2 {
			t.Fatalf("expected total 2, got %v", total)
		}
	})

	t.Run("has_password_maybe", func(t *testing.T) {
		rec := doDeep3(t, h, http.MethodGet, "/api/links?has_password=maybe", nil, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected status 400, got %d", rec.Code)
		}
		if !strings.Contains(rec.Body.String(), "has_password") {
			t.Fatalf("expected response body to contain has_password, got %s", rec.Body.String())
		}
	})

	t.Run("has_password_enabled_combo", func(t *testing.T) {
		if total := getTotal(t, "/api/links?has_password=true&enabled=false"); total != 1 {
			t.Fatalf("expected total 1, got %v", total)
		}
	})

	t.Run("has_password_absent", func(t *testing.T) {
		if total := getTotal(t, "/api/links"); total != 4 {
			t.Fatalf("expected total 4, got %v", total)
		}
	})
}
