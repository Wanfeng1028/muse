package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestSync2_MalformedJSON(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	cfg := config.DefaultConfig()
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	req := httptest.NewRequest("POST", "/api/sync", strings.NewReader("{"))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d (body=%s)", rec.Code, rec.Body.String())
	}
}

func TestSync2_UnknownSource(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	cfg := config.DefaultConfig()
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	body := `{"sources":["nope"]}`
	req := httptest.NewRequest("POST", "/api/sync", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected status 500, got %d (body=%s)", rec.Code, rec.Body.String())
	}
}

func TestSync2_EmptySourcesSyncsAll(t *testing.T) {
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "s1.csv")
	if err := os.WriteFile(csvPath, []byte("id,name\n1,Alice\n2,Bob\n"), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Path: csvPath, Table: "t1", PrimaryKey: "id"},
	}
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	body := `{"sources":[]}`
	req := httptest.NewRequest("POST", "/api/sync", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d (body=%s)", rec.Code, rec.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v (body=%s)", err, rec.Body.String())
	}
	if _, ok := resp["stats"]; !ok {
		t.Fatalf("expected response to contain 'stats' key, got %v", resp)
	}

	count, err := st.TableCount("t1")
	if err != nil {
		t.Fatalf("table count t1: %v", err)
	}
	if count != 2 {
		t.Fatalf("expected t1 row count 2, got %d", count)
	}
}

func TestSync2_DefaultJobName(t *testing.T) {
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "s1.csv")
	if err := os.WriteFile(csvPath, []byte("id,name\n1,Alice\n2,Bob\n"), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Path: csvPath, Table: "t1", PrimaryKey: "id"},
	}
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	body := `{"sources":["s1"]}`
	req := httptest.NewRequest("POST", "/api/sync", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d (body=%s)", rec.Code, rec.Body.String())
	}

	runs, err := st.ListRuns(10)
	if err != nil {
		t.Fatalf("list runs: %v", err)
	}
	if len(runs) == 0 {
		t.Fatalf("expected at least one run record, got none")
	}
	if !strings.Contains(runs[0].Job, "manual") {
		t.Fatalf("expected latest run job to contain 'manual', got %q", runs[0].Job)
	}
}

func TestSync2_SpecificSourcesOnly(t *testing.T) {
	dir := t.TempDir()
	csv1 := filepath.Join(dir, "s1.csv")
	csv2 := filepath.Join(dir, "s2.csv")
	if err := os.WriteFile(csv1, []byte("id,name\n1,Alice\n2,Bob\n"), 0o644); err != nil {
		t.Fatalf("write csv1: %v", err)
	}
	if err := os.WriteFile(csv2, []byte("id,name\n9,Zed\n"), 0o644); err != nil {
		t.Fatalf("write csv2: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Path: csv1, Table: "t1", PrimaryKey: "id"},
		{Name: "s2", Type: "csv", Path: csv2, Table: "t2", PrimaryKey: "id"},
	}
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	body := `{"sources":["s1"]}`
	req := httptest.NewRequest("POST", "/api/sync", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d (body=%s)", rec.Code, rec.Body.String())
	}

	count1, err := st.TableCount("t1")
	if err != nil {
		t.Fatalf("table count t1: %v", err)
	}
	if count1 != 2 {
		t.Fatalf("expected t1 row count 2, got %d", count1)
	}

	count2, err := st.TableCount("t2")
	if err != nil {
		if !strings.Contains(err.Error(), "no such table") {
			t.Fatalf("table count t2 unexpected error: %v", err)
		}
		// t2 从未被同步创建，表不存在即等价于 0 行，符合"只同步了指定源"的预期
	} else if count2 != 0 {
		t.Fatalf("expected t2 row count 0, got %d", count2)
	}
}

func TestSync2_SourcesListsConfigured(t *testing.T) {
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "s1.csv")
	if err := os.WriteFile(csvPath, []byte("id,name\n1,Alice\n"), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Path: csvPath, Table: "t1", PrimaryKey: "id"},
	}
	logger := log.New(io.Discard, "info")
	srv := NewServer(st, cfg, logger)

	req := httptest.NewRequest("GET", "/api/sources", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d (body=%s)", rec.Code, rec.Body.String())
	}

	var arr []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &arr); err != nil {
		t.Fatalf("decode response: %v (body=%s)", err, rec.Body.String())
	}
	if len(arr) != 1 {
		t.Fatalf("expected 1 source, got %d", len(arr))
	}
	found := false
	for _, v := range arr[0] {
		if s, ok := v.(string); ok && s == "s1" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected source entry to contain value 's1', got %v", arr[0])
	}
}
