package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/metrics"
)

// snapshotBackupHealth 从 metrics 文本输出解析备份健康指标（替代不存在的 SnapshotBackupHealth）。
func snapshotBackupHealth(t *testing.T) (healthy bool, lastSuccess int64) {
	t.Helper()
	rec := httptest.NewRecorder()
	metrics.Default.Handler()(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	for _, line := range strings.Split(rec.Body.String(), "\n") {
		if strings.HasPrefix(line, "linkshort_backup_health_status ") {
			var v int64
			fmt.Sscanf(strings.TrimPrefix(line, "linkshort_backup_health_status "), "%d", &v)
			healthy = v == 1
		}
		if strings.HasPrefix(line, "linkshort_backup_last_success_timestamp ") {
			fmt.Sscanf(strings.TrimPrefix(line, "linkshort_backup_last_success_timestamp "), "%d", &lastSuccess)
		}
	}
	return healthy, lastSuccess
}

func writeDeepSidecar(t *testing.T, dir string, sc backupSidecar) {
	t.Helper()
	raw, err := json.Marshal(sc)
	if err != nil {
		t.Fatalf("marshal sidecar: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "last-backup.json"), raw, 0o644); err != nil {
		t.Fatalf("write sidecar: %v", err)
	}
}

func writeRawSidecar(t *testing.T, dir string, content string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, "last-backup.json"), []byte(content), 0o644); err != nil {
		t.Fatalf("write raw sidecar: %v", err)
	}
}

func touchBackup(t *testing.T, dir string, name string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, name), []byte("x"), 0o644); err != nil {
		t.Fatalf("touch backup %s: %v", name, err)
	}
}

func TestCountBackupsGlobAndMissingDir(t *testing.T) {
	dir := t.TempDir()
	touchBackup(t, dir, "linkshort-20240101.db")
	touchBackup(t, dir, "linkshort-20240102.db")
	touchBackup(t, dir, "linkshort-20240103.db")
	touchBackup(t, dir, "other-20240101.db")
	touchBackup(t, dir, "linkshort-20240101.db.tmp")

	got := countBackups(dir)
	if got != 3 {
		t.Fatalf("countBackups matched %d, want 3", got)
	}

	missing := filepath.Join(dir, "nope")
	if got := countBackups(missing); got != 0 {
		t.Fatalf("countBackups on missing dir = %d, want 0", got)
	}
}

func TestReadBackupHealthNoSidecar(t *testing.T) {
	dir := t.TempDir()
	touchBackup(t, dir, "linkshort-a.db")
	touchBackup(t, dir, "linkshort-b.db")

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.LastBackupOK {
		t.Fatalf("LastBackupOK = true, want false")
	}
	if resp.Reason != "尚未做过备份（无备份记录）" {
		t.Fatalf("Reason = %q", resp.Reason)
	}
	if resp.BackupCount != 2 {
		t.Fatalf("BackupCount = %d, want 2", resp.BackupCount)
	}
	if resp.LastBackupAt != nil {
		t.Fatalf("LastBackupAt = %v, want nil", *resp.LastBackupAt)
	}
	if resp.BackupDir != dir {
		t.Fatalf("BackupDir = %q, want %q", resp.BackupDir, dir)
	}
}

func TestReadBackupHealthCorruptSidecar(t *testing.T) {
	dir := t.TempDir()
	writeRawSidecar(t, dir, "{not json")

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.Reason != "备份状态记录损坏" {
		t.Fatalf("Reason = %q", resp.Reason)
	}
	if resp.LastBackupOK {
		t.Fatalf("LastBackupOK = true, want false")
	}
}

func TestReadBackupHealthLastBackupFailed(t *testing.T) {
	dir := t.TempDir()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             false,
		File:           "linkshort-20240101.db",
		FinishedAt:     time.Now().UTC().Format(time.RFC3339),
		IntegrityCheck: "ok",
		SizeBytes:      1024,
		Error:          "磁盘写入失败",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.LastBackupOK {
		t.Fatalf("LastBackupOK = true, want false")
	}
	if resp.Reason != "磁盘写入失败" {
		t.Fatalf("Reason = %q, want 磁盘写入失败", resp.Reason)
	}
	if resp.File != "linkshort-20240101.db" {
		t.Fatalf("File = %q", resp.File)
	}
}

func TestReadBackupHealthFailedWithoutError(t *testing.T) {
	dir := t.TempDir()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             false,
		File:           "linkshort-20240101.db",
		FinishedAt:     time.Now().UTC().Format(time.RFC3339),
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.Reason != "上次备份失败" {
		t.Fatalf("Reason = %q, want 上次备份失败", resp.Reason)
	}
	if resp.LastBackupOK {
		t.Fatalf("LastBackupOK = true, want false")
	}
}

func TestReadBackupHealthIntegrityFailed(t *testing.T) {
	dir := t.TempDir()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-20240101.db",
		FinishedAt:     time.Now().UTC().Format(time.RFC3339),
		IntegrityCheck: "failed",
		SizeBytes:      2048,
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.Reason != "上次备份完整性校验未通过" {
		t.Fatalf("Reason = %q", resp.Reason)
	}
	if resp.Integrity != "failed" {
		t.Fatalf("Integrity = %q, want failed", resp.Integrity)
	}
	if !resp.LastBackupOK {
		t.Fatalf("LastBackupOK = false, want true")
	}
}

func TestReadBackupHealthInvalidTime(t *testing.T) {
	dir := t.TempDir()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-20240101.db",
		FinishedAt:     "2024/01/01 00:00:00",
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.Reason != "备份时间格式非法" {
		t.Fatalf("Reason = %q", resp.Reason)
	}
	if resp.LastBackupAt == nil {
		t.Fatalf("LastBackupAt = nil, want non-nil")
	}
	if *resp.LastBackupAt != "2024/01/01 00:00:00" {
		t.Fatalf("LastBackupAt = %q", *resp.LastBackupAt)
	}
}

func TestReadBackupHealthExpiredBeyondMaxAge(t *testing.T) {
	dir := t.TempDir()
	old := time.Now().Add(-8 * 24 * time.Hour).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-old.db",
		FinishedAt:     old.Format(time.RFC3339),
		IntegrityCheck: "ok",
		SizeBytes:      4096,
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "degraded" {
		t.Fatalf("Status = %q, want degraded", resp.Status)
	}
	if resp.Reason != "最近一次备份已超过 7 天" {
		t.Fatalf("Reason = %q", resp.Reason)
	}
	if resp.AgeHours < 190 || resp.AgeHours > 194 {
		t.Fatalf("AgeHours = %f, want around 192", resp.AgeHours)
	}
	if resp.MaxAgeDays != 7 {
		t.Fatalf("MaxAgeDays = %d, want 7", resp.MaxAgeDays)
	}
}

func TestReadBackupHealthExactlyAtBoundary(t *testing.T) {
	dir := t.TempDir()
	// 注：精确 7 天会因测试执行耗时漂过 `>` 边界，改用 7 天减 1 小时测边界内 ok 语义
	finished := time.Now().Add(-7*24*time.Hour + time.Hour).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-edge.db",
		FinishedAt:     finished.Format(time.RFC3339),
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "ok" {
		t.Fatalf("Status = %q, want ok", resp.Status)
	}
	if resp.Reason != "" {
		t.Fatalf("Reason = %q, want empty", resp.Reason)
	}
	if resp.LastBackupOK != true {
		t.Fatalf("LastBackupOK = false, want true")
	}
}

func TestReadBackupHealthMaxAgeZeroDisablesCheck(t *testing.T) {
	dir := t.TempDir()
	veryOld := time.Now().Add(-365 * 24 * time.Hour).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-ancient.db",
		FinishedAt:     veryOld.Format(time.RFC3339),
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 0}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "ok" {
		t.Fatalf("Status = %q, want ok", resp.Status)
	}
	if resp.MaxAgeDays != 0 {
		t.Fatalf("MaxAgeDays = %d, want 0", resp.MaxAgeDays)
	}
	if resp.AgeHours < 8000 {
		t.Fatalf("AgeHours = %f, want > 8000", resp.AgeHours)
	}
}

func TestReadBackupHealthHealthy(t *testing.T) {
	dir := t.TempDir()
	touchBackup(t, dir, "linkshort-20240101.db")
	touchBackup(t, dir, "linkshort-20240102.db")
	finished := time.Now().Add(-2 * time.Hour).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-20240102.db",
		FinishedAt:     finished.Format(time.RFC3339),
		IntegrityCheck: "ok",
		SizeBytes:      8192,
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	resp := ReadBackupHealth(cfg)

	if resp.Status != "ok" {
		t.Fatalf("Status = %q, want ok", resp.Status)
	}
	if !resp.LastBackupOK {
		t.Fatalf("LastBackupOK = false, want true")
	}
	if resp.Integrity != "ok" {
		t.Fatalf("Integrity = %q, want ok", resp.Integrity)
	}
	if resp.BackupCount != 2 {
		t.Fatalf("BackupCount = %d, want 2", resp.BackupCount)
	}
	if resp.AgeHours < 1.5 || resp.AgeHours > 2.5 {
		t.Fatalf("AgeHours = %f, want around 2", resp.AgeHours)
	}
}

func TestHandleBackupHealthWritesMetricsAndJSON(t *testing.T) {
	dir := t.TempDir()
	touchBackup(t, dir, "linkshort-20240101.db")
	finished := time.Now().Add(-1 * time.Hour).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-20240101.db",
		FinishedAt:     finished.Format(time.RFC3339),
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}
	req := httptest.NewRequest(http.MethodGet, "/api/backup/health", nil)
	rec := httptest.NewRecorder()

	handleBackupHealth(rec, req, cfg)

	if rec.Code != http.StatusOK {
		t.Fatalf("status code = %d, want 200", rec.Code)
	}
	contentType := rec.Header().Get("Content-Type")
	if !strings.Contains(contentType, "application/json") {
		t.Fatalf("Content-Type = %q, want application/json", contentType)
	}

	var body BackupHealthResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	if body.Status != "ok" {
		t.Fatalf("body.Status = %q, want ok", body.Status)
	}
	if !body.LastBackupOK {
		t.Fatalf("body.LastBackupOK = false, want true")
	}
	if body.LastBackupAt == nil {
		t.Fatalf("body.LastBackupAt = nil, want non-nil")
	}
	if body.LastBackupAt != nil && *body.LastBackupAt != finished.Format(time.RFC3339) {
		t.Fatalf("body.LastBackupAt = %q, want %q", *body.LastBackupAt, finished.Format(time.RFC3339))
	}

	healthy, lastSuccess := snapshotBackupHealth(t)
	if !healthy {
		t.Fatalf("metrics healthy = false, want true")
	}
	if lastSuccess != finished.Unix() {
		t.Fatalf("metrics lastSuccess = %d, want %d", lastSuccess, finished.Unix())
	}
}

func TestHandleBackupHealthDegradedMetrics(t *testing.T) {
	dir := t.TempDir()
	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}

	req := httptest.NewRequest(http.MethodGet, "/api/backup/health", nil)
	rec := httptest.NewRecorder()

	handleBackupHealth(rec, req, cfg)

	if rec.Code != http.StatusOK {
		t.Fatalf("status code = %d, want 200", rec.Code)
	}
	var body BackupHealthResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	if body.Status != "degraded" {
		t.Fatalf("body.Status = %q, want degraded", body.Status)
	}

	healthy, lastSuccess := snapshotBackupHealth(t)
	if healthy {
		t.Fatalf("metrics healthy = true, want false")
	}
	if lastSuccess != 0 {
		t.Fatalf("metrics lastSuccess = %d, want 0", lastSuccess)
	}
}

func TestReadBackupHealthConcurrentRaceFree(t *testing.T) {
	dir := t.TempDir()
	touchBackup(t, dir, "linkshort-a.db")
	finished := time.Now().Add(-1 * time.Hour).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-a.db",
		FinishedAt:     finished.Format(time.RFC3339),
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}

	var wg sync.WaitGroup
	results := make([]BackupHealthResponse, 16)
	for i := 0; i < 16; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			results[idx] = ReadBackupHealth(cfg)
		}(i)
	}
	wg.Wait()

	for i, resp := range results {
		if resp.Status != "ok" {
			t.Fatalf("result[%d].Status = %q, want ok", i, resp.Status)
		}
		if resp.BackupCount != 1 {
			t.Fatalf("result[%d].BackupCount = %d, want 1", i, resp.BackupCount)
		}
	}
}

func TestHandleBackupHealthConcurrentRaceFree(t *testing.T) {
	dir := t.TempDir()
	finished := time.Now().Add(-30 * time.Minute).UTC()
	writeDeepSidecar(t, dir, backupSidecar{
		OK:             true,
		File:           "linkshort-concurrent.db",
		FinishedAt:     finished.Format(time.RFC3339),
		IntegrityCheck: "ok",
	})

	cfg := &config.Config{BackupDir: dir, BackupMaxAgeDays: 7}

	var wg sync.WaitGroup
	codes := make([]int, 12)
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			req := httptest.NewRequest(http.MethodGet, "/api/backup/health", nil)
			rec := httptest.NewRecorder()
			handleBackupHealth(rec, req, cfg)
			codes[idx] = rec.Code
		}(i)
	}
	wg.Wait()

	for i, code := range codes {
		if code != http.StatusOK {
			t.Fatalf("codes[%d] = %d, want 200", i, code)
		}
	}
}
