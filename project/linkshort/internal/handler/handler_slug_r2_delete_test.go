package handler

import (
	"net/http"
	"strconv"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestSlugR2_DeleteRedirect404(t *testing.T) {
	st, h := newDeep3Router(t)
	link := &model.Link{Slug: "b2del1", URL: "https://example.com/b2del1", Enabled: true}
	id := mkLinkDeep3(t, st, link)

	rec := doDeep3(t, h, http.MethodGet, "/b2del1", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302 before delete, got %d", rec.Code)
	}

	rec = doDeep3(t, h, http.MethodDelete, "/api/links/"+strconv.FormatInt(id, 10), nil, "")
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204 on delete, got %d", rec.Code)
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2del1", nil, "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 after delete, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "短链不存在") {
		t.Fatalf("expected body to contain 短链不存在, got %q", rec.Body.String())
	}
}

func TestSlugR2_DeleteCascadesVisits(t *testing.T) {
	st, h := newDeep3Router(t)
	link := &model.Link{Slug: "b2del2", URL: "https://example.com/b2del2", Enabled: true}
	id := mkLinkDeep3(t, st, link)

	for i := 0; i < 2; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2del2", nil, "")
		if rec.Code != http.StatusFound {
			t.Fatalf("expected 302 on visit %d, got %d", i, rec.Code)
		}
	}

	stats, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks before delete: %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 2 {
		t.Fatalf("expected 2 clicks before delete, got %d", sum)
	}

	rec := doDeep3(t, h, http.MethodDelete, "/api/links/"+strconv.FormatInt(id, 10), nil, "")
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204 on delete, got %d", rec.Code)
	}

	stats, err = st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks after delete: %v", err)
	}
	sum = 0
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 0 {
		t.Fatalf("expected 0 clicks after delete (cascade), got %d", sum)
	}
}

func TestSlugR2_DeleteMissing404(t *testing.T) {
	_, h := newDeep3Router(t)

	rec := doDeep3(t, h, http.MethodDelete, "/api/links/999999", nil, "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接不存在") {
		t.Fatalf("expected body to contain 链接不存在, got %q", rec.Body.String())
	}
}

func TestSlugR2_DeleteBadID400(t *testing.T) {
	_, h := newDeep3Router(t)

	rec := doDeep3(t, h, http.MethodDelete, "/api/links/xyz", nil, "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "id 非法") {
		t.Fatalf("expected body to contain id 非法, got %q", rec.Body.String())
	}
}
