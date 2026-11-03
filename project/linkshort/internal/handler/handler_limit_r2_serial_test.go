package handler

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestLimitR2_SerialTwoThen410(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ls1", URL: "https://example.com/s1?k=v", Enabled: true, MaxVisits: &mv})

	for i := 0; i < 2; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")
		if rec.Code != http.StatusFound {
			t.Fatalf("request %d: got status %d, want %d", i+1, rec.Code, http.StatusFound)
		}
		if loc := rec.Header().Get("Location"); loc != "https://example.com/s1?k=v" {
			t.Fatalf("request %d: got Location %q, want %q", i+1, loc, "https://example.com/s1?k=v")
		}
	}

	rec := doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("third request: got status %d, want %d", rec.Code, http.StatusGone)
	}
}

func TestLimitR2_SerialClicksTwo(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ls1", URL: "https://example.com/s1?k=v", Enabled: true, MaxVisits: &mv})

	doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")

	link, err := st.GetLinkBySlug("b2ls1")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link.Clicks != 2 {
		t.Fatalf("got Clicks %d, want 2", link.Clicks)
	}
}

func TestLimitR2_SerialVisitsTwo(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ls1", URL: "https://example.com/s1?k=v", Enabled: true, MaxVisits: &mv})

	doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")

	stats, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks error: %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 2 {
		t.Fatalf("got visits sum %d, want 2", sum)
	}
}

func TestLimitR2_Serial410NoExtraVisit(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ls1", URL: "https://example.com/s1?k=v", Enabled: true, MaxVisits: &mv})

	doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")

	for i := 0; i < 2; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2ls1", nil, "")
		if rec.Code != http.StatusGone {
			t.Fatalf("extra request %d: got status %d, want %d", i+1, rec.Code, http.StatusGone)
		}
	}

	stats, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks error: %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 2 {
		t.Fatalf("got visits sum %d, want 2", sum)
	}
}
