package backup

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"

	"sentinel/internal/db"
)

// newTestDB 在临时目录中创建一个真实的 SQLite 库并写入一行数据
func newTestDB(t *testing.T) (string, string) {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	sqlDB, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	if _, err := sqlDB.Exec(`CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)`); err != nil {
		sqlDB.Close()
		t.Fatalf("建表失败: %v", err)
	}
	if _, err := sqlDB.Exec(`INSERT INTO items (name) VALUES ('first')`); err != nil {
		sqlDB.Close()
		t.Fatalf("插入失败: %v", err)
	}
	if err := sqlDB.Close(); err != nil {
		t.Fatalf("关闭数据库失败: %v", err)
	}
	return dir, dbPath
}

// countRows 打开数据库并统计 items 行数
func countRows(t *testing.T, path string) int {
	t.Helper()
	sqlDB, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	defer sqlDB.Close()
	var n int
	if err := sqlDB.QueryRow(`SELECT COUNT(*) FROM items`).Scan(&n); err != nil {
		t.Fatalf("统计行数失败: %v", err)
	}
	return n
}

func TestBackupAndPrune(t *testing.T) {
	dir, dbPath := newTestDB(t)
	backupDir := filepath.Join(dir, "backups")
	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		t.Fatalf("创建备份目录失败: %v", err)
	}

	for i := 0; i < 3; i++ {
		if _, err := Backup(dbPath, backupDir, 2); err != nil {
			t.Fatalf("第 %d 次备份失败: %v", i+1, err)
		}
	}

	infos, err := List(backupDir)
	if err != nil {
		t.Fatalf("列出备份失败: %v", err)
	}
	if len(infos) != 2 {
		t.Fatalf("期望保留 2 个备份，实际 %d", len(infos))
	}

	// 验证每个备份文件都是合法 sqlite 且可查询
	for _, info := range infos {
		sqlDB, err := sql.Open("sqlite", info.Path)
		if err != nil {
			t.Fatalf("打开备份 %s 失败: %v", info.Path, err)
		}
		var n int
		if err := sqlDB.QueryRow(`SELECT COUNT(*) FROM items`).Scan(&n); err != nil {
			sqlDB.Close()
			t.Fatalf("查询备份 %s 失败: %v", info.Path, err)
		}
		sqlDB.Close()
		if n != 1 {
			t.Fatalf("备份 %s 行数期望 1，实际 %d", info.Path, n)
		}
	}
}

func TestRestore(t *testing.T) {
	dir, dbPath := newTestDB(t)
	backupDir := filepath.Join(dir, "backups")
	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		t.Fatalf("创建备份目录失败: %v", err)
	}

	backupPath, err := Backup(dbPath, backupDir, 5)
	if err != nil {
		t.Fatalf("备份失败: %v", err)
	}

	// 往原库再插一行
	sqlDB, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	if _, err := sqlDB.Exec(`INSERT INTO items (name) VALUES ('second')`); err != nil {
		sqlDB.Close()
		t.Fatalf("插入失败: %v", err)
	}
	if err := sqlDB.Close(); err != nil {
		t.Fatalf("关闭数据库失败: %v", err)
	}

	if got := countRows(t, dbPath); got != 2 {
		t.Fatalf("恢复前行数期望 2，实际 %d", got)
	}

	if err := Restore(dbPath, backupPath); err != nil {
		t.Fatalf("恢复失败: %v", err)
	}

	if got := countRows(t, dbPath); got != 1 {
		t.Fatalf("恢复后行数期望 1，实际 %d", got)
	}
}

func TestRestorePathTraversal(t *testing.T) {
	dir, dbPath := newTestDB(t)
	backupDir := filepath.Join(dir, "backups")
	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		t.Fatalf("创建备份目录失败: %v", err)
	}

	if err := Restore(dbPath, "/etc/passwd"); err == nil {
		t.Fatalf("期望拒绝越权路径 /etc/passwd")
	}

	if err := Restore(dbPath, backupDir+"/../evil.db"); err == nil {
		t.Fatalf("期望拒绝包含 .. 的路径")
	}
}

func TestListEmpty(t *testing.T) {
	dir := t.TempDir()
	infos, err := List(dir)
	if err != nil {
		t.Fatalf("列出空目录失败: %v", err)
	}
	if infos == nil {
		t.Fatalf("期望非 nil 空 slice")
	}
	if len(infos) != 0 {
		t.Fatalf("期望空 slice，实际长度 %d", len(infos))
	}
}
