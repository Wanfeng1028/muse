package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newTestServerWithPurge(t *testing.T, purge bool) *httptest.Server {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open(:memory:) 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)
	cfg := &config.Config{AdminKey: testKey, BurnPurgeAfterDestroy: purge}
	srv := httptest.NewServer(NewRouter(st, cfg))
	t.Cleanup(srv.Close)
	return srv
}

func noFollowRedirectClient() *http.Client {
	return &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

func TestRedirect_BurnPurge开_首次302后彻底消失(t *testing.T) {
	srv := newTestServerWithPurge(t, true)

	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com",
		"burn": true,
		"slug": "pg-burn-1",
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", resp.StatusCode, data)
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal err=%v body=%s", err, data)
	}
	slug, _ := m["slug"].(string)
	idFloat, _ := m["id"].(float64)
	id := int64(idFloat)

	client := noFollowRedirectClient()

	r1, err := client.Get(srv.URL + "/" + slug)
	if err != nil {
		t.Fatalf("first get err=%v", err)
	}
	r1.Body.Close()
	if r1.StatusCode != http.StatusFound {
		t.Fatalf("first get status=%d want=302", r1.StatusCode)
	}

	r2, err := client.Get(srv.URL + "/" + slug)
	if err != nil {
		t.Fatalf("second get err=%v", err)
	}
	r2.Body.Close()
	if r2.StatusCode != http.StatusNotFound {
		t.Fatalf("second get status=%d want=404", r2.StatusCode)
	}

	resp, data = doJSON(t, http.MethodGet, srv.URL+"/api/links/"+strconv.FormatInt(id, 10), testKey, nil)
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("api get status=%d body=%s want=404", resp.StatusCode, data)
	}
}

func TestRedirect_BurnPurge默认关闭_行为不变(t *testing.T) {
	srv := newTestServer(t)

	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com",
		"burn": true,
		"slug": "pg-burn-2",
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", resp.StatusCode, data)
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal err=%v body=%s", err, data)
	}
	slug, _ := m["slug"].(string)

	client := noFollowRedirectClient()

	r1, err := client.Get(srv.URL + "/" + slug)
	if err != nil {
		t.Fatalf("first get err=%v", err)
	}
	r1.Body.Close()
	if r1.StatusCode != http.StatusFound {
		t.Fatalf("first get status=%d want=302", r1.StatusCode)
	}

	r2, err := client.Get(srv.URL + "/" + slug)
	if err != nil {
		t.Fatalf("second get err=%v", err)
	}
	r2.Body.Close()
	if r2.StatusCode != http.StatusGone {
		t.Fatalf("second get status=%d want=410", r2.StatusCode)
	}
}

func TestMeta_返回burnPurge开关(t *testing.T) {
	srvOn := newTestServerWithPurge(t, true)

	resp, data := doJSON(t, http.MethodGet, srvOn.URL+"/api/meta", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("meta status=%d body=%s", resp.StatusCode, data)
	}
	var metaOn map[string]any
	if err := json.Unmarshal(data, &metaOn); err != nil {
		t.Fatalf("unmarshal err=%v body=%s", err, data)
	}
	if metaOn["burn_purge_after_destroy"] != true {
		t.Fatalf("burn_purge_after_destroy=%v want=true", metaOn["burn_purge_after_destroy"])
	}

	srvOff := newTestServer(t)

	resp, data = doJSON(t, http.MethodGet, srvOff.URL+"/api/meta", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("meta status=%d body=%s", resp.StatusCode, data)
	}
	var metaOff map[string]any
	if err := json.Unmarshal(data, &metaOff); err != nil {
		t.Fatalf("unmarshal err=%v body=%s", err, data)
	}
	if metaOff["burn_purge_after_destroy"] != false {
		t.Fatalf("burn_purge_after_destroy=%v want=false", metaOff["burn_purge_after_destroy"])
	}
}
