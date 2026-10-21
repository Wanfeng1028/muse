package handlers

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

// newSLATestServer 创建内存数据库、store 和测试用的 Server（避开包内已有的 newTestServer）
func newSLATestServer(t *testing.T) (*Server, *store.Store, *sql.DB) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存数据库失败: %v", err)
	}
	st := store.New(database)
	srv := &Server{store: st}
	return srv, st, database
}

// insertMonitor 往 monitors 表插入一条记录，返回自增 ID
func insertMonitor(t *testing.T, database *sql.DB) int64 {
	t.Helper()
	res, err := database.Exec("INSERT INTO monitors (name, target, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))", "test-monitor", "https://example.com")
	if err != nil {
		t.Fatalf("插入 monitor 失败: %v", err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		t.Fatalf("获取 monitor ID 失败: %v", err)
	}
	return id
}

// insertChecks 往 checks 表插入指定数量的记录
func insertChecks(t *testing.T, database *sql.DB, monitorID int64, count int, ok bool) {
	t.Helper()
	for i := 0; i < count; i++ {
		checkedAt := time.Date(2024, 3, 1+i, 10, 0, 0, 0, time.UTC).Format("2006-01-02 15:04:05")
		_, err := database.Exec(
			"INSERT INTO checks (monitor_id, checked_at, ok, latency_ms) VALUES (?, ?, ?, ?)",
			monitorID, checkedAt, ok, 100+i,
		)
		if err != nil {
			t.Fatalf("插入 check 失败: %v", err)
		}
	}
}

// slaResponse 用于解析 SLA JSON 响应
type slaResponse struct {
	Month     string  `json:"month"`
	UptimePct float64 `json:"uptime_pct"`
}

func TestSLAAPI_JSON(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	monitorID := insertMonitor(t, database)
	insertChecks(t, database, monitorID, 10, true)

	req := httptest.NewRequest("GET", "/api/monitors/" + fmt.Sprintf("%d", monitorID) + "/sla?month=2024-03", nil)
	req.SetPathValue("id", fmt.Sprintf("%d", monitorID))
	rec := httptest.NewRecorder()
	srv.handleMonitorSLAJSON(rec, req)
	resp := rec.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200, 得到 %d", resp.StatusCode)
	}

	var body slaResponse
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}

	if body.Month != "2024-03" {
		t.Errorf("期望 month 为 2024-03, 得到 %s", body.Month)
	}
	if body.UptimePct != 100 {
		t.Errorf("期望 uptime_pct 为 100, 得到 %f", body.UptimePct)
	}
}

func TestSLAAPI_CSV(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	monitorID := insertMonitor(t, database)
	insertChecks(t, database, monitorID, 10, true)

	req := httptest.NewRequest("GET", "/api/monitors/" + fmt.Sprintf("%d", monitorID) + "/sla?month=2024-03&format=csv", nil)
	req.SetPathValue("id", fmt.Sprintf("%d", monitorID))
	rec := httptest.NewRecorder()
	srv.handleMonitorSLAJSON(rec, req)
	resp := rec.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200, 得到 %d", resp.StatusCode)
	}

	contentType := resp.Header.Get("Content-Type")
	if !strings.Contains(contentType, "text/csv") {
		t.Errorf("期望 Content-Type 包含 text/csv, 得到 %s", contentType)
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("读取响应体失败: %v", err)
	}
	content := string(bodyBytes)
	// 去除 UTF-8 BOM
	content = strings.TrimPrefix(content, "\uFEFF")
	lines := strings.Split(content, "\n")
	if len(lines) == 0 {
		t.Fatal("CSV 响应为空")
	}
	header := strings.TrimSpace(lines[0])
	expectedHeader := "date,uptime_pct,p95_latency_ms,total_checks,downtime_sec"
	if header != expectedHeader {
		t.Errorf("CSV 表头不匹配: 得到 %q, 期望 %q", header, expectedHeader)
	}
}

func TestSLAAPI_BadMonth(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	monitorID := insertMonitor(t, database)

	req := httptest.NewRequest("GET", "/api/monitors/" + fmt.Sprintf("%d", monitorID) + "/sla?month=13", nil)
	req.SetPathValue("id", fmt.Sprintf("%d", monitorID))
	rec := httptest.NewRecorder()
	srv.handleMonitorSLAJSON(rec, req)
	resp := rec.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("期望状态码 400, 得到 %d", resp.StatusCode)
	}
}

func TestSLAAPI_NotFound(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	// 直调 handler：必须用 SetPathValue 注入路径参数，否则 PathValue 为空、
	// parsePathID 失败，永远走不到 404 分支（httptest.NewServer 包 handler
	// 没有路由 pattern 匹配，PathValue 恒为空）。
	req := httptest.NewRequest("GET", "/api/monitors/999/sla?month=2024-03", nil)
	req.SetPathValue("id", "999")
	rec := httptest.NewRecorder()
	srv.handleMonitorSLAJSON(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望状态码 404, 得到 %d", rec.Code)
	}
}
