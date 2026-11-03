package handler

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// TestBurnRaceConcurrentGet 验并发访问 burn 链接时的精确语义：
// TryBurn 的单条条件 UPDATE 保证全局恰好 1 次 302，
// 其余请求要么在 loadActiveLink 命中 enabled=0 → 410"链接已阅销毁"，
// 要么在 purge 链删行后 → 404"短链不存在"。
func TestBurnRaceConcurrentGet(t *testing.T) {
	st, h := newDeep3Router(t)

	mkLinkDeep3(t, st, &model.Link{
		Slug:           "burnrace",
		URL:            "https://example.com/x",
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
			rec := doDeep3(t, h, http.MethodGet, "/burnrace", nil, "")
			codes[idx] = rec.Code
		}(i)
	}
	close(start)
	wg.Wait()

	got302 := 0
	gotNon302 := 0
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
		t.Fatalf("302 数 + 非 302 数 = %d，期望 %d，codes=%v", got302+gotNon302, n, codes)
	}

	// 每个 302 恰好记一次访问。
	link, err := st.GetLinkBySlug("burnrace")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Clicks != int64(got302) {
		t.Fatalf("Clicks = %d，期望等于 302 的数量 %d", link.Clicks, got302)
	}
	if link.Enabled {
		t.Fatalf("burn 链接跳转后 Enabled 应该为 false，实际为 true")
	}

	// 再访问一次，burn 且已禁用 → 410 "链接已阅销毁"
	rec := doDeep3(t, h, http.MethodGet, "/burnrace", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("再访问状态码 = %d，期望 410", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已阅销毁") {
		t.Fatalf("响应 body 应包含 链接已阅销毁，实际：%q", rec.Body.String())
	}
}

// TestClientIPHeaderPrecedence 验 clientIP 的头优先级，以及 hashIP 的长度和稳定性。
func TestClientIPHeaderPrecedence(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	r.Header.Set("X-Forwarded-For", "1.2.3.4, 5.6.7.8")
	if got := clientIP(r, trustedProxyTestConfig(t, "192.0.2.1/32")); got != "1.2.3.4" {
		t.Fatalf("XFF 取第一个合法 IP，got=%q 期望 1.2.3.4", got)
	}

	r2 := httptest.NewRequest(http.MethodGet, "/x", nil)
	r2.Header.Set("X-Forwarded-For", "garbage")
	r2.Header.Set("X-Real-IP", "9.9.9.9")
	if got := clientIP(r2, trustedProxyTestConfig(t, "192.0.2.1/32")); got != "9.9.9.9" {
		t.Fatalf("XFF 非法时回落到 X-Real-IP，got=%q 期望 9.9.9.9", got)
	}

	h1 := hashIP("1.2.3.4")
	if len(h1) != 16 {
		t.Fatalf("hashIP 结果长度 = %d，期望 16", len(h1))
	}
	if h2 := hashIP("1.2.3.4"); h2 != h1 {
		t.Fatalf("hashIP 同一输入两次结果应一致，got %q vs %q", h1, h2)
	}
}

// TestMarkBurnedTwice 验 MarkBurned 对已销毁 burn 链接的真实行为。
// 关键点：SQL 是 UPDATE links SET enabled=0 ... WHERE id=? AND burn=1，
// 只看 burn=1，不看 enabled，所以对已经 enabled=0 的 burn 链接再调一次，
// WHERE 仍然匹配，影响行数为 1，返回 nil，而不是 ErrNotFound。
func TestMarkBurnedTwice(t *testing.T) {
	st, _ := newDeep3Router(t)

	id := mkLinkDeep3(t, st, &model.Link{
		Slug:           "burnmark",
		URL:            "https://example.com/b",
		Enabled:        true,
		Burn:           true,
		PurgeAfterBurn: false,
	})

	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("第一次 MarkBurned 应成功，got err=%v", err)
	}
	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("第二次 MarkBurned 应返回 nil（WHERE 只看 burn=1），got err=%v", err)
	}

	// burn=false 的链接，WHERE 不匹配，影响行数 0 → ErrNotFound
	normalID := mkLinkDeep3(t, st, &model.Link{
		Slug:    "notburn",
		URL:     "https://example.com/n",
		Enabled: true,
		Burn:    false,
	})
	if err := st.MarkBurned(normalID); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("对 burn=false 的链接 MarkBurned 应返回 ErrNotFound，got err=%v", err)
	}

	// 不存在的 id，影响行数 0 → ErrNotFound
	if err := st.MarkBurned(999999); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("对不存在的 id MarkBurned 应返回 ErrNotFound，got err=%v", err)
	}
}
