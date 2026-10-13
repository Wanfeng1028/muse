package backup

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	_ "modernc.org/sqlite"

	"sentinel/internal/log"
)

// Info 描述一个备份文件。
type Info struct {
	Name      string    `json:"name"`
	Path      string    `json:"path"`
	Size      int64     `json:"size"`
	CreatedAt time.Time `json:"created_at"`
}

// Backup 通过 VACUUM INTO 生成数据库备份，并按 keep 保留最新的若干个。
// 返回备份文件路径。
func Backup(dbPath, backupDir string, keep int) (string, error) {
	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		log.Logger().Error("创建备份目录失败", "dir", backupDir, "err", err)
		return "", fmt.Errorf("创建备份目录失败: %w", err)
	}

	if keep <= 0 {
		keep = 7
	}

	// 生成目标路径；若同名文件已存在（同一秒内多次备份），追加 -2、-3… 后缀直到找到空闲名。
	base := fmt.Sprintf("sentinel-%s", time.Now().Format("20060102-150405"))
	name := base + ".db"
	dst := filepath.Join(backupDir, name)
	for i := 2; ; i++ {
		if _, err := os.Stat(dst); os.IsNotExist(err) {
			break
		}
		name = fmt.Sprintf("%s-%d.db", base, i)
		dst = filepath.Join(backupDir, name)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		log.Logger().Error("打开数据库失败", "dbPath", dbPath, "err", err)
		return "", fmt.Errorf("打开数据库失败: %w", err)
	}
	defer db.Close()

	// SQL 转义单引号。
	escaped := strings.ReplaceAll(dst, "'", "''")
	if _, err := db.Exec(fmt.Sprintf("VACUUM INTO '%s'", escaped)); err != nil {
		log.Logger().Error("VACUUM INTO 失败", "dst", dst, "err", err)
		return "", fmt.Errorf("执行备份失败: %w", err)
	}

	log.Logger().Info("备份完成", "path", dst)

	if err := prune(backupDir, keep); err != nil {
		log.Logger().Warn("修剪旧备份失败", "err", err)
	}

	return dst, nil
}

// prune 只保留最新的 keep 个备份。
func prune(dir string, keep int) error {
	list, err := List(dir)
	if err != nil {
		return err
	}
	// List 已按时间倒序。
	for i := keep; i < len(list); i++ {
		if err := os.Remove(list[i].Path); err != nil {
			log.Logger().Warn("删除旧备份失败", "path", list[i].Path, "err", err)
		} else {
			log.Logger().Info("删除旧备份", "path", list[i].Path)
		}
	}
	return nil
}

// List 列出备份目录中的 sentinel-*.db，按创建时间倒序。
func List(dir string) ([]Info, error) {
	// 始终返回非 nil 的 slice，空目录返回空 slice。
	out := []Info{}

	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return out, nil
		}
		return nil, fmt.Errorf("读取备份目录失败: %w", err)
	}

	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasPrefix(name, "sentinel-") || !strings.HasSuffix(name, ".db") {
			continue
		}
		full := filepath.Join(dir, name)
		fi, err := os.Stat(full)
		if err != nil {
			continue
		}
		out = append(out, Info{
			Name:      name,
			Path:      full,
			Size:      fi.Size(),
			CreatedAt: fi.ModTime(),
		})
	}

	sort.Slice(out, func(i, j int) bool {
		return out[i].CreatedAt.After(out[j].CreatedAt)
	})

	return out, nil
}

// Restore 用备份文件覆盖当前数据库文件。
// 校验 backupPath 必须存在且为普通文件。
func Restore(dbPath, backupPath string) error {
	if backupPath == "" {
		return fmt.Errorf("备份路径不能为空")
	}

	absDB, err := filepath.Abs(dbPath)
	if err != nil {
		return fmt.Errorf("解析数据库路径失败: %w", err)
	}
	absBackup, err := filepath.Abs(backupPath)
	if err != nil {
		return fmt.Errorf("解析备份路径失败: %w", err)
	}

	// 校验备份文件必须存在且为普通文件（非目录）。
	fi, err := os.Stat(absBackup)
	if err != nil {
		return fmt.Errorf("备份文件不存在: %w", err)
	}
	if fi.IsDir() {
		return fmt.Errorf("备份路径是目录: %s", absBackup)
	}
	if !fi.Mode().IsRegular() {
		return fmt.Errorf("备份路径不是普通文件: %s", absBackup)
	}

	// 校验 SQLite 文件魔数（前 16 字节为 "SQLite format 3\0"），防止恢复非数据库文件。
	f, err := os.Open(absBackup)
	if err != nil {
		return fmt.Errorf("打开备份文件失败: %w", err)
	}
	magic := make([]byte, 16)
	if _, err := f.Read(magic); err != nil {
		f.Close()
		return fmt.Errorf("读取备份文件头失败: %w", err)
	}
	f.Close()
	if string(magic) != "SQLite format 3\x00" {
		return fmt.Errorf("不是有效的 SQLite 数据库文件: %s", absBackup)
	}

	data, err := os.ReadFile(absBackup)
	if err != nil {
		return fmt.Errorf("读取备份文件失败: %w", err)
	}

	if err := os.WriteFile(absDB, data, 0o644); err != nil {
		return fmt.Errorf("写入数据库文件失败: %w", err)
	}

	log.Logger().Info("数据库恢复完成", "dbPath", absDB, "backupPath", absBackup)
	return nil
}
