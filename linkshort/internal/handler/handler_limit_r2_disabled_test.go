package handler

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestLimitR2_DisabledQuotaNotConsumed(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ld1", URL: "https://example.com/d1", Enabled: true, MaxVisits: &mv})
	if err := st.UpdateLinkEx(id, "", false, nil, &mv, false, false); err != nil {
		t.Fatalf("UpdateLinkEx disable: %v", err)
	}
	rec := doDeep3(t, h, http.MethodGet, "/b2ld1", nil, "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("disabled GET code = %d, want 404", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "短链不存在") {
		t.Fatalf("disabled GET body = %q, want contains 短链不存在", rec.Body.String())
	}
	link, err := st.GetLinkBySlug("b2ld1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Clicks != 0 {
		t.Fatalf("disabled clicks = %d, want 0", link.Clicks)
	}
}

func TestLimitR2_ReenabledQuotaIntact(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ld1", URL: "https://example.com/d1", Enabled: true, MaxVisits: &mv})
	if err := st.UpdateLinkEx(id, "", false, nil, &mv, false, false); err != nil {
		t.Fatalf("UpdateLinkEx disable: %v", err)
	}
	doDeep3(t, h, http.MethodGet, "/b2ld1", nil, "")
	if err := st.UpdateLinkEx(id, "", true, nil, &mv, false, false); err != nil {
		t.Fatalf("UpdateLinkEx reenable: %v", err)
	}
	rec1 := doDeep3(t, h, http.MethodGet, "/b2ld1", nil, "")
	if rec1.Code != http.StatusFound {
		t.Fatalf("reenabled GET #1 code = %d, want 302", rec1.Code)
	}
	rec2 := doDeep3(t, h, http.MethodGet, "/b2ld1", nil, "")
	if rec2.Code != http.StatusFound {
		t.Fatalf("reenabled GET #2 code = %d, want 302", rec2.Code)
	}
	rec3 := doDeep3(t, h, http.MethodGet, "/b2ld1", nil, "")
	if rec3.Code != http.StatusGone {
		t.Fatalf("reenabled GET #3 code = %d, want 410", rec3.Code)
	}
}

func TestLimitR2_DisabledPost410(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(1)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ld2", URL: "https://example.com/d2", Enabled: true, MaxVisits: &mv})
	rec1 := doDeep3(t, h, http.MethodGet, "/b2ld2", nil, "")
	if rec1.Code != http.StatusFound {
		t.Fatalf("GET #1 code = %d, want 302", rec1.Code)
	}
	if err := st.UpdateLinkEx(id, "", false, nil, &mv, false, false); err != nil {
		t.Fatalf("UpdateLinkEx disable: %v", err)
	}
	rec2 := doDeep3(t, h, http.MethodGet, "/b2ld2", nil, "")
	if rec2.Code != http.StatusNotFound {
		t.Fatalf("disabled exhausted GET code = %d, want 404", rec2.Code)
	}
}

func TestLimitR2_ReenabledStillExhausted(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(1)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ld2", URL: "https://example.com/d2", Enabled: true, MaxVisits: &mv})
	doDeep3(t, h, http.MethodGet, "/b2ld2", nil, "")
	if err := st.UpdateLinkEx(id, "", false, nil, &mv, false, false); err != nil {
		t.Fatalf("UpdateLinkEx disable: %v", err)
	}
	doDeep3(t, h, http.MethodGet, "/b2ld2", nil, "")
	if err := st.UpdateLinkEx(id, "", true, nil, &mv, false, false); err != nil {
		t.Fatalf("UpdateLinkEx reenable: %v", err)
	}
	rec := doDeep3(t, h, http.MethodGet, "/b2ld2", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("reenabled exhausted GET code = %d, want 410", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已达访问上限") {
		t.Fatalf("reenabled exhausted GET body = %q, want contains 链接已达访问上限", rec.Body.String())
	}
}