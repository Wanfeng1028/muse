package handler

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurnR2_InvalidXFFStillBurns(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2xf1", URL: "https://example.com/x1", Enabled: true, Burn: true})

	rec := doDeep3(t, h, http.MethodGet, "/b2xf1", map[string]string{"X-Forwarded-For": "not-an-ip"}, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}
}

func TestBurnR2_InvalidXFFRecordsVisit(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2xf1", URL: "https://example.com/x1", Enabled: true, Burn: true})

	rec := doDeep3(t, h, http.MethodGet, "/b2xf1", map[string]string{"X-Forwarded-For": "not-an-ip"}, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}

	stats, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks: %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 1 {
		t.Fatalf("expected 1 visit, got %d", sum)
	}
}

func TestBurnR2_MultiXFFFirstIP(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2xf2", URL: "https://example.com/x2", Enabled: true})

	rec := doDeep3(t, h, http.MethodGet, "/b2xf2", map[string]string{"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}
}

func TestBurnR2_EmptyUANormal(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2xf3", URL: "https://example.com/x3", Enabled: true, Burn: true})

	rec := doDeep3(t, h, http.MethodGet, "/b2xf3", map[string]string{"User-Agent": ""}, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}
}