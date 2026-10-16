package handler

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/metrics"
)

// backupSidecar 是 scripts/backup.sh 写入的备份状态记录。
type backupSidecar struct {
	OK             bool   `json:"ok"`
	File           string `json:"file"`
	FinishedAt     string `json:"finished_at"`
	IntegrityCheck string `json:"integrity_check"`
	SizeBytes      int64  `json:"size_bytes"`
	Error          string `json:"error"`
}

// BackupHealthResponse 是备份健康端点的响应结构。
type BackupHealthResponse struct {
	Status       string  `json:"status"`
	LastBackupAt *string `json:"last_backup_at"`
	LastBackupOK bool    `json:"last_backup_ok"`
	Integrity    string  `json:"integrity"`
	File         string  `json:"file"`
	AgeHours     float64 `json:"age_hours"`
	MaxAgeDays   int     `json:"max_age_days"`
	BackupDir    string  `json:"backup_dir"`
	BackupCount  int     `json:"backup_count"`
	Reason       string  `json:"reason"`
}

// countBackups 统计备份目录下 linkshort-*.db 文件个数，目录不存在时返回 0。
func countBackups(dir string) int {
	matches, err := filepath.Glob(filepath.Join(dir, "linkshort-*.db"))
	if err != nil {
		return 0
	}
	return len(matches)
}

// ReadBackupHealth 读取备份状态 sidecar 并判定当前备份健康状态。
func ReadBackupHealth(cfg *config.Config) BackupHealthResponse {
	resp := BackupHealthResponse{
		Status:       "degraded",
		LastBackupOK: false,
		MaxAgeDays:   cfg.BackupMaxAgeDays,
		BackupDir:    cfg.BackupDir,
		BackupCount:  countBackups(cfg.BackupDir),
	}

	sidecarPath := filepath.Join(cfg.BackupDir, "last-backup.json")
	raw, err := os.ReadFile(sidecarPath)
	if err != nil {
		resp.Reason = "尚未做过备份（无备份记录）"
		return resp
	}

	var sc backupSidecar
	if err := json.Unmarshal(raw, &sc); err != nil {
		resp.Reason = "备份状态记录损坏"
		return resp
	}

	resp.LastBackupOK = sc.OK
	resp.Integrity = sc.IntegrityCheck
	resp.File = sc.File
	if sc.FinishedAt != "" {
		at := sc.FinishedAt
		resp.LastBackupAt = &at
	}

	if !sc.OK {
		if sc.Error != "" {
			resp.Reason = sc.Error
		} else {
			resp.Reason = "上次备份失败"
		}
		return resp
	}

	if sc.IntegrityCheck != "ok" {
		resp.Reason = "上次备份完整性校验未通过"
		return resp
	}

	finished, err := time.Parse(time.RFC3339, sc.FinishedAt)
	if err != nil {
		resp.Reason = "备份时间格式非法"
		return resp
	}

	resp.AgeHours = time.Since(finished).Hours()

	if cfg.BackupMaxAgeDays > 0 {
		maxAge := time.Duration(cfg.BackupMaxAgeDays) * 24 * time.Hour
		if time.Since(finished) > maxAge {
			resp.Reason = "最近一次备份已超过 " + strconv.Itoa(cfg.BackupMaxAgeDays) + " 天"
			return resp
		}
	}

	resp.Status = "ok"
	resp.Reason = ""
	return resp
}

// handleBackupHealth 处理 /api/backup/health 请求。
func handleBackupHealth(w http.ResponseWriter, r *http.Request, cfg *config.Config) {
	resp := ReadBackupHealth(cfg)

	healthy := resp.Status == "ok"
	var lastSuccessUnix int64
	if resp.LastBackupOK && resp.LastBackupAt != nil {
		if t, err := time.Parse(time.RFC3339, *resp.LastBackupAt); err == nil {
			lastSuccessUnix = t.Unix()
		}
	}
	metrics.Default.SetBackupHealth(healthy, lastSuccessUnix)

	writeJSON(w, http.StatusOK, resp)
}
