package checker

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestR2_CheckMethodLowercaseNormalized(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusMethodNotAllowed)
	}))
	defer ts.Close()

	m := store.Monitor{
		ID:             1,
		Kind:           "http",
		Target:         ts.URL,
		Method:         "post",
		TimeoutSec:     2,
		ExpectedStatus: 200,
	}

	c := Check(m)
	if c.Ok != 1 {
		t.Fatalf("expected Ok=1 for lowercase method normalized to POST, got Ok=%d, status=%d, error=%q", c.Ok, c.StatusCode.Int64, c.Error)
	}
	if !c.StatusCode.Valid || c.StatusCode.Int64 != 200 {
		t.Fatalf("expected valid status code 200, got valid=%v value=%d", c.StatusCode.Valid, c.StatusCode.Int64)
	}
}

func TestR2_CheckMethodDefaultGET(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusMethodNotAllowed)
	}))
	defer ts.Close()

	m := store.Monitor{
		ID:             2,
		Kind:           "http",
		Target:         ts.URL,
		Method:         "",
		TimeoutSec:     2,
		ExpectedStatus: 200,
	}

	c := Check(m)
	if c.Ok != 0 {
		t.Fatalf("expected Ok=0 for default GET against POST-only server, got Ok=%d, status=%d, error=%q", c.Ok, c.StatusCode.Int64, c.Error)
	}
	if !c.StatusCode.Valid || c.StatusCode.Int64 != 405 {
		t.Fatalf("expected valid status code 405, got valid=%v value=%d", c.StatusCode.Valid, c.StatusCode.Int64)
	}
}

func TestR2_CheckStatusMismatchMessage(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer ts.Close()

	m := store.Monitor{
		ID:             3,
		Kind:           "http",
		Target:         ts.URL,
		Method:         http.MethodGet,
		TimeoutSec:     2,
		ExpectedStatus: 200,
	}

	c := Check(m)
	if c.Ok != 0 {
		t.Fatalf("expected Ok=0 for status mismatch, got Ok=%d, status=%d, error=%q", c.Ok, c.StatusCode.Int64, c.Error)
	}
	if !strings.Contains(c.Error, "期望 200") {
		t.Fatalf("expected error to contain expected status part, got error=%q", c.Error)
	}
	if !strings.Contains(c.Error, "实际 503") {
		t.Fatalf("expected error to contain actual status part, got error=%q", c.Error)
	}
}
