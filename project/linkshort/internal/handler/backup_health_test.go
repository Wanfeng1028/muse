package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// newBackupHealthServer 构造带临时备份目录的测试服务。
func newBackupHealthServer(t *testing.T, tmp string, maxAgeDays int) (*httptest.Server, *config.Config) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	st := store.New(database)
	cfg := &config.Config{AdminKey: testKey, BackupDir: tmp, BackupMaxAgeDays: maxAgeDays}
	srv := httptest.NewServer(NewRouter(st, cfg))
	t.Cleanup(srv.Close)
	return srv, cfg
}

// writeSidecar 写入备份状态 sidecar 文件。
func writeSidecar(t *testing.T, dir string, content string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, "last-backup.json"), []byte(content), 0o644); err != nil {
		t.Fatalf("write sidecar: %v", err)
	}
}

// fetchBackupHealth 发起带 API Key 的请求并解析响应。
func fetchBackupHealth(t *testing.T, srv *httptest.Server) BackupHealthResponse {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, srv.URL+"/api/backup/health", nil)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("X-API-Key", testKey)
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", res.StatusCode)
	}
	var out BackupHealthResponse
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return out
}

func TestBackupHealth_OK(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)
	now := time.Now().UTC().Format(time.RFC3339)
	writeSidecar(t, tmp, fmt.Sprintf(`{"ok":true,"file":"linkshort-20240101-000000.db","finished_at":%q,"integrity_check":"ok","size_bytes":123,"error":""}`, now))

	got := fetchBackupHealth(t, srv)
	if got.Status != "ok" {
		t.Fatalf("status = %q, want ok", got.Status)
	}
	if !got.LastBackupOK {
		t.Fatalf("last_backup_ok = false, want true")
	}
	if got.Integrity != "ok" {
		t.Fatalf("integrity = %q, want ok", got.Integrity)
	}
	if got.Reason != "" {
		t.Fatalf("reason = %q, want empty", got.Reason)
	}
	if got.MaxAgeDays != 7 {
		t.Fatalf("max_age_days = %d, want 7", got.MaxAgeDays)
	}
	if got.LastBackupAt == nil {
		t.Fatalf("last_backup_at = nil, want non-nil")
	}
}

func TestBackupHealth_TooOld(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)
	old := time.Now().Add(-10 * 24 * time.Hour).UTC().Format(time.RFC3339)
	writeSidecar(t, tmp, fmt.Sprintf(`{"ok":true,"file":"linkshort-20240101-000000.db","finished_at":%q,"integrity_check":"ok","size_bytes":123,"error":""}`, old))

	got := fetchBackupHealth(t, srv)
	if got.Status != "degraded" {
		t.Fatalf("status = %q, want degraded", got.Status)
	}
	if !strings.Contains(got.Reason, "超过 7 天") {
		t.Fatalf("reason = %q, want contains 超过 7 天", got.Reason)
	}
}

func TestBackupHealth_Failed(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)
	writeSidecar(t, tmp, `{"ok":false,"file":"","finished_at":"","integrity_check":"","size_bytes":0,"error":"磁盘满了"}`)

	got := fetchBackupHealth(t, srv)
	if got.Status != "degraded" {
		t.Fatalf("status = %q, want degraded", got.Status)
	}
	if !strings.Contains(got.Reason, "磁盘满了") {
		t.Fatalf("reason = %q, want contains 磁盘满了", got.Reason)
	}
	if got.LastBackupOK {
		t.Fatalf("last_backup_ok = true, want false")
	}
}

func TestBackupHealth_IntegrityFailed(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)
	now := time.Now().UTC().Format(time.RFC3339)
	writeSidecar(t, tmp, fmt.Sprintf(`{"ok":true,"file":"linkshort-20240101-000000.db","finished_at":%q,"integrity_check":"corrupt","size_bytes":123,"error":""}`, now))

	got := fetchBackupHealth(t, srv)
	if got.Status != "degraded" {
		t.Fatalf("status = %q, want degraded", got.Status)
	}
	if got.Reason != "上次备份完整性校验未通过" {
		t.Fatalf("reason = %q, want 上次备份完整性校验未通过", got.Reason)
	}
}

func TestBackupHealth_NoSidecar(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)

	got := fetchBackupHealth(t, srv)
	if got.Status != "degraded" {
		t.Fatalf("status = %q, want degraded", got.Status)
	}
	if got.Reason != "尚未做过备份（无备份记录）" {
		t.Fatalf("reason = %q, want 尚未做过备份（无备份记录）", got.Reason)
	}
	if got.LastBackupAt != nil {
		t.Fatalf("last_backup_at = %v, want nil", *got.LastBackupAt)
	}
	if got.AgeHours != 0 {
		t.Fatalf("age_hours = %v, want 0", got.AgeHours)
	}
}

func TestBackupHealth_CorruptSidecar(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)
	writeSidecar(t, tmp, `{not json`)

	got := fetchBackupHealth(t, srv)
	if got.Status != "degraded" {
		t.Fatalf("status = %q, want degraded", got.Status)
	}
	if got.Reason != "备份状态记录损坏" {
		t.Fatalf("reason = %q, want 备份状态记录损坏", got.Reason)
	}
}

func TestBackupHealth_BackupCount(t *testing.T) {
	tmp := t.TempDir()
	srv, _ := newBackupHealthServer(t, tmp, 7)
	for _, name := range []string{"linkshort-20240101-000000.db", "linkshort-20240102-000000.db"} {
		if err := os.WriteFile(filepath.Join(tmp, name), []byte{}, 0o644); err != nil {
			t.Fatalf("write backup file: %v", err)
		}
	}

	got := fetchBackupHealth(t, srv)
	if got.BackupCount != 2 {
		t.Fatalf("backup_count = %d, want 2", got.BackupCount)
	}
}
