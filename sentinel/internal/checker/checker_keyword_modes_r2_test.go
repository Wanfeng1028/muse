package checker

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func newKeywordTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, err := w.Write([]byte("Hello Sentinel")); err != nil {
			t.Errorf("write response body: %v", err)
		}
	}))
}

func TestR2_CheckKeywordExact(t *testing.T) {
	srv := newKeywordTestServer(t)
	defer srv.Close()

	pass := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "Hello",
		KeywordMode:    "exact",
	})
	if pass.Ok != 1 {
		t.Fatalf("exact match failed: Ok=%d Error=%q", pass.Ok, pass.Error)
	}
	if pass.Error != "" {
		t.Fatalf("exact match returned unexpected error: %q", pass.Error)
	}

	fail := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "hello",
		KeywordMode:    "exact",
	})
	if fail.Ok != 0 {
		t.Fatalf("case-sensitive mismatch should fail: Ok=%d Error=%q", fail.Ok, fail.Error)
	}
	if !strings.Contains(fail.Error, "关键字") {
		t.Fatalf("case-sensitive mismatch error missing keyword marker: %q", fail.Error)
	}
}

func TestR2_CheckKeywordIgnorecase(t *testing.T) {
	srv := newKeywordTestServer(t)
	defer srv.Close()

	c := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "hello",
		KeywordMode:    "ignorecase",
	})
	if c.Ok != 1 {
		t.Fatalf("ignorecase match failed: Ok=%d Error=%q", c.Ok, c.Error)
	}
	if c.Error != "" {
		t.Fatalf("ignorecase match returned unexpected error: %q", c.Error)
	}
}

func TestR2_CheckKeywordRegex(t *testing.T) {
	srv := newKeywordTestServer(t)
	defer srv.Close()

	pass := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "H.llo",
		KeywordMode:    "regex",
	})
	if pass.Ok != 1 {
		t.Fatalf("regex match failed: Ok=%d Error=%q", pass.Ok, pass.Error)
	}
	if pass.Error != "" {
		t.Fatalf("regex match returned unexpected error: %q", pass.Error)
	}

	fail := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "^[0-9]+$",
		KeywordMode:    "regex",
	})
	if fail.Ok != 0 {
		t.Fatalf("regex mismatch should fail: Ok=%d Error=%q", fail.Ok, fail.Error)
	}
	if !strings.Contains(fail.Error, "关键字") {
		t.Fatalf("regex mismatch error missing keyword marker: %q", fail.Error)
	}
}

func TestR2_CheckKeywordIllegalMode(t *testing.T) {
	srv := newKeywordTestServer(t)
	defer srv.Close()

	c := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "x",
		KeywordMode:    "bogus",
	})
	if c.Ok != 0 {
		t.Fatalf("illegal keyword mode should fail: Ok=%d Error=%q", c.Ok, c.Error)
	}
	if !strings.Contains(c.Error, "关键字") {
		t.Fatalf("illegal keyword mode error missing keyword marker: %q", c.Error)
	}
}

func TestR2_CheckKeywordEmptyNoAssert(t *testing.T) {
	srv := newKeywordTestServer(t)
	defer srv.Close()

	c := Check(store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
		Keyword:        "",
		KeywordMode:    "exact",
	})
	if c.Ok != 1 {
		t.Fatalf("empty keyword should not assert and should pass: Ok=%d Error=%q", c.Ok, c.Error)
	}
	if c.Error != "" {
		t.Fatalf("empty keyword returned unexpected error: %q", c.Error)
	}
}
