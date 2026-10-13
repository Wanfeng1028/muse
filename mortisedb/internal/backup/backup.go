// Package backup 提供 MortiseDB 的在线备份、校验与恢复能力。
// 备份使用 SQLite 的 VACUUM INTO 语法，可在库处于 WAL 模式时获得一致性快照。
package backup

import (
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// Meta 备份元信息，写于同名 .meta.json。
type Meta struct {
	CreatedAt string `json:"created_at"`
	SourceDB  string `json:"source_db"`
	SizeBytes int64  `json:"size_bytes"`
	SHA256    string `json:"sha256"`
	Version   string `json:"version"`
}

// Version 备份格式版本。
var Version = "1.1.0"

// Backup 使用 VACUUM INTO 将 srcDBPath 一致性快照写入 dstPath。
// dstPath 存在时返回错误；写完后生成 dstPath+".meta.json"。
func Backup(srcDBPath, dstPath string) (Meta, error) {
	var meta Meta
	if strings.TrimSpace(srcDBPath) == "" {
		return meta, fmt.Errorf("源数据库路径为空")
	}
	if strings.TrimSpace(dstPath) == "" {
		return meta, fmt.Errorf("目标路径为空")
	}
	if _, err := os.Stat(srcDBPath); err != nil {
		return meta, fmt.Errorf("源数据库不存在: %w", err)
	}
	if _, err := os.Stat(dstPath); err == nil {
		return meta, fmt.Errorf("目标文件已存在: %s", dstPath)
	}
	if dir := filepath.Dir(dstPath); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return meta, fmt.Errorf("创建目标目录失败: %w", err)
		}
	}

	// 打开源库（可读写，因为 VACUUM INTO 需要读锁）
	db, err := sql.Open("sqlite", srcDBPath)
	if err != nil {
		return meta, fmt.Errorf("打开源数据库失败: %w", err)
	}
	defer db.Close()
	if err := db.Ping(); err != nil {
		return meta, fmt.Errorf("连接源数据库失败: %w", err)
	}

	// VACUUM INTO 要求目标路径为字面量；转义单引号后拼接。
	escaped := strings.ReplaceAll(dstPath, "'", "''")
	stmt := fmt.Sprintf("VACUUM INTO '%s'", escaped)
	if _, err := db.Exec(stmt); err != nil {
		return meta, fmt.Errorf("VACUUM INTO 失败: %w", err)
	}

	// 计算 sha256 与大小
	f, err := os.Open(dstPath)
	if err != nil {
		return meta, fmt.Errorf("打开备份文件失败: %w", err)
	}
	defer f.Close()
	h := sha256.New()
	size, err := io.Copy(h, f)
	if err != nil {
		return meta, fmt.Errorf("计算摘要失败: %w", err)
	}

	meta = Meta{
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
		SourceDB:  srcDBPath,
		SizeBytes: size,
		SHA256:    hex.EncodeToString(h.Sum(nil)),
		Version:   Version,
	}
	buf, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		return meta, fmt.Errorf("序列化元信息失败: %w", err)
	}
	if err := os.WriteFile(dstPath+".meta.json", buf, 0o644); err != nil {
		return meta, fmt.Errorf("写入元信息失败: %w", err)
	}
	return meta, nil
}

// Verify 校验备份文件：可只读打开、integrity_check 返回单行 ok、含 _m_watermarks 表。
func Verify(path string) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("备份路径为空")
	}
	if _, err := os.Stat(path); err != nil {
		return fmt.Errorf("备份文件不存在: %w", err)
	}
	dsn := "file:" + path + "?mode=ro"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return fmt.Errorf("打开备份失败: %w", err)
	}
	defer db.Close()
	if err := db.Ping(); err != nil {
		return fmt.Errorf("连接备份失败: %w", err)
	}

	var result string
	if err := db.QueryRow("PRAGMA integrity_check").Scan(&result); err != nil {
		return fmt.Errorf("完整性检查失败: %w", err)
	}
	if !strings.EqualFold(strings.TrimSpace(result), "ok") {
		return fmt.Errorf("完整性检查未通过: %s", result)
	}

	var name string
	err = db.QueryRow(
		`SELECT "name" FROM "sqlite_master" WHERE "type"='table' AND "name"='_m_watermarks'`,
	).Scan(&name)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return fmt.Errorf("备份缺少 _m_watermarks 表，可能是非 MortiseDB 数据库")
		}
		return fmt.Errorf("查询系统表失败: %w", err)
	}
	return nil
}

// Restore 将 backupPath 恢复到 targetPath。
// 若 targetPath 已存在且非空且未指定 force，返回错误。
// force 为真时先将旧库改名为 *.bak-<时间戳> 留底，再原子替换。
func Restore(backupPath, targetPath string, force bool) error {
	if strings.TrimSpace(backupPath) == "" || strings.TrimSpace(targetPath) == "" {
		return fmt.Errorf("备份路径或目标路径为空")
	}
	if err := Verify(backupPath); err != nil {
		return fmt.Errorf("备份校验失败: %w", err)
	}

	exists := false
	if info, err := os.Stat(targetPath); err == nil {
		if info.Size() > 0 {
			exists = true
		}
	}

	if exists && !force {
		return fmt.Errorf("目标文件已存在且非空，需使用 --force: %s", targetPath)
	}

	// force 时先将旧库改名留底
	if exists && force {
		bakPath := fmt.Sprintf("%s.bak-%s", targetPath, time.Now().UTC().Format("20060102T150405Z"))
		if err := os.Rename(targetPath, bakPath); err != nil {
			return fmt.Errorf("备份旧库失败: %w", err)
		}
	}

	if dir := filepath.Dir(targetPath); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("创建目标目录失败: %w", err)
		}
	}

	// 复制到临时文件后原子重命名
	tmpPath := targetPath + ".tmp-restore"
	if err := copyFile(backupPath, tmpPath); err != nil {
		return fmt.Errorf("复制备份失败: %w", err)
	}
	if err := os.Rename(tmpPath, targetPath); err != nil {
		return fmt.Errorf("原子替换失败: %w", err)
	}
	return nil
}

// copyFile 复制文件内容。
func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	if _, err := io.Copy(out, in); err != nil {
		return err
	}
	return out.Sync()
}
