package handler

import (
	"errors"
	"net/http"
	"strings"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func i64ptrH(v int64) *int64 { return &v }

// TestAtomicBurn_32并发恰1次302 burn 链 32 并发，恰 1 次 302，其余 410/404，0 个 500。
func TestAtomicBurn_32并发恰1次302(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:           "atomicburn",
		URL:            "https://example.com/ab",
		Enabled:        true,
		Burn:           true,
		PurgeAfterBurn: false,
	})

	const n = 32
	start := make(chan struct{})
	codes := make([]int, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			rec := doDeep3(t, h, http.MethodGet, "/atomicburn", nil, "")
			codes[idx] = rec.Code
		}(i)
	}
	close(start)
	wg.Wait()

	got302, gotNon302 := 0, 0
	for _, c := range codes {
		if c == http.StatusInternalServerError {
			t.Fatalf("出现 500，不该有：codes=%v", codes)
		}
		switch c {
		case http.StatusFound:
			got302++
		case http.StatusGone, http.StatusNotFound:
			gotNon302++
		}
	}
	if got302 != 1 {
		t.Fatalf("302 数 = %d，期望恰好 1，codes=%v", got302, codes)
	}
	if got302+gotNon302 != n {
		t.Fatalf("302 + 非 302 = %d，期望 %d，codes=%v", got302+gotNon302, n, codes)
	}

	link, err := st.GetLinkBySlug("atomicburn")
	if err == nil {
		if link.Enabled {
			t.Fatalf("burn 链跳转后 Enabled 应为 false")
		}
	} else if !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("GetLinkBySlug err=%v，期望 nil 或 ErrNotFound", err)
	}
}

// TestAtomicMaxVisits_20并发恰N次302 max_visits=5，20 并发恰 5 次 302，15 次 410，0 个 500。
func TestAtomicMaxVisits_20并发恰N次302(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "atomicmax5",
		URL:       "https://example.com/am",
		Enabled:   true,
		MaxVisits: i64ptrH(5),
	})

	const n = 20
	start := make(chan struct{})
	codes := make([]int, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			rec := doDeep3(t, h, http.MethodGet, "/atomicmax5", nil, "")
			codes[idx] = rec.Code
		}(i)
	}
	close(start)
	wg.Wait()

	got302, got410, got500 := 0, 0, 0
	for _, c := range codes {
		switch c {
		case http.StatusFound:
			got302++
		case http.StatusGone:
			got410++
		case http.StatusInternalServerError:
			got500++
		}
	}
	if got500 != 0 {
		t.Fatalf("出现 500，不该有：codes=%v", codes)
	}
	if got302 != 5 {
		t.Fatalf("302 数 = %d，期望恰好 5，codes=%v", got302, codes)
	}
	if got410 != 15 {
		t.Fatalf("410 数 = %d，期望恰好 15，codes=%v", got410, codes)
	}

	link, err := st.GetLinkBySlug("atomicmax5")
	if err == nil {
		if link.Clicks != 5 {
			t.Fatalf("Clicks = %d，期望 5", link.Clicks)
		}
	}
}

// TestMaxVisits_串行N加1 max_visits=5 链串行 GET 6 次：前 5 次 302，第 6 次 410 且 body 含"访问上限"。
func TestMaxVisits_串行N加1(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "maxserial5",
		URL:       "https://example.com/ms",
		Enabled:   true,
		MaxVisits: i64ptrH(5),
	})

	for i := 0; i < 5; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/maxserial5", nil, "")
		if rec.Code != http.StatusFound {
			t.Fatalf("第 %d 次 GET code = %d，期望 302", i+1, rec.Code)
		}
	}
	rec := doDeep3(t, h, http.MethodGet, "/maxserial5", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("第 6 次 GET code = %d，期望 410", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "访问上限") {
		t.Fatalf("第 6 次 body = %q，期望包含 \"访问上限\"", rec.Body.String())
	}
}

// TestBurn_串行两次 burn 链串行 GET 两次：第 1 次 302，第 2 次 410 且 body 含"已阅销毁"。
func TestBurn_串行两次(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "burnserial",
		URL:     "https://example.com/bs",
		Enabled: true,
		Burn:    true,
	})

	rec := doDeep3(t, h, http.MethodGet, "/burnserial", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("第 1 次 GET code = %d，期望 302", rec.Code)
	}
	rec = doDeep3(t, h, http.MethodGet, "/burnserial", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("第 2 次 GET code = %d，期望 410", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "已阅销毁") {
		t.Fatalf("第 2 次 body = %q，期望包含 \"已阅销毁\"", rec.Body.String())
	}
}

// TestBurn_Purge链并发 PurgeAfterBurn=true 的 burn 链 32 并发 GET：302==1，其余为 404 或 410，500==0。
func TestBurn_Purge链并发(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:           "burnpurge",
		URL:            "https://example.com/bp",
		Enabled:        true,
		Burn:           true,
		PurgeAfterBurn: true,
	})

	const n = 32
	start := make(chan struct{})
	codes := make([]int, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			rec := doDeep3(t, h, http.MethodGet, "/burnpurge", nil, "")
			codes[idx] = rec.Code
		}(i)
	}
	close(start)
	wg.Wait()

	got302, gotOther := 0, 0
	for _, c := range codes {
		if c == http.StatusInternalServerError {
			t.Fatalf("出现 500，不该有：codes=%v", codes)
		}
		switch c {
		case http.StatusFound:
			got302++
		case http.StatusGone, http.StatusNotFound:
			gotOther++
		}
	}
	if got302 != 1 {
		t.Fatalf("302 数 = %d，期望恰好 1，codes=%v", got302, codes)
	}
	if got302+gotOther != n {
		t.Fatalf("302 + 非 302 = %d，期望 %d，codes=%v", got302+gotOther, n, codes)
	}
}
