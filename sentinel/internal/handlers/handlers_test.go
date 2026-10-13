package handlers

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/scheduler"
	"sentinel/internal/store"
)

// testToken 测试用 Bearer token 明文。
const testToken = "test-token"

// isWhitelisted 判断路径是否属于免鉴权白名单。
func isWhitelisted(path string) bool {
	switch path {
	case "/api/healthz", "/api/readyz", "/api/health":
		return true
	}
	return strings.HasPrefix(path, "/api/status/")
}

// newTestServer 构建测试用 Server：临时库 + store + 空 notify 的 scheduler。
// 同时向 users 表插入一个 token_hash=sha256("test-token") 的用户。
func newTestServer(t *testing.T) (*Server, *store.Store) {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "test.db")
	sqlDB, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { _ = sqlDB.Close() })
	st := store.New(sqlDB)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}
	sum := sha256.Sum256([]byte(testToken))
	tokenHash := hex.EncodeToString(sum[:])
	if _, err := st.CreateUser(1, "tester", tokenHash); err != nil {
		t.Fatalf("CreateUser: %v", err)
	}
	sc := scheduler.New(st, func(webhookURL, event, name, target, at, errMsg string) {
		// 测试中通知为空实现
	}, 10, 5, 2)
	srv := New(st, sc, 2)
	return srv, st
}

// newReq 构造请求：对 /api/* 非白名单路径自动带 Bearer token。
func newReq(method, path string, body io.Reader) *http.Request {
	req := httptest.NewRequest(method, path, body)
	if strings.HasPrefix(path, "/api/") && !isWhitelisted(path) {
		req.Header.Set("Authorization", "Bearer "+testToken)
	}
	return req
}

// doJSON 发起 JSON 请求并返回响应与解码后的 map。
func doJSON(t *testing.T, h http.Handler, method, path string, body string) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()
	var rdr io.Reader
	if body != "" {
		rdr = strings.NewReader(body)
	}
	req := newReq(method, path, rdr)
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	var m map[string]any
	if rec.Body.Len() > 0 {
		_ = json.Unmarshal(rec.Body.Bytes(), &m)
	}
	return rec, m
}

// TestHealth 健康检查接口
func TestHealth(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, m := doJSON(t, srv.Routes(), http.MethodGet, "/api/health", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if m["status"] != "ok" {
		t.Fatalf("status field=%v", m["status"])
	}
}

// TestMonitorCRUD 监控目标增删改查
func TestMonitorCRUD(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	rec, m := doJSON(t, h, http.MethodPost, "/api/monitors",
		`{"name":"t","kind":"http","target":"https://example.com"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", rec.Code, rec.Body.String())
	}
	if m["kind"] != "http" || m["method"] != "GET" {
		t.Fatalf("unexpected kind/method: %v/%v", m["kind"], m["method"])
	}
	id, _ := m["id"].(float64)
	if id == 0 {
		t.Fatalf("missing id: %v", m)
	}

	// 非法 kind -> 400
	rec, _ = doJSON(t, h, http.MethodPost, "/api/monitors",
		`{"name":"bad","kind":"ftp","target":"https://example.com"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("invalid kind status=%d", rec.Code)
	}

	// 列表应含 1 条且 last_ok 为 null
	req := newReq(http.MethodGet, "/api/monitors", nil)
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list status=%d", rec.Code)
	}
	var list []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &list); err != nil {
		t.Fatalf("unmarshal list: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("list len=%d", len(list))
	}
	if v, ok := list[0]["last_ok"]; !ok || v != nil {
		t.Fatalf("last_ok should be null, got %v", v)
	}

	// 更新 interval_sec
	idPath := "/api/monitors/" + itoa(int64(id))
	rec, _ = doJSON(t, h, http.MethodPut, idPath,
		`{"name":"t","kind":"http","target":"https://example.com","interval_sec":120}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("update status=%d body=%s", rec.Code, rec.Body.String())
	}

	// 详情
	rec, _ = doJSON(t, h, http.MethodGet, idPath, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("get status=%d", rec.Code)
	}

	// 删除
	rec, _ = doJSON(t, h, http.MethodDelete, idPath, "")
	if rec.Code != http.StatusNoContent {
		t.Fatalf("delete status=%d", rec.Code)
	}
	rec, _ = doJSON(t, h, http.MethodGet, idPath, "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("get after delete status=%d", rec.Code)
	}
}

// TestManualCheck 手动检查一次
func TestManualCheck(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	rec, m := doJSON(t, h, http.MethodPost, "/api/monitors",
		`{"name":"m","kind":"http","target":"`+ts.URL+`"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", rec.Code, rec.Body.String())
	}
	id := int64(m["id"].(float64))
	idPath := "/api/monitors/" + itoa(id)

	rec, m = doJSON(t, h, http.MethodPost, idPath+"/check", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("check status=%d body=%s", rec.Code, rec.Body.String())
	}
	if m["ok"] != true {
		t.Fatalf("ok should be true, got %v", m["ok"])
	}

	rec, m = doJSON(t, h, http.MethodGet, idPath+"/checks?limit=10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("checks status=%d", rec.Code)
	}
	if total, ok := m["total"].(float64); !ok || int(total) != 1 {
		t.Fatalf("checks total=%v", m["total"])
	}
}

// TestIncidentFlow 完整翻转流程：ok -> down -> recovered
func TestIncidentFlow(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	// 可变 handler 控制返回码
	var code int = http.StatusOK
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(code)
	}))
	defer ts.Close()

	rec, m := doJSON(t, h, http.MethodPost, "/api/monitors",
		`{"name":"flip","kind":"http","target":"`+ts.URL+`","interval_sec":10}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", rec.Code, rec.Body.String())
	}
	id := int64(m["id"].(float64))
	idPath := "/api/monitors/" + itoa(id)

	// 1) ok
	rec, m = doJSON(t, h, http.MethodPost, idPath+"/check", "")
	if rec.Code != http.StatusOK || m["ok"] != true {
		t.Fatalf("first check: %d %v", rec.Code, m)
	}

	// 2) down 翻转
	code = http.StatusInternalServerError
	rec, m = doJSON(t, h, http.MethodPost, idPath+"/check", "")
	if rec.Code != http.StatusOK || m["ok"] != false {
		t.Fatalf("second check: %d %v", rec.Code, m)
	}

	// 3) recovered
	code = http.StatusOK
	rec, m = doJSON(t, h, http.MethodPost, idPath+"/check", "")
	if rec.Code != http.StatusOK || m["ok"] != true {
		t.Fatalf("third check: %d %v", rec.Code, m)
	}

	// 事件应有 1 条且已关闭
	rec, m = doJSON(t, h, http.MethodGet, "/api/incidents", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("incidents status=%d", rec.Code)
	}
	items, _ := m["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("incidents len=%d body=%s", len(items), rec.Body.String())
	}
	inc := items[0].(map[string]any)
	if inc["ended_at"] == nil || inc["ended_at"] == "" {
		t.Fatalf("ended_at should be set: %v", inc)
	}
	if d, ok := inc["downtime_sec"].(float64); !ok || d < 0 {
		t.Fatalf("downtime_sec invalid: %v", inc["downtime_sec"])
	}

	// overview: down==0, up==1
	rec, m = doJSON(t, h, http.MethodGet, "/api/overview", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("overview status=%d", rec.Code)
	}
	if m["down"].(float64) != 0 || m["up"].(float64) != 1 {
		t.Fatalf("overview unexpected: %v", m)
	}
}

// TestOverview 概览计数
func TestOverview(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	for i := 0; i < 2; i++ {
		rec, _ := doJSON(t, h, http.MethodPost, "/api/monitors",
			`{"name":"o`+itoa(int64(i))+`","kind":"http","target":"https://example.com"}`)
		if rec.Code != http.StatusCreated {
			t.Fatalf("create %d status=%d", i, rec.Code)
		}
	}
	rec, m := doJSON(t, h, http.MethodGet, "/api/overview", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("overview status=%d", rec.Code)
	}
	if m["total"].(float64) != 2 {
		t.Fatalf("total=%v", m["total"])
	}
}

// itoa 简单的整数转换，避免额外 import
func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

// 保证 context/time 引用（测试文件中避免未使用；实际 handler 可能用到）
var _ = context.Background
var _ = time.Now
