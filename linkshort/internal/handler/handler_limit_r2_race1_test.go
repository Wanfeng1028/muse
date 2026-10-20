package handler

import (
	"net/http"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestLimitR2_MaxVisits1Race32ExactlyOne302(t *testing.T) {
	st, h := newDeep3Router(t)
	ptrOf := func(v int64) *int64 { return &v }
	mkLinkDeep3(t, st, &model.Link{Slug: "b2l1", URL: "https://example.com/l1", Enabled: true, MaxVisits: ptrOf(1)})

	const n = 32
	start := make(chan struct{})
	var wg sync.WaitGroup
	codes := make([]int, n)
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			rec := doDeep3(t, h, http.MethodGet, "/b2l1", nil, "")
			codes[idx] = rec.Code
		}(i)
	}
	close(start)
	wg.Wait()

	c302 := 0
	c410 := 0
	c500 := 0
	for _, c := range codes {
		switch c {
		case http.StatusFound:
			c302++
		case http.StatusGone:
			c410++
		case http.StatusInternalServerError:
			c500++
		}
	}
	if c302 != 1 {
		t.Fatalf("expected exactly one 302, got %d (codes=%v)", c302, codes)
	}
	if c410 != n-1 {
		t.Fatalf("expected %d 410, got %d (codes=%v)", n-1, c410, codes)
	}
	if c500 != 0 {
		t.Fatalf("expected zero 500, got %d (codes=%v)", c500, codes)
	}
}

func TestLimitR2_MaxVisits1ClicksOne(t *testing.T) {
	st, h := newDeep3Router(t)
	ptrOf := func(v int64) *int64 { return &v }
	mkLinkDeep3(t, st, &model.Link{Slug: "b2l1b", URL: "https://example.com/l1b", Enabled: true, MaxVisits: ptrOf(1)})

	const n = 32
	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			<-start
			doDeep3(t, h, http.MethodGet, "/b2l1b", nil, "")
		}()
	}
	close(start)
	wg.Wait()

	link, err := st.GetLinkBySlug("b2l1b")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link.Clicks != 1 {
		t.Fatalf("expected Clicks == 1, got %d", link.Clicks)
	}
}

func TestLimitR2_MaxVisits1VisitsOne(t *testing.T) {
	st, h := newDeep3Router(t)
	ptrOf := func(v int64) *int64 { return &v }
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2l1v", URL: "https://example.com/l1v", Enabled: true, MaxVisits: ptrOf(1)})

	const n = 32
	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			<-start
			doDeep3(t, h, http.MethodGet, "/b2l1v", nil, "")
		}()
	}
	close(start)
	wg.Wait()

	stats, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks error: %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 1 {
		t.Fatalf("expected sum of daily visits == 1, got %d (stats=%v)", sum, stats)
	}
}

func TestLimitR2_SecondWaveAll410(t *testing.T) {
	st, h := newDeep3Router(t)
	ptrOf := func(v int64) *int64 { return &v }
	mkLinkDeep3(t, st, &model.Link{Slug: "b2l1c", URL: "https://example.com/l1c", Enabled: true, MaxVisits: ptrOf(2)})

	rec1 := doDeep3(t, h, http.MethodGet, "/b2l1c", nil, "")
	if rec1.Code != http.StatusFound {
		t.Fatalf("first serial GET expected 302, got %d", rec1.Code)
	}
	rec2 := doDeep3(t, h, http.MethodGet, "/b2l1c", nil, "")
	if rec2.Code != http.StatusFound {
		t.Fatalf("second serial GET expected 302, got %d", rec2.Code)
	}

	const n = 10
	start := make(chan struct{})
	var wg sync.WaitGroup
	codes := make([]int, n)
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			rec := doDeep3(t, h, http.MethodGet, "/b2l1c", nil, "")
			codes[idx] = rec.Code
		}(i)
	}
	close(start)
	wg.Wait()

	for i, c := range codes {
		if c != http.StatusGone {
			t.Fatalf("second wave goroutine %d expected 410, got %d (codes=%v)", i, c, codes)
		}
	}

	link, err := st.GetLinkBySlug("b2l1c")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link.Clicks != 2 {
		t.Fatalf("expected Clicks == 2, got %d", link.Clicks)
	}
}
