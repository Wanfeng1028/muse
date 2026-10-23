package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestBatch_ShortURL_AllOK(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{{"url": "https://example.com/su1"}, {"url": "https://example.com/su2", "slug": "t-shorturl-1"}}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("expected 201, got %d", resp.StatusCode)
	}

	_, items := parseBatch(t, data)
	if len(items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(items))
	}

	for _, it := range items {
		if !batchOK(it) {
			t.Fatalf("expected item ok=true, got %v", it)
		}
		slug := it["slug"].(string)
		shortURL := it["short_url"].(string)
		if shortURL == "" {
			t.Error("short_url is empty")
		}
		if !strings.HasPrefix(shortURL, "http://") {
			t.Errorf("short_url %q missing http:// prefix", shortURL)
		}
		if !strings.HasSuffix(shortURL, "/"+slug) {
			t.Errorf("short_url %q does not end with /%s", shortURL, slug)
		}
	}
}

func TestBatch_ShortURL_Partial(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{{"url": "https://example.com/su3"}, {"url": "not-a-url"}}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusMultiStatus {
		t.Fatalf("expected 207, got %d", resp.StatusCode)
	}

	_, items := parseBatch(t, data)
	if len(items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(items))
	}

	for _, it := range items {
		if batchOK(it) {
			slug := it["slug"].(string)
			shortURL := it["short_url"].(string)
			if shortURL == "" {
				t.Error("short_url is empty for ok item")
			}
			if !strings.HasPrefix(shortURL, "http://") {
				t.Errorf("short_url %q missing http:// prefix", shortURL)
			}
			if !strings.HasSuffix(shortURL, "/"+slug) {
				t.Errorf("short_url %q does not end with /%s", shortURL, slug)
			}
		} else {
			errMsg := batchErr(it)
			if errMsg == "" {
				t.Error("expected non-empty error message for failed item")
			}
			if _, exists := it["short_url"]; exists {
				t.Errorf("failed item should not have short_url key, got %v", it)
			}
		}
	}
}

func TestBatch_ShortURL_AutoSlugMatches(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{{"url": "https://example.com/su4"}}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("expected 201, got %d", resp.StatusCode)
	}

	_, items := parseBatch(t, data)
	if len(items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(items))
	}

	it := items[0]
	if !batchOK(it) {
		t.Fatalf("expected item ok=true, got %v", it)
	}

	slug := it["slug"].(string)
	if slug == "" {
		t.Fatal("auto-generated slug is empty")
	}

	shortURL := it["short_url"].(string)
	if !strings.HasSuffix(shortURL, "/"+slug) {
		t.Errorf("short_url %q does not end with /%s", shortURL, slug)
	}
}
