package handler

import (
	"net/http"
	"strings"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurnR2_PostConsumesBurnQuota(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2post1", URL: "https://example.com/p1", Enabled: true, Burn: true})

	rr := doDeep3(t, h, http.MethodPost, "/b2post1", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("first POST code=%d want 302", rr.Code)
	}
	if loc := rr.Header().Get("Location"); loc != "https://example.com/p1" {
		t.Fatalf("first POST Location=%q want %q", loc, "https://example.com/p1")
	}

	rr2 := doDeep3(t, h, http.MethodPost, "/b2post1", nil, "")
	if rr2.Code != http.StatusGone {
		t.Fatalf("second POST code=%d want 410", rr2.Code)
	}
	if !strings.Contains(rr2.Body.String(), "链接已阅销毁") {
		t.Fatalf("second POST body=%q want contains 链接已阅销毁", rr2.Body.String())
	}

	link, err := st.GetLinkBySlug("b2post1")
	if err != nil {
		t.Fatalf("GetLinkBySlug err=%v", err)
	}
	if link.BurnedAt == nil {
		t.Fatalf("BurnedAt is nil want non-nil")
	}
}

func TestBurnR2_PostThenGetSecond410(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2post2", URL: "https://example.com/p2", Enabled: true, Burn: true})

	rr := doDeep3(t, h, http.MethodPost, "/b2post2", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("POST code=%d want 302", rr.Code)
	}

	rr2 := doDeep3(t, h, http.MethodGet, "/b2post2", nil, "")
	if rr2.Code != http.StatusGone {
		t.Fatalf("GET code=%d want 410", rr2.Code)
	}
}

func TestBurnR2_MixedGetPostRaceExactlyOne302(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2post3", URL: "https://example.com/p3", Enabled: true, Burn: true})

	const total = 32
	start := make(chan struct{})
	codes := make([]int, total)
	var wg sync.WaitGroup
	wg.Add(total)
	for i := 0; i < total; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			method := http.MethodGet
			if idx%2 == 1 {
				method = http.MethodPost
			}
			rr := doDeep3(t, h, method, "/b2post3", nil, "")
			codes[idx] = rr.Code
		}(i)
	}
	close(start)
	wg.Wait()

	count302 := 0
	for _, c := range codes {
		if c == http.StatusFound {
			count302++
		} else if c != http.StatusGone {
			t.Fatalf("unexpected code=%d want 302 or 410", c)
		}
	}
	if count302 != 1 {
		t.Fatalf("302 count=%d want exactly 1", count302)
	}

	link, err := st.GetLinkBySlug("b2post3")
	if err != nil {
		t.Fatalf("GetLinkBySlug err=%v", err)
	}
	if link.Clicks != 1 {
		t.Fatalf("Clicks=%d want 1", link.Clicks)
	}
}

func TestBurnR2_PostOnNormalLinkRedirects(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2post4", URL: "https://example.com/p4", Enabled: true})

	rr := doDeep3(t, h, http.MethodPost, "/b2post4", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("POST code=%d want 302", rr.Code)
	}
	if loc := rr.Header().Get("Location"); loc != "https://example.com/p4" {
		t.Fatalf("Location=%q want %q", loc, "https://example.com/p4")
	}

	link, err := st.GetLinkBySlug("b2post4")
	if err != nil {
		t.Fatalf("GetLinkBySlug err=%v", err)
	}
	if link.Clicks != 1 {
		t.Fatalf("Clicks=%d want 1", link.Clicks)
	}
}