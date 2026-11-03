package handler

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newDeep2CrudRouter(t *testing.T) http.Handler {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open 失败: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := &config.Config{}
	return NewRouter(st, cfg)
}

func doCrudDeep2(t *testing.T, h http.Handler, method, path string, body []byte) *httptest.ResponseRecorder {
	t.Helper()
	var r *http.Request
	if body == nil {
		r = httptest.NewRequest(method, path, nil)
	} else {
		r = httptest.NewRequest(method, path, bytes.NewReader(body))
		r.Header.Set("Content-Type", "application/json")
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func createDeep2(t *testing.T, h http.Handler, payload map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	b, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal 失败: %v", err)
	}
	return doCrudDeep2(t, h, http.MethodPost, "/api/links", b)
}

func TestCreateLinkSuccessDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url": "https://example.com/deep2",
	})
	if w.Code < 200 || w.Code >= 300 {
		t.Fatalf("创建成功期望 2xx，实际 %d，体=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("响应不是 JSON: %v，体=%s", err, w.Body.String())
	}
	if _, ok := resp["slug"]; !ok {
		t.Fatalf("创建响应缺少 slug 字段，体=%s", w.Body.String())
	}
	if resp["url"] != "https://example.com/deep2" {
		t.Fatalf("url 期望 https://example.com/deep2，实际 %v", resp["url"])
	}
}

func TestCreateLinkEmptyURLDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{"url": ""})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("url 空期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "url 不能为空") {
		t.Fatalf("错误信息期望包含 'url 不能为空'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkTooLongURLDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	long := "https://example.com/" + strings.Repeat("a", 2100)
	w := createDeep2(t, h, map[string]any{"url": long})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("url 超长期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "url 过长") {
		t.Fatalf("错误信息期望包含 'url 过长'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkFtpSchemeDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{"url": "ftp://example.com/file"})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("ftp scheme 期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "url 必须以 http:// 或 https:// 开头") {
		t.Fatalf("错误信息期望包含 'url 必须以 http:// 或 https:// 开头'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkSlugWithSpaceDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url":  "https://example.com/slug",
		"slug": "bad slug",
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("slug 带空格期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "slug 不合规") {
		t.Fatalf("错误信息期望包含 'slug 不合规'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkBadExpiresAtDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url":        "https://example.com/exp",
		"expires_at": "not-a-time",
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expires_at 非法期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "expires_at 格式错误") {
		t.Fatalf("错误信息期望包含 'expires_at 格式错误'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkMaxVisitsZeroDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url":        "https://example.com/mv0",
		"max_visits": 0,
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("max_visits=0 期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "max_visits 必须为正整数") {
		t.Fatalf("错误信息期望包含 'max_visits 必须为正整数'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkMaxVisitsHugeDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url":        "https://example.com/mvhuge",
		"max_visits": 100000000,
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("max_visits 极大期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "max_visits 过大") {
		t.Fatalf("错误信息期望包含 'max_visits 过大'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkBurnWithMaxVisitsDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url":        "https://example.com/burnmv",
		"burn":       true,
		"max_visits": 5,
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("burn+max_visits 同设期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "阅后即焚不能与限次访问同时设置") {
		t.Fatalf("错误信息期望包含 '阅后即焚不能与限次访问同时设置'，实际 %s", w.Body.String())
	}
}

func TestCreateLinkPurgeWithoutBurnDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := createDeep2(t, h, map[string]any{
		"url":   "https://example.com/purge",
		"burn":  false,
		"purge": true,
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("purge=true+burn=false 期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "只有阅后即焚链接才能设置销毁后彻底删除") {
		t.Fatalf("错误信息期望包含 '只有阅后即焚链接才能设置销毁后彻底删除'，实际 %s", w.Body.String())
	}
}

func createAndGetIDDeep2(t *testing.T, h http.Handler) string {
	t.Helper()
	w := createDeep2(t, h, map[string]any{"url": "https://example.com/forpatch"})
	if w.Code < 200 || w.Code >= 300 {
		t.Fatalf("准备数据失败，状态 %d，体=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("解析创建响应失败: %v", err)
	}
	id, ok := resp["id"]
	if !ok {
		t.Fatalf("创建响应缺少 id 字段，体=%s", w.Body.String())
	}
	return fmt.Sprintf("%v", id)
}

func TestPatchLinkNotFoundDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	body, _ := json.Marshal(map[string]any{"url": "https://example.com/x"})
	w := doCrudDeep2(t, h, http.MethodPatch, "/api/links/99999999", body)
	if w.Code != http.StatusNotFound {
		t.Fatalf("patch 不存在 id 期望 404，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "链接不存在") {
		t.Fatalf("错误信息期望包含 '链接不存在'，实际 %s", w.Body.String())
	}
}

func TestPatchLinkInvalidIDDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	body, _ := json.Marshal(map[string]any{"url": "https://example.com/x"})
	w := doCrudDeep2(t, h, http.MethodPatch, "/api/links/notanumber", body)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("patch 非数字 id 期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "id 非法") {
		t.Fatalf("错误信息期望包含 'id 非法'，实际 %s", w.Body.String())
	}
}

func TestPatchLinkMaxVisitsTooLargeDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	id := createAndGetIDDeep2(t, h)
	body, _ := json.Marshal(map[string]any{"max_visits": 1000001})
	w := doCrudDeep2(t, h, http.MethodPatch, "/api/links/"+id, body)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("patch max_visits>1000000 期望 400，实际 %d，体=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "max_visits 必须为正整数且不超过 1000000") {
		t.Fatalf("错误信息期望包含 'max_visits 必须为正整数且不超过 1000000'，实际 %s", w.Body.String())
	}
}

func TestPatchLinkSuccessUpdatesFieldDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	id := createAndGetIDDeep2(t, h)
	newTitle := "updated-title-deep2"
	body, _ := json.Marshal(map[string]any{"title": newTitle})
	w := doCrudDeep2(t, h, http.MethodPatch, "/api/links/"+id, body)
	if w.Code != http.StatusOK {
		t.Fatalf("patch 成功期望 200，实际 %d，体=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("patch 响应不是 JSON: %v，体=%s", err, w.Body.String())
	}
	if resp["title"] != newTitle {
		t.Fatalf("patch 后 title 期望 %s，实际 %v", newTitle, resp["title"])
	}

	getW := doCrudDeep2(t, h, http.MethodGet, "/api/links/"+id, nil)
	if getW.Code != http.StatusOK {
		t.Fatalf("GET 期望 200，实际 %d，体=%s", getW.Code, getW.Body.String())
	}
	var getResp map[string]any
	if err := json.Unmarshal(getW.Body.Bytes(), &getResp); err != nil {
		t.Fatalf("GET 响应不是 JSON: %v", err)
	}
	if getResp["title"] != newTitle {
		t.Fatalf("GET 后 title 期望 %s，实际 %v", newTitle, getResp["title"])
	}
}

func TestDeleteLinkNotFoundDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	w := doCrudDeep2(t, h, http.MethodDelete, "/api/links/99999999", nil)
	if w.Code != http.StatusNotFound {
		t.Fatalf("delete 不存在期望 404，实际 %d，体=%s", w.Code, w.Body.String())
	}
}

func TestDeleteLinkThenGetNotFoundDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	id := createAndGetIDDeep2(t, h)

	delW := doCrudDeep2(t, h, http.MethodDelete, "/api/links/"+id, nil)
	if delW.Code < 200 || delW.Code >= 300 {
		t.Fatalf("delete 成功期望 2xx，实际 %d，体=%s", delW.Code, delW.Body.String())
	}

	getW := doCrudDeep2(t, h, http.MethodGet, "/api/links/"+id, nil)
	if getW.Code != http.StatusNotFound {
		t.Fatalf("delete 后 GET 期望 404，实际 %d，体=%s", getW.Code, getW.Body.String())
	}
}

func TestListLinksStructureDeep2(t *testing.T) {
	h := newDeep2CrudRouter(t)
	createDeep2(t, h, map[string]any{"url": "https://example.com/list1"})
	w := doCrudDeep2(t, h, http.MethodGet, "/api/links", nil)
	if w.Code != http.StatusOK {
		t.Fatalf("list 期望 200，实际 %d，体=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("list 响应不是 JSON: %v，体=%s", err, w.Body.String())
	}
	if _, ok := resp["items"]; !ok {
		t.Fatalf("list 响应缺少 items 字段，体=%s", w.Body.String())
	}
	if _, ok := resp["total"]; !ok {
		t.Fatalf("list 响应缺少 total 字段，体=%s", w.Body.String())
	}
}