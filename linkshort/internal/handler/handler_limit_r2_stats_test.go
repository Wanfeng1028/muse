package handler

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestLimitR2_DailyCountsOnlySuccess(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lt1", URL: "https://example.com/b2lt1", Enabled: true, MaxVisits: &mv})

	codes := []int{}
	for i := 0; i < 4; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2lt1", nil, "")
		codes = append(codes, rec.Code)
	}
	if codes[0] != http.StatusFound || codes[1] != http.StatusFound || codes[2] != http.StatusGone || codes[3] != http.StatusGone {
		t.Fatalf("unexpected codes: %v", codes)
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
		t.Fatalf("daily sum = %d, want 2", sum)
	}
}

func TestLimitR2_StatsOverviewClicks(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(3)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2lt2", URL: "https://example.com/b2lt2", Enabled: true, MaxVisits: &mv})

	for i := 0; i < 5; i++ {
		doDeep3(t, h, http.MethodGet, "/b2lt2", nil, "")
	}

	links, enabledLinks, totalClicks, todayClicks, err := st.StatsOverview()
	if err != nil {
		t.Fatalf("StatsOverview error: %v", err)
	}
	if links != 1 {
		t.Fatalf("links = %d, want 1", links)
	}
	if enabledLinks != 1 {
		t.Fatalf("enabledLinks = %d, want 1", enabledLinks)
	}
	if totalClicks != 3 {
		t.Fatalf("totalClicks = %d, want 3", totalClicks)
	}
	if todayClicks != 3 {
		t.Fatalf("todayClicks = %d, want 3", todayClicks)
	}
}

func TestLimitR2_DailyEmptyForFresh(t *testing.T) {
	st, _ := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lt3", URL: "https://example.com/b2lt3", Enabled: true})

	stats, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks error: %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 0 {
		t.Fatalf("daily sum = %d, want 0", sum)
	}
}

func TestLimitR2_DailySumsAcrossLinks(t *testing.T) {
	st, h := newDeep3Router(t)
	id1 := mkLinkDeep3(t, st, &model.Link{Slug: "b2lt4a", URL: "https://example.com/b2lt4a", Enabled: true})
	id2 := mkLinkDeep3(t, st, &model.Link{Slug: "b2lt4b", URL: "https://example.com/b2lt4b", Enabled: true})

	doDeep3(t, h, http.MethodGet, "/b2lt4a", nil, "")
	doDeep3(t, h, http.MethodGet, "/b2lt4b", nil, "")

	stats1, err := st.LinkDailyClicks(id1, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks id1 error: %v", err)
	}
	var sum1 int64
	for _, s := range stats1 {
		sum1 += s.Clicks
	}
	if sum1 != 1 {
		t.Fatalf("id1 daily sum = %d, want 1", sum1)
	}

	stats2, err := st.LinkDailyClicks(id2, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks id2 error: %v", err)
	}
	var sum2 int64
	for _, s := range stats2 {
		sum2 += s.Clicks
	}
	if sum2 != 1 {
		t.Fatalf("id2 daily sum = %d, want 1", sum2)
	}
}
