package handler

import (
"net/http"
"net/http/httptest"
"strings"
"testing"
)

func TestSlugR2_URLFtp400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"ftp://example.com/f","slug":"b2u1"}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("status = %d, want 400, body=%s", rr.Code, rr.Body.String())
}
if !strings.Contains(rr.Body.String(), "必须以 http://") {
t.Fatalf("body = %s, want contains 必须以 http://", rr.Body.String())
}
}

func TestSlugR2_URLJavascript400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"javascript:alert(1)","slug":"b2u2"}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("status = %d, want 400, body=%s", rr.Code, rr.Body.String())
}
}

func TestSlugR2_URLEmpty400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"","slug":"b2u3"}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("status = %d, want 400, body=%s", rr.Code, rr.Body.String())
}
if !strings.Contains(rr.Body.String(), "不能为空") {
t.Fatalf("body = %s, want contains 不能为空", rr.Body.String())
}
}

func TestSlugR2_URLTooLong400(t *testing.T) {
_, h := newDeep3Router(t)
longURL := "https://example.com/" + strings.Repeat("a", 2048)
body := `{"url":"` + longURL + `","slug":"b2u4"}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("status = %d, want 400, body=%s", rr.Code, rr.Body.String())
}
if !strings.Contains(rr.Body.String(), "过长") {
t.Fatalf("body = %s, want contains 过长", rr.Body.String())
}
}

func TestSlugR2_URLTrimmedOK(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":" https://example.com/trim ","slug":"b2u5"}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusCreated {
t.Fatalf("status = %d, want 201, body=%s", rr.Code, rr.Body.String())
}
}

func TestSlugR2_URLUppercaseScheme400(t *testing.T) {
_, h := newDeep3Router(t)
body := `{"url":"HTTPS://example.com/x","slug":"b2u6"}`
req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
req.Header.Set("Content-Type", "application/json")
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)
if rr.Code != http.StatusBadRequest {
t.Fatalf("status = %d, want 400, body=%s", rr.Code, rr.Body.String())
}
}