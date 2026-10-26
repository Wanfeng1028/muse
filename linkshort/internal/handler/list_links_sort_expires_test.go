package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksSortByExpiresAtHTTP(t *testing.T) {
	st, h := newDeep3Router(t)

	far := time.Now().Add(2 * time.Hour)
	near := time.Now().Add(time.Hour)
	links := []model.Link{
		{Slug: "s-never", URL: "https://s-never.com", Enabled: true},
		{Slug: "s-far", URL: "https://s-far.com", Enabled: true, ExpiresAt: &far},
		{Slug: "s-near", URL: "https://s-near.com", Enabled: true, ExpiresAt: &near},
	}
	for _, l := range links {
		mkLinkDeep3(t, st, &l)
	}

	rec := doDeep3(t, h, http.MethodGet, "/api/links?sort=expires_at", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
	}
	var body struct {
		Items []struct {
			Slug string `json:"slug"`
		} `json:"items"`
		Total int `json:"total"`
	}
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if body.Total != 3 {
		t.Fatalf("expected total 3, got %d", body.Total)
	}
	want := []string{"s-far", "s-near", "s-never"}
	if len(body.Items) != len(want) {
		t.Fatalf("expected %d items, got %d", len(want), len(body.Items))
	}
	for i := range want {
		if body.Items[i].Slug != want[i] {
			t.Fatalf("order mismatch at %d: expected %v, got slug %q", i, want, body.Items[i].Slug)
		}
	}

	rec = doDeep3(t, h, http.MethodGet, "/api/links?sort=bogus", nil, "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("bogus sort: expected status %d, got %d", http.StatusBadRequest, rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "sort 非法") {
		t.Fatalf("bogus sort: expected body to contain sort 非法, got %q", rec.Body.String())
	}
}
