package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestDocs_返回200且包含全部端点(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	defer database.Close()

	st := store.New(database)
	cfg := &config.Config{AdminKey: testKey}

	srv := httptest.NewServer(NewRouter(st, cfg))
	defer srv.Close()

	resp, body := doJSON(t, http.MethodGet, srv.URL+"/docs", "", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", resp.StatusCode)
	}
	if ct := resp.Header.Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Fatalf("Content-Type = %q, 期望包含 text/html", ct)
	}

	page := string(body)
	wants := []string{
		"/api/health",
		"/api/readyz",
		"/api/meta",
		"/api/links",
		"/api/links/{id}",
		"/api/links/{id}/qrcode.png",
		"/api/links/{id}/daily",
		"/api/stats/overview",
		"/api/stats/daily",
		"/api/stats/top-links",
		"/api/stats/top-referers",
		"/api/import",
		"/api/export.csv",
		"/{slug}",
		"/metrics",
		"X-API-Key",
		"API 文档",
	}
	for _, want := range wants {
		if !strings.Contains(page, want) {
			t.Errorf("文档页缺少子串: %q", want)
		}
	}
}
