package handler

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func int64ptr(v int64) *int64 { return &v }

func TestLimitR2_ExhaustedBodyExact(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lx1", URL: "https://example.com/x1", Enabled: true, MaxVisits: int64ptr(2)})
	_ = id

	r1 := doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	if r1.Code != http.StatusFound {
		t.Fatalf("first GET status = %d, want 302", r1.Code)
	}
	r2 := doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	if r2.Code != http.StatusFound {
		t.Fatalf("second GET status = %d, want 302", r2.Code)
	}
	r3 := doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	if r3.Code != http.StatusGone {
		t.Fatalf("third GET status = %d, want 410", r3.Code)
	}
	if !strings.Contains(r3.Body.String(), "链接已达访问上限") {
		t.Fatalf("third GET body = %q, want contains %q", r3.Body.String(), "链接已达访问上限")
	}
}

func TestLimitR2_ExhaustedClicksFrozen(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lx1", URL: "https://example.com/x1", Enabled: true, MaxVisits: int64ptr(2)})
	_ = id

	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	for i := 0; i < 3; i++ {
		r := doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
		if r.Code != http.StatusGone {
			t.Fatalf("post-exhaust GET #%d status = %d, want 410", i+1, r.Code)
		}
	}
	link, err := st.GetLinkBySlug("b2lx1")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link.Clicks != 2 {
		t.Fatalf("Clicks = %d, want 2", link.Clicks)
	}
}

func TestLimitR2_ExhaustedVisitsFrozen(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lx1", URL: "https://example.com/x1", Enabled: true, MaxVisits: int64ptr(2)})

	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	for i := 0; i < 3; i++ {
		doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
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
		t.Fatalf("visits sum = %d, want 2", sum)
	}
}

func TestLimitR2_ExhaustedStillEnabled(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lx1", URL: "https://example.com/x1", Enabled: true, MaxVisits: int64ptr(2)})
	_ = id

	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2lx1", nil, "")

	link, err := st.GetLinkBySlug("b2lx1")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link.Enabled != true {
		t.Fatalf("Enabled = %v, want true", link.Enabled)
	}
}
