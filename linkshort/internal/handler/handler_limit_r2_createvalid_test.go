package handler

import (
"net/http"
"net/http/httptest"
"strings"
"testing"
)

func TestLimitR2_CreateMaxVisitsZero400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"https://example.com/z1","slug":"b2cz1","max_visits":0}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("expected 400, got %d body=%s", rr.Code, rr.Body.String())
}
if !strings.Contains(rr.Body.String(), "必须为正整数") {
t.Fatalf("expected body contains 必须为正整数, got %s", rr.Body.String())
}
}

func TestLimitR2_CreateMaxVisitsNegative400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"https://example.com/z2","slug":"b2cz2","max_visits":-5}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("expected 400, got %d body=%s", rr.Code, rr.Body.String())
}
}

func TestLimitR2_CreateMaxVisitsTooLarge400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"https://example.com/z3","slug":"b2cz3","max_visits":1000001}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("expected 400, got %d body=%s", rr.Code, rr.Body.String())
}
if !strings.Contains(rr.Body.String(), "过大") {
t.Fatalf("expected body contains 过大, got %s", rr.Body.String())
}
}

func TestLimitR2_CreateMaxVisitsBoundary1000000(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"https://example.com/z4","slug":"b2cz4","max_visits":1000000}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusCreated {
t.Fatalf("expected 201, got %d body=%s", rr.Code, rr.Body.String())
}
}

func TestLimitR2_CreateBurnMaxVisits5Rejected(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"https://example.com/z5","slug":"b2cz5","burn":true,"max_visits":5}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("expected 400, got %d body=%s", rr.Code, rr.Body.String())
}
if !strings.Contains(rr.Body.String(), "阅后即焚不能与限次访问同时设置") {
t.Fatalf("expected body contains 阅后即焚不能与限次访问同时设置, got %s", rr.Body.String())
}
}