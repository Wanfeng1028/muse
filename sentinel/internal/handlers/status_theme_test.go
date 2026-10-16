package handlers

import (
	"net/http"
	"strconv"
	"testing"
)

// TestUpdateStatusPageTheme_OK 验证更新主题成功并返回新值。
func TestUpdateStatusPageTheme_OK(t *testing.T) {
	srv, _ := newTestServer(t)
	id, err := srv.store.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	rec, resp := doJSON(t, srv.Routes(), http.MethodPut, "/api/status-pages/"+strconv.FormatInt(id, 10)+"/theme",
		"{\"theme\":\"dark\",\"accent_color\":\"#123abc\"}")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实际 %d，响应 %v", rec.Code, resp)
	}
	if resp["theme"] != "dark" {
		t.Fatalf("响应主题应为 dark，实际为 %v", resp["theme"])
	}
	if resp["accent_color"] != "#123abc" {
		t.Fatalf("响应主色应为 #123abc，实际为 %v", resp["accent_color"])
	}
}

// TestUpdateStatusPageTheme_BadBody 验证非法主题与非法主色返回 400。
func TestUpdateStatusPageTheme_BadBody(t *testing.T) {
	srv, _ := newTestServer(t)
	id, err := srv.store.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	path := "/api/status-pages/" + strconv.FormatInt(id, 10) + "/theme"

	rec, _ := doJSON(t, srv.Routes(), http.MethodPut, path, "{\"theme\":\"neon\"}")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法主题期望 400，实际 %d", rec.Code)
	}

	rec, _ = doJSON(t, srv.Routes(), http.MethodPut, path,
		"{\"theme\":\"dark\",\"accent_color\":\"zzz\"}")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法主色期望 400，实际 %d", rec.Code)
	}
}

// TestUpdateStatusPageTheme_BadID 验证非法 ID 与不存在的页面。
func TestUpdateStatusPageTheme_BadID(t *testing.T) {
	srv, _ := newTestServer(t)

	rec, _ := doJSON(t, srv.Routes(), http.MethodPut, "/api/status-pages/0/theme",
		"{\"theme\":\"dark\"}")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法 ID 期望 400，实际 %d", rec.Code)
	}

	rec, _ = doJSON(t, srv.Routes(), http.MethodPut, "/api/status-pages/99999/theme",
		"{\"theme\":\"dark\"}")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("不存在的页面期望 404，实际 %d", rec.Code)
	}
}

// TestPublicStatus_Theme 验证公开状态接口透出主题字段。
func TestPublicStatus_Theme(t *testing.T) {
	srv, _ := newTestServer(t)
	id, err := srv.store.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	if err := srv.store.UpdateStatusPageTheme(id, "dark", "#123abc"); err != nil {
		t.Fatalf("更新主题失败: %v", err)
	}

	rec, resp := doJSON(t, srv.Routes(), http.MethodGet, "/api/status/demo", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实际 %d，响应 %v", rec.Code, resp)
	}
	if resp["theme"] != "dark" {
		t.Fatalf("公开接口主题应为 dark，实际为 %v", resp["theme"])
	}
	if resp["accent_color"] != "#123abc" {
		t.Fatalf("公开接口主色应为 #123abc，实际为 %v", resp["accent_color"])
	}
}
