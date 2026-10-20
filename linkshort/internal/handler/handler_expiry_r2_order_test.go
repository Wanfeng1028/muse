package handler

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_ExpiredBeatsExhausted(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(1)
	exp := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2eo1",
		URL:       "https://example.com/o1",
		Enabled:   true,
		ExpiresAt: &exp,
		MaxVisits: &mv,
	})
	rec := doDeep3(t, h, http.MethodGet, "/b2eo1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("expected 410, got %d body=%q", rec.Code, rec.Body.String())
	}
	body := rec.Body.String()
	if !strings.Contains(body, "链接已过期") {
		t.Fatalf("expected body to contain 链接已过期, got %q", body)
	}
	if strings.Contains(body, "链接已达访问上限") {
		t.Fatalf("expected body to not contain 链接已达访问上限, got %q", body)
	}
}

func TestExpiryR2_ExhaustedBeatsNormal(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(1)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2eo2",
		URL:       "https://example.com/o2",
		Enabled:   true,
		MaxVisits: &mv,
	})
	first := doDeep3(t, h, http.MethodGet, "/b2eo2", nil, "")
	if first.Code != http.StatusFound {
		t.Fatalf("first GET expected 302, got %d body=%q", first.Code, first.Body.String())
	}
	second := doDeep3(t, h, http.MethodGet, "/b2eo2", nil, "")
	if second.Code != http.StatusGone {
		t.Fatalf("second GET expected 410, got %d body=%q", second.Code, second.Body.String())
	}
	if !strings.Contains(second.Body.String(), "链接已达访问上限") {
		t.Fatalf("expected body to contain 链接已达访问上限, got %q", second.Body.String())
	}
}

func TestExpiryR2_TwoLinksSameURLIndependent(t *testing.T) {
	st, h := newDeep3Router(t)
	expired := time.Now().Add(-time.Hour)
	future := time.Now().Add(time.Hour)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2eo3a",
		URL:       "https://example.com/same",
		Enabled:   true,
		ExpiresAt: &expired,
	})
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2eo3b",
		URL:       "https://example.com/same",
		Enabled:   true,
		ExpiresAt: &future,
	})
	recA := doDeep3(t, h, http.MethodGet, "/b2eo3a", nil, "")
	if recA.Code != http.StatusGone {
		t.Fatalf("expired link expected 410, got %d body=%q", recA.Code, recA.Body.String())
	}
	recB := doDeep3(t, h, http.MethodGet, "/b2eo3b", nil, "")
	if recB.Code != http.StatusFound {
		t.Fatalf("active link expected 302, got %d body=%q", recB.Code, recB.Body.String())
	}
}

func TestExpiryR2_BoundaryHour(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2eo4past",
		URL:       "https://example.com/bpast",
		Enabled:   true,
		ExpiresAt: &past,
	})
	recPast := doDeep3(t, h, http.MethodGet, "/b2eo4past", nil, "")
	if recPast.Code != http.StatusGone {
		t.Fatalf("past expiry expected 410, got %d body=%q", recPast.Code, recPast.Body.String())
	}
	future := time.Now().Add(time.Hour)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2eo4future",
		URL:       "https://example.com/bfuture",
		Enabled:   true,
		ExpiresAt: &future,
	})
	recFuture := doDeep3(t, h, http.MethodGet, "/b2eo4future", nil, "")
	if recFuture.Code != http.StatusFound {
		t.Fatalf("future expiry expected 302, got %d body=%q", recFuture.Code, recFuture.Body.String())
	}
}