package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_CreateWithOffsetNormalizedToUTC(t *testing.T) {
	_, h := newDeep3Router(t)
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/tz1","slug":"b2tz1","expires_at":"2027-06-01T12:00:00+08:00"}`))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, w.Body.String())
	}
	got, ok := resp["expires_at"].(string)
	if !ok {
		t.Fatalf("expires_at not string: %v", resp["expires_at"])
	}
	if got != "2027-06-01T04:00:00Z" {
		t.Fatalf("expected 2027-06-01T04:00:00Z, got %q", got)
	}
	if _, err := time.Parse(time.RFC3339, got); err != nil {
		t.Fatalf("time.Parse: %v", err)
	}
}

func TestExpiryR2_CreateWithZStaysZ(t *testing.T) {
	_, h := newDeep3Router(t)
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/tz2","slug":"b2tz3","expires_at":"2027-06-01T04:00:00Z"}`))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, w.Body.String())
	}
	got, ok := resp["expires_at"].(string)
	if !ok {
		t.Fatalf("expires_at not string: %v", resp["expires_at"])
	}
	if got != "2027-06-01T04:00:00Z" {
		t.Fatalf("expected 2027-06-01T04:00:00Z, got %q", got)
	}
}

func TestExpiryR2_CreateMalformedExpiresAt400(t *testing.T) {
	_, h := newDeep3Router(t)
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/tz3","slug":"b2tz4","expires_at":"2027/06/01"}`))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "expires_at 格式错误") {
		t.Fatalf("expected body to contain expires_at 格式错误, got %s", w.Body.String())
	}
}

func TestExpiryR2_OffsetExpiryEnforced(t *testing.T) {
	st, h := newDeep3Router(t)
	exp1, err := time.Parse(time.RFC3339, "2027-06-01T12:00:00+08:00")
	if err != nil {
		t.Fatalf("parse time: %v", err)
	}
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2tz1",
		URL:       "https://example.com/tz1",
		Enabled:   true,
		ExpiresAt: &exp1,
	})
	w := doDeep3(t, h, "GET", "/b2tz1", nil, "")
	if w.Code != http.StatusFound {
		t.Fatalf("expected 302 for future offset expiry, got %d body=%s", w.Code, w.Body.String())
	}
	exp2, err := time.Parse(time.RFC3339, "2020-06-01T12:00:00+08:00")
	if err != nil {
		t.Fatalf("parse time: %v", err)
	}
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2tz2",
		URL:       "https://example.com/tz2",
		Enabled:   true,
		ExpiresAt: &exp2,
	})
	w2 := doDeep3(t, h, "GET", "/b2tz2", nil, "")
	if w2.Code != http.StatusGone {
		t.Fatalf("expected 410 for past offset expiry, got %d body=%s", w2.Code, w2.Body.String())
	}
	if !strings.Contains(w2.Body.String(), "链接已过期") {
		t.Fatalf("expected body to contain 链接已过期, got %s", w2.Body.String())
	}
}
