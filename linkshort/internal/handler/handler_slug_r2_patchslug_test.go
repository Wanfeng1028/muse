package handler

import (
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestSlugR2_PatchSlugIgnored(t *testing.T) {
	st, h := newDeep3Router(t)
	l := &model.Link{Slug: "b2psl1", URL: "https://example.com/b2psl1", Title: "旧标题", Enabled: true}
	id := mkLinkDeep3(t, st, l)

	rec := doDeep3(t, h, "PATCH", "/api/links/"+strconv.FormatInt(id, 10), map[string]string{"Content-Type": "application/json"}, `{"slug":"hacked","title":"新标题"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	got, err := st.GetLinkBySlug("b2psl1")
	if err != nil {
		t.Fatalf("GetLinkBySlug(b2psl1) error: %v", err)
	}
	if got == nil {
		t.Fatalf("GetLinkBySlug(b2psl1) returned nil link")
	}

	if _, err := st.GetLinkBySlug("hacked"); err == nil {
		t.Fatalf("expected error for GetLinkBySlug(hacked), got nil")
	}

	updated, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink(%d) error: %v", id, err)
	}
	if updated.Title != "新标题" {
		t.Fatalf("expected title 新标题, got %q", updated.Title)
	}
}

func TestSlugR2_PatchMissingID404(t *testing.T) {
	_, h := newDeep3Router(t)

	req := httptest.NewRequest("PATCH", "/api/links/999999", strings.NewReader(`{"title":"x"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "链接不存在") {
		t.Fatalf("expected body to contain 链接不存在, got %s", rec.Body.String())
	}
}

func TestSlugR2_PatchBadID400(t *testing.T) {
	_, h := newDeep3Router(t)

	req := httptest.NewRequest("PATCH", "/api/links/abc", strings.NewReader(`{"title":"x"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "id 非法") {
		t.Fatalf("expected body to contain id 非法, got %s", rec.Body.String())
	}
}

func TestSlugR2_PatchEmptyBody400(t *testing.T) {
	st, h := newDeep3Router(t)
	l := &model.Link{Slug: "b2psl2", URL: "https://example.com/b2psl2", Title: "标题", Enabled: true}
	id := mkLinkDeep3(t, st, l)

	rec := doDeep3(t, h, "PATCH", "/api/links/"+strconv.FormatInt(id, 10), map[string]string{"Content-Type": "application/json"}, "")

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "请求体解析失败") {
		t.Fatalf("expected body to contain 请求体解析失败, got %s", rec.Body.String())
	}
}
