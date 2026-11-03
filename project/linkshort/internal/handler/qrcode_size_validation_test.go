package handler

import (
	"net/http"
	"strconv"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestQRCodeSizeABC400(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "qsv1", URL: "https://example.com/qsv", Enabled: true})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/qrcode.png?size=abc", nil, "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
}

func TestQRCodeSizeDefault200(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "qsv2", URL: "https://example.com/qsv", Enabled: true})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/qrcode.png", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "image/png") {
		t.Fatalf("expected Content-Type to contain image/png, got %q", ct)
	}
	if rec.Body.Len() == 0 {
		t.Fatal("expected non-empty body")
	}
}

func TestQRCodeSizeExplicit256_200(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "qsv3", URL: "https://example.com/qsv", Enabled: true})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/qrcode.png?size=256", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "image/png") {
		t.Fatalf("expected Content-Type to contain image/png, got %q", ct)
	}
	if rec.Body.Len() == 0 {
		t.Fatal("expected non-empty body")
	}
}

func TestQRCodeSizeMissingLinkABC404(t *testing.T) {
	_, h := newDeep3Router(t)
	rec := doDeep3(t, h, http.MethodGet, "/api/links/999999/qrcode.png?size=abc", nil, "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", rec.Code)
	}
}
