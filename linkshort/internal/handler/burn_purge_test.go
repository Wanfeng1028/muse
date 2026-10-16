package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"testing"
)

func TestCreate_PurgeRequiresBurn(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	resp, _ := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":   "https://example.com/x",
		"burn":  false,
		"purge": true,
	})
	defer resp.Body.Close()
	if resp.StatusCode != 400 {
		t.Fatalf("expected 400, got %d", resp.StatusCode)
	}
}

func TestRedirect_PerLinkPurge(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":   "https://example.com/x",
		"burn":  true,
		"purge": true,
		"slug":  "plp-1",
	})
	defer resp.Body.Close()
	if resp.StatusCode != 201 {
		t.Fatalf("expected 201, got %d", resp.StatusCode)
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if v, _ := m["purge_after_burn"].(bool); !v {
		t.Fatalf("expected purge_after_burn true")
	}
	idF, _ := m["id"].(float64)
	idPath := strconv.FormatInt(int64(idF), 10)

	client := noFollowRedirectClient()
	r1, err := client.Get(srv.URL + "/plp-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r1.Body)
	r1.Body.Close()
	if r1.StatusCode != 302 {
		t.Fatalf("expected 302, got %d", r1.StatusCode)
	}

	r2, err := client.Get(srv.URL + "/plp-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r2.Body)
	r2.Body.Close()
	if r2.StatusCode != 404 {
		t.Fatalf("expected 404, got %d", r2.StatusCode)
	}

	r3, _ := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+idPath, testKey, nil)
	defer r3.Body.Close()
	if r3.StatusCode != 404 {
		t.Fatalf("expected 404, got %d", r3.StatusCode)
	}
}

func TestRedirect_DefaultSoftBurn(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	resp, _ := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com/x",
		"burn": true,
		"slug": "soft-1",
	})
	defer resp.Body.Close()
	if resp.StatusCode != 201 {
		t.Fatalf("expected 201, got %d", resp.StatusCode)
	}

	client := noFollowRedirectClient()
	r1, err := client.Get(srv.URL + "/soft-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r1.Body)
	r1.Body.Close()
	if r1.StatusCode != 302 {
		t.Fatalf("expected 302, got %d", r1.StatusCode)
	}

	r2, err := client.Get(srv.URL + "/soft-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r2.Body)
	r2.Body.Close()
	if r2.StatusCode != 410 {
		t.Fatalf("expected 410, got %d", r2.StatusCode)
	}
}

func TestPatch_SetPurge(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com/x",
		"burn": true,
		"slug": "pp-1",
	})
	defer resp.Body.Close()
	if resp.StatusCode != 201 {
		t.Fatalf("expected 201, got %d", resp.StatusCode)
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	idF, _ := m["id"].(float64)
	idPath := strconv.FormatInt(int64(idF), 10)

	presp, pdata := doJSON(t, http.MethodPatch, srv.URL+"/api/links/"+idPath, testKey, map[string]any{
		"purge": true,
	})
	defer presp.Body.Close()
	if presp.StatusCode != 200 {
		t.Fatalf("expected 200, got %d", presp.StatusCode)
	}
	var pm map[string]any
	if err := json.Unmarshal(pdata, &pm); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if v, _ := pm["purge_after_burn"].(bool); !v {
		t.Fatalf("expected purge_after_burn true")
	}

	client := noFollowRedirectClient()
	r1, err := client.Get(srv.URL + "/pp-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r1.Body)
	r1.Body.Close()
	if r1.StatusCode != 302 {
		t.Fatalf("expected 302, got %d", r1.StatusCode)
	}

	r2, err := client.Get(srv.URL + "/pp-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r2.Body)
	r2.Body.Close()
	if r2.StatusCode != 404 {
		t.Fatalf("expected 404, got %d", r2.StatusCode)
	}
}

func TestRedirect_EnvPurgeStillWorks(t *testing.T) {
	srv := newTestServerWithPurge(t, true)
	defer srv.Close()

	resp, _ := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com/x",
		"burn": true,
		"slug": "env-1",
	})
	defer resp.Body.Close()
	if resp.StatusCode != 201 {
		t.Fatalf("expected 201, got %d", resp.StatusCode)
	}

	client := noFollowRedirectClient()
	r1, err := client.Get(srv.URL + "/env-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r1.Body)
	r1.Body.Close()
	if r1.StatusCode != 302 {
		t.Fatalf("expected 302, got %d", r1.StatusCode)
	}

	r2, err := client.Get(srv.URL + "/env-1")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	_, _ = io.Copy(io.Discard, r2.Body)
	r2.Body.Close()
	if r2.StatusCode != 404 {
		t.Fatalf("expected 404, got %d", r2.StatusCode)
	}
}
