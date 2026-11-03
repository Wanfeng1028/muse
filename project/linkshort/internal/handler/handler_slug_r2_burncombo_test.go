package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSlugR2_BurnMaxVisits1OK(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/c1","slug":"b2c1","burn":true,"max_visits":1}`
	rr := doDeep3(t, h, "POST", "/api/links", map[string]string{"Content-Type": "application/json"}, body)
	if rr.Code != 201 {
		t.Fatalf("expected 201, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

func TestSlugR2_BurnMaxVisits1BurnWins(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/c2","slug":"b2c2","burn":true,"max_visits":1}`
	rr := doDeep3(t, h, "POST", "/api/links", map[string]string{"Content-Type": "application/json"}, body)
	if rr.Code != 201 {
		t.Fatalf("expected 201, got %d, body=%s", rr.Code, rr.Body.String())
	}
	rr1 := doDeep3(t, h, "GET", "/b2c2", nil, "")
	if rr1.Code != 302 {
		t.Fatalf("expected 302, got %d, body=%s", rr1.Code, rr1.Body.String())
	}
	rr2 := doDeep3(t, h, "GET", "/b2c2", nil, "")
	if rr2.Code != 410 {
		t.Fatalf("expected 410, got %d, body=%s", rr2.Code, rr2.Body.String())
	}
	if !strings.Contains(rr2.Body.String(), "链接已阅销毁") {
		t.Fatalf("expected body contains 链接已阅销毁, got %s", rr2.Body.String())
	}
}

func TestSlugR2_PurgeWithoutBurn400(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/c3","slug":"b2c3","purge":true}`
	rr := doDeep3(t, h, "POST", "/api/links", map[string]string{"Content-Type": "application/json"}, body)
	if rr.Code != 400 {
		t.Fatalf("expected 400, got %d, body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "只有阅后即焚链接才能设置销毁后彻底删除") {
		t.Fatalf("expected body contains 只有阅后即焚链接才能设置销毁后彻底删除, got %s", rr.Body.String())
	}
}

func TestSlugR2_BurnPurgeOK(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/c4","slug":"b2c4","burn":true,"purge":true}`
	rr := doDeep3(t, h, "POST", "/api/links", map[string]string{"Content-Type": "application/json"}, body)
	if rr.Code != 201 {
		t.Fatalf("expected 201, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

var _ = httptest.NewRequest
var _ = http.MethodPost