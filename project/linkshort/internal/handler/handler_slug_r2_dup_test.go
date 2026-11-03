package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
)

func TestSlugR2_DuplicateCustomSlug400(t *testing.T) {
	_, h := newDeep3Router(t)

	first := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d1","slug":"b2dup1"}`))
	first.Header.Set("Content-Type", "application/json")
	rrFirst := httptest.NewRecorder()
	h.ServeHTTP(rrFirst, first)
	if rrFirst.Code != http.StatusCreated {
		t.Fatalf("first create: got %d, want 201, body=%s", rrFirst.Code, rrFirst.Body.String())
	}

	second := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d1-other","slug":"b2dup1"}`))
	second.Header.Set("Content-Type", "application/json")
	rrSecond := httptest.NewRecorder()
	h.ServeHTTP(rrSecond, second)
	if rrSecond.Code != http.StatusBadRequest {
		t.Fatalf("duplicate slug: got %d, want 400, body=%s", rrSecond.Code, rrSecond.Body.String())
	}
}

func TestSlugR2_DuplicateSlugBodyMentions(t *testing.T) {
	_, h := newDeep3Router(t)

	first := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d1","slug":"b2dup1"}`))
	first.Header.Set("Content-Type", "application/json")
	rrFirst := httptest.NewRecorder()
	h.ServeHTTP(rrFirst, first)
	if rrFirst.Code != http.StatusCreated {
		t.Fatalf("first create: got %d, want 201, body=%s", rrFirst.Code, rrFirst.Body.String())
	}

	second := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d1-other","slug":"b2dup1"}`))
	second.Header.Set("Content-Type", "application/json")
	rrSecond := httptest.NewRecorder()
	h.ServeHTTP(rrSecond, second)
	if rrSecond.Code != http.StatusBadRequest {
		t.Fatalf("duplicate slug: got %d, want 400, body=%s", rrSecond.Code, rrSecond.Body.String())
	}

	body := rrSecond.Body.String()
	if !strings.Contains(body, "insert link") && !strings.Contains(body, "UNIQUE") && !strings.Contains(body, "unique") {
		t.Fatalf("body does not mention insert link or UNIQUE: %q", body)
	}
}

func TestSlugR2_DuplicateCaseSensitive(t *testing.T) {
	_, h := newDeep3Router(t)

	lower := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d2","slug":"b2dup2"}`))
	lower.Header.Set("Content-Type", "application/json")
	rrLower := httptest.NewRecorder()
	h.ServeHTTP(rrLower, lower)
	if rrLower.Code != http.StatusCreated {
		t.Fatalf("lower slug: got %d, want 201, body=%s", rrLower.Code, rrLower.Body.String())
	}

	upper := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d2-upper","slug":"B2DUP2"}`))
	upper.Header.Set("Content-Type", "application/json")
	rrUpper := httptest.NewRecorder()
	h.ServeHTTP(rrUpper, upper)
	if rrUpper.Code != http.StatusCreated {
		t.Fatalf("upper slug: got %d, want 201, body=%s", rrUpper.Code, rrUpper.Body.String())
	}
}

func TestSlugR2_ReuseAfterDelete(t *testing.T) {
	_, h := newDeep3Router(t)

	first := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d3","slug":"b2dup3"}`))
	first.Header.Set("Content-Type", "application/json")
	rrFirst := httptest.NewRecorder()
	h.ServeHTTP(rrFirst, first)
	if rrFirst.Code != http.StatusCreated {
		t.Fatalf("first create: got %d, want 201, body=%s", rrFirst.Code, rrFirst.Body.String())
	}

	var created struct {
		ID float64 `json:"id"`
	}
	if err := json.Unmarshal(rrFirst.Body.Bytes(), &created); err != nil {
		t.Fatalf("unmarshal created: %v, body=%s", err, rrFirst.Body.String())
	}
	id := int64(created.ID)

	del := httptest.NewRequest("DELETE", "/api/links/"+strconv.FormatInt(id, 10), nil)
	rrDel := httptest.NewRecorder()
	h.ServeHTTP(rrDel, del)
	if rrDel.Code != http.StatusNoContent {
		t.Fatalf("delete: got %d, want 204, body=%s", rrDel.Code, rrDel.Body.String())
	}

	again := httptest.NewRequest("POST", "/api/links", strings.NewReader(`{"url":"https://example.com/d3-again","slug":"b2dup3"}`))
	again.Header.Set("Content-Type", "application/json")
	rrAgain := httptest.NewRecorder()
	h.ServeHTTP(rrAgain, again)
	if rrAgain.Code != http.StatusCreated {
		t.Fatalf("reuse after delete: got %d, want 201, body=%s", rrAgain.Code, rrAgain.Body.String())
	}
}