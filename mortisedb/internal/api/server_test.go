package api

import (
	"bytes"
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
	syncpkg "github.com/Wanfeng1028/muse/mortisedb/internal/sync"
	"github.com/Wanfeng1028/muse/mortisedb/internal/views"
	"github.com/Wanfeng1028/muse/mortisedb/internal/web"
)

func newTestServer(t *testing.T) (*store.Store, http.Handler) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	cols := []infer.Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
		{Name: "age", Type: "INTEGER"},
	}
	if err := st.EnsureTable("users", "id", cols); err != nil {
		t.Fatalf("建表失败: %v", err)
	}
	if err := st.UpsertRow("users", "id", int64(1), []string{"id", "name", "age"}, []any{int64(1), "张三", int64(30)}, "h1", "srcA"); err != nil {
		t.Fatalf("插入失败: %v", err)
	}
	if err := st.UpsertRow("users", "id", int64(2), []string{"id", "name", "age"}, []any{int64(2), "李四", int64(25)}, "h2", "srcA"); err != nil {
		t.Fatalf("插入失败: %v", err)
	}
	cfg := config.DefaultConfig()
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)
	return st, srv
}

func TestHealth(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/health", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d，body=%s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}
	if resp["status"] != "ok" {
		t.Fatalf("期望 status=ok，得到 %v", resp["status"])
	}
	if resp["version"] != Version {
		t.Fatalf("期望 version=%s，得到 %v", Version, resp["version"])
	}
}

func TestTables(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/tables", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d，body=%s", rec.Code, rec.Body.String())
	}
	var arr []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &arr); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}
	found := false
	for _, it := range arr {
		if it["name"] == "users" {
			found = true
			if it["rows"].(float64) != 2 {
				t.Fatalf("期望 users 行数 2，得到 %v", it["rows"])
			}
		}
	}
	if !found {
		t.Fatalf("未找到 users 表: %v", arr)
	}
}

func TestQueryValid(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	body := `{"sql":"SELECT id, name FROM users ORDER BY id"}`
	req := httptest.NewRequest(http.MethodPost, "/api/query", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d，body=%s", rec.Code, rec.Body.String())
	}
	var resp struct {
		Columns []string `json:"columns"`
		Rows    [][]any  `json:"rows"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}
	if len(resp.Columns) != 2 {
		t.Fatalf("期望 2 列，得到 %d", len(resp.Columns))
	}
	if len(resp.Rows) != 2 {
		t.Fatalf("期望 2 行，得到 %d", len(resp.Rows))
	}
}

func TestQueryInvalidDrop(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	body := `{"sql":"DROP TABLE users"}`
	req := httptest.NewRequest(http.MethodPost, "/api/query", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code == http.StatusOK {
		t.Fatalf("DROP TABLE 应被拒绝，却返回 200，body=%s", rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}
	if _, ok := resp["error"]; !ok {
		t.Fatalf("期望包含 error 字段，得到 %v", resp)
	}
}

func TestQueryInvalidSemicolon(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	body := `{"sql":"SELECT 1; SELECT 2"}`
	req := httptest.NewRequest(http.MethodPost, "/api/query", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code == http.StatusOK {
		t.Fatalf("含分号应被拒绝，却返回 200")
	}
}

func TestViewsEmpty(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/views", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d", rec.Code)
	}
	var arr []any
	if err := json.Unmarshal(rec.Body.Bytes(), &arr); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}
	if len(arr) != 0 {
		t.Fatalf("期望空列表，得到 %v", arr)
	}
}

func TestViewsCreateAndRunCSV(t *testing.T) {
	st, srv := newTestServer(t)
	defer st.Close()

	createBody := `{"name":"v_users","sql":"SELECT id, name FROM users","description":"用户视图"}`
	req := httptest.NewRequest(http.MethodPost, "/api/views", strings.NewReader(createBody))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("创建视图期望 200，得到 %d，body=%s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodGet, "/api/views/v_users/rows?format=csv", nil)
	rec = httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("运行视图期望 200，得到 %d，body=%s", rec.Code, rec.Body.String())
	}
	ct := rec.Header().Get("Content-Type")
	if !strings.Contains(ct, "text/csv") {
		t.Fatalf("期望 text/csv，得到 %s", ct)
	}
	reader := csv.NewReader(bytes.NewReader(rec.Body.Bytes()))
	records, err := reader.ReadAll()
	if err != nil {
		t.Fatalf("解析 CSV 失败: %v", err)
	}
	if len(records) < 1 {
		t.Fatalf("CSV 至少应有表头")
	}
	header := records[0]
	if len(header) != 2 || header[0] != "id" || header[1] != "name" {
		t.Fatalf("表头不符，得到 %v", header)
	}
	if len(records) != 3 {
		t.Fatalf("期望 1 表头 + 2 数据行，得到 %d", len(records))
	}
}

// TestMetricsAfterSync 使用内存库 + CSV 连接器做一次同步，断言 /metrics 暴露 sync_rows_total。
func TestMetricsAfterSync(t *testing.T) {
	// 准备临时 CSV
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "orders.csv")
	content := "order_id,user_id,amount,updated_at\n" +
		"1,u001,10.5,2026-01-01 00:00:00\n" +
		"2,u002,20.0,2026-01-01 00:01:00\n" +
		"3,u003,30.0,2026-01-01 00:02:00\n"
	if err := os.WriteFile(csvPath, []byte(content), 0o644); err != nil {
		t.Fatalf("写 CSV 失败: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{
			Name:        "csv_orders",
			Type:        "csv",
			Path:        csvPath,
			Table:       "orders",
			PrimaryKey:  "order_id",
			Incremental: "column:updated_at",
		},
	}

	// 确保标准指标已注册
	metrics.Default().RegisterStandard()

	if _, err := syncpkg.Sync(cfg, st, nil, "test"); err != nil {
		t.Fatalf("同步失败: %v", err)
	}

	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d，body=%s", rec.Code, rec.Body.String())
	}
	body := rec.Body.String()
	if !strings.Contains(body, "mortise_sync_rows_total") {
		t.Fatalf("/metrics 未包含 mortise_sync_rows_total，body=%s", body)
	}
	// 3 行插入
	if !strings.Contains(body, `op="inserted"`) {
		t.Fatalf("/metrics 未包含 inserted 系列，body=%s", body)
	}
	// 至少出现一次 3 计数
	if !strings.Contains(body, "} 3") {
		t.Fatalf("/metrics 未包含期望的计数值 3，body=%s", body)
	}
}

// 确保未使用的 import 被引用
var (
	_ = context.Background
	_ = fmt.Sprintf
	_ = fs.FS(nil)
	_ = strconv.Itoa
	_ = time.Now
	_ = views.Add
	_ = web.StaticFS
)
