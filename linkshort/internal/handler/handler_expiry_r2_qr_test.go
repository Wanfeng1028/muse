package handler

import (
	"net/http"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_QRCodeOnExpiredLink200(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2eq1", URL: "https://example.com/q1", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/qrcode.png", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "image/png") {
		t.Fatalf("expected Content-Type image/png, got %q", ct)
	}
	if rec.Body.Len() == 0 {
		t.Fatalf("expected non-empty body")
	}
}

func TestExpiryR2_QRCodeOnExhaustedLink200(t *testing.T) {
	st, h := newDeep3Router(t)
	max := int64(1)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2eq2", URL: "https://example.com/q2", Enabled: true, MaxVisits: &max})
	rec := doDeep3(t, h, http.MethodGet, "/b2eq2", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302 to exhaust quota, got %d", rec.Code)
	}
	rec2 := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/qrcode.png", nil, "")
	if rec2.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec2.Code)
	}
	if ct := rec2.Header().Get("Content-Type"); !strings.Contains(ct, "image/png") {
		t.Fatalf("expected Content-Type image/png, got %q", ct)
	}
}

func TestExpiryR2_QRCodeMissing404(t *testing.T) {
	_, h := newDeep3Router(t)
	rec := doDeep3(t, h, http.MethodGet, "/api/links/999999/qrcode.png", nil, "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

func TestExpiryR2_QRCodeBadSize400(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2eq3", URL: "https://example.com/q3", Enabled: true})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/qrcode.png?size=0", nil, "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}