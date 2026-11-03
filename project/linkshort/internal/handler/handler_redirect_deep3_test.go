package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newDeep3Router(t *testing.T) (*store.Store, http.Handler) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	return st, NewRouter(st, &cfg)
}

func mkLinkDeep3(t *testing.T, st *store.Store, l *model.Link) int64 {
	t.Helper()
	id, err := st.CreateLinkEx(l.Slug, l.URL, l.Title, l.ExpiresAt, l.MaxVisits, l.Burn, l.PurgeAfterBurn)
	if err != nil {
		t.Fatalf("CreateLinkEx(%s): %v", l.Slug, err)
	}
	if !l.Enabled {
		if err := st.UpdateLinkEx(id, l.Title, false, l.ExpiresAt, l.MaxVisits, l.Burn, l.PurgeAfterBurn); err != nil {
			t.Fatalf("disable link: %v", err)
		}
	}
	if l.PasswordHash != nil {
		if err := st.SetLinkPassword(id, *l.PasswordHash); err != nil {
			t.Fatalf("set password: %v", err)
		}
	}
	return id
}

func doDeep3(t *testing.T, h http.Handler, method, target string, hdr map[string]string, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, target, strings.NewReader(body))
	if method == http.MethodPost {
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	}
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

// 密码页 GET 不应产生点击（仅渲染表单）。
func TestDeep3PasswordGetDoesNotRecordClick(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, err := auth.HashPassword("pw12345678")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	mkLinkDeep3(t, st, &model.Link{
		Slug:         "pwget",
		URL:          "https://example.com/pwget",
		Enabled:      true,
		PasswordHash: &hash,
	})
	rr := doDeep3(t, h, http.MethodGet, "/pwget", nil, "")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rr.Code)
	}
	if loc := rr.Header().Get("Location"); loc != "" {
		t.Fatalf("password page must not redirect, Location=%q", loc)
	}
	got, err := st.GetLinkBySlug("pwget")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 0 {
		t.Fatalf("GET password page must not record click, got %d", got.Clicks)
	}
}

// 无密码短链的 POST 也直接跳转（兼容直 POST 客户端）。
func TestDeep3PostNoPasswordRedirects(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "nopostpw",
		URL:     "https://example.com/nopostpw",
		Enabled: true,
	})
	rr := doDeep3(t, h, http.MethodPost, "/nopostpw", nil, "password=whatever")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	if got := rr.Header().Get("Location"); got != "https://example.com/nopostpw" {
		t.Fatalf("Location = %q", got)
	}
}

// 密码短链 POST 缺 password 字段应视为错误。
func TestDeep3PostMissingPasswordField(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, err := auth.HashPassword("pw12345678")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	mkLinkDeep3(t, st, &model.Link{
		Slug:         "nopwfield",
		URL:          "https://example.com/nopwfield",
		Enabled:      true,
		PasswordHash: &hash,
	})
	rr := doDeep3(t, h, http.MethodPost, "/nopwfield", nil, "")
	if rr.Code == http.StatusFound {
		t.Fatalf("missing password must not redirect")
	}
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rr.Code)
	}
	got, err := st.GetLinkBySlug("nopwfield")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 0 {
		t.Fatalf("failed unlock must not record click, got %d", got.Clicks)
	}
}

// 密码错误多次仍不产生点击，并保持 401。
func TestDeep3RepeatedWrongPasswordKeepsClicksZero(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, err := auth.HashPassword("rightpw1234")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	mkLinkDeep3(t, st, &model.Link{
		Slug:         "repeatwrong",
		URL:          "https://example.com/repeatwrong",
		Enabled:      true,
		PasswordHash: &hash,
	})
	for i := 0; i < 3; i++ {
		rr := doDeep3(t, h, http.MethodPost, "/repeatwrong", nil, "password=nope")
		if rr.Code != http.StatusUnauthorized {
			t.Fatalf("iter %d: status = %d, want 401", i, rr.Code)
		}
	}
	got, err := st.GetLinkBySlug("repeatwrong")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 0 {
		t.Fatalf("wrong password must not record clicks, got %d", got.Clicks)
	}
}

// 密码短链已达访问上限：正确密码解锁后应 410。
func TestDeep3PasswordCorrectButCapped410(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, err := auth.HashPassword("pw12345678")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	var limit int64 = 1
	id := mkLinkDeep3(t, st, &model.Link{
		Slug:         "pwcap",
		URL:          "https://example.com/pwcap",
		Enabled:      true,
		MaxVisits:    &limit,
		PasswordHash: &hash,
	})
	if err := st.RecordVisit(id, "", "", ""); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	rr := doDeep3(t, h, http.MethodPost, "/pwcap", nil, "password=pw12345678")
	if rr.Code != http.StatusGone {
		t.Fatalf("status = %d, want 410", rr.Code)
	}
}

// 密码短链过期：GET 密码页也应按过期处理 410。
func TestDeep3PasswordExpired410(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, err := auth.HashPassword("pw12345678")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	past := time.Now().Add(-1 * time.Hour)
	mkLinkDeep3(t, st, &model.Link{
		Slug:         "pwexpired",
		URL:          "https://example.com/pwexpired",
		Enabled:      true,
		ExpiresAt:    &past,
		PasswordHash: &hash,
	})
	rr := doDeep3(t, h, http.MethodGet, "/pwexpired", nil, "")
	if rr.Code != http.StatusGone {
		t.Fatalf("status = %d, want 410", rr.Code)
	}
}

// 密码短链禁用：应 404（不暴露密码页）。
func TestDeep3PasswordDisabled404(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, err := auth.HashPassword("pw12345678")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	mkLinkDeep3(t, st, &model.Link{
		Slug:         "pwdisabled",
		URL:          "https://example.com/pwdisabled",
		Enabled:      false,
		PasswordHash: &hash,
	})
	rr := doDeep3(t, h, http.MethodGet, "/pwdisabled", nil, "")
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rr.Code)
	}
}

// burn + purge：跳转一次后应彻底删除，二次访问 404（不是 410）。
func TestDeep3BurnWithPurgeRemovesLink(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:           "burnpurge",
		URL:            "https://example.com/burnpurge",
		Enabled:        true,
		Burn:           true,
		PurgeAfterBurn: true,
	})
	first := doDeep3(t, h, http.MethodGet, "/burnpurge", nil, "")
	if first.Code != http.StatusFound {
		t.Fatalf("first status = %d, want 302", first.Code)
	}
	second := doDeep3(t, h, http.MethodGet, "/burnpurge", nil, "")
	if second.Code != http.StatusNotFound {
		t.Fatalf("after purge status = %d, want 404", second.Code)
	}
}

// burn 不带 purge：第一次 302，第二次 410（保留在库中标记已销毁）。
func TestDeep3BurnWithoutPurgeStays410(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "burnkeep",
		URL:     "https://example.com/burnkeep",
		Enabled: true,
		Burn:    true,
	})
	first := doDeep3(t, h, http.MethodGet, "/burnkeep", nil, "")
	if first.Code != http.StatusFound {
		t.Fatalf("first status = %d, want 302", first.Code)
	}
	second := doDeep3(t, h, http.MethodGet, "/burnkeep", nil, "")
	if second.Code != http.StatusGone {
		t.Fatalf("second status = %d, want 410", second.Code)
	}
}

// MaxVisits 未达上限：第一次应 302 并递增点击。
func TestDeep3MaxVisitsNotYetReachedRedirects(t *testing.T) {
	st, h := newDeep3Router(t)
	var limit int64 = 3
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "capnotyet",
		URL:       "https://example.com/capnotyet",
		Enabled:   true,
		MaxVisits: &limit,
	})
	rr := doDeep3(t, h, http.MethodGet, "/capnotyet", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	got, err := st.GetLinkBySlug("capnotyet")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("clicks = %d, want 1", got.Clicks)
	}
}

// X-Forwarded-For 非法值应回退到 RemoteAddr，仍应 302 并记录点击。
func TestDeep3InvalidXFFFallsBackAndRecords(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "badxff",
		URL:     "https://example.com/badxff",
		Enabled: true,
	})
	rr := doDeep3(t, h, http.MethodGet, "/badxff", map[string]string{
		"X-Forwarded-For": "not-an-ip, 10.0.0.1",
	}, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	got, err := st.GetLinkBySlug("badxff")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("clicks = %d, want 1", got.Clicks)
	}
}

// X-Real-IP 回退路径也应能记录点击。
func TestDeep3XRealIPFallbackRecords(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "xrealip",
		URL:     "https://example.com/xrealip",
		Enabled: true,
	})
	rr := doDeep3(t, h, http.MethodGet, "/xrealip", map[string]string{
		"X-Real-IP": "203.0.113.7",
	}, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	got, err := st.GetLinkBySlug("xrealip")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("clicks = %d, want 1", got.Clicks)
	}
}

// 超长 User-Agent/Referer 应被截断而不影响跳转。
func TestDeep3TruncatesLongUAAndReferer(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "longua",
		URL:     "https://example.com/longua",
		Enabled: true,
	})
	longUA := strings.Repeat("U", 4096)
	longRef := "https://ref.example.com/" + strings.Repeat("r", 2048)
	rr := doDeep3(t, h, http.MethodGet, "/longua", map[string]string{
		"User-Agent": longUA,
		"Referer":    longRef,
	}, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	got, err := st.GetLinkBySlug("longua")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("clicks = %d, want 1", got.Clicks)
	}
}

// 根路径应 302 到 /ui/。
func TestDeep3RootRedirectsToUI(t *testing.T) {
	_, h := newDeep3Router(t)
	rr := doDeep3(t, h, http.MethodGet, "/", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	if loc := rr.Header().Get("Location"); loc != "/ui/" {
		t.Fatalf("Location = %q, want /ui/", loc)
	}
}

// 两次点击分别走不同 IP，均记录，clicks 累加为 2。
func TestDeep3TwoDifferentIPsAccumulateClicks(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "twoip",
		URL:     "https://example.com/twoip",
		Enabled: true,
	})
	doDeep3(t, h, http.MethodGet, "/twoip", map[string]string{"X-Forwarded-For": "198.51.100.1"}, "")
	doDeep3(t, h, http.MethodGet, "/twoip", map[string]string{"X-Forwarded-For": "198.51.100.2"}, "")
	got, err := st.GetLinkBySlug("twoip")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 2 {
		t.Fatalf("clicks = %d, want 2", got.Clicks)
	}
}
