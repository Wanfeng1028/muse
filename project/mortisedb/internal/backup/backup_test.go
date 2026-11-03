package backup

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// setupDB 建立测试用 MortiseDB 结构库，写入一行用户数据与一条水位线。
func setupDB(t *testing.T, path string) {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("打开库失败: %v", err)
	}
	defer db.Close()
	stmts := []string{
		`CREATE TABLE "_m_watermarks" ("source" TEXT, "table_name" TEXT, "column_name" TEXT, "value" TEXT, PRIMARY KEY("source","table_name","column_name"))`,
		`CREATE TABLE "users" ("id" INTEGER PRIMARY KEY, "name" TEXT)`,
		`INSERT INTO "users" ("id","name") VALUES (1, '张三')`,
		`INSERT INTO "users" ("id","name") VALUES (2, '李四')`,
		`INSERT INTO "_m_watermarks" ("source","table_name","column_name","value") VALUES ('csv','users','updated_at','2026-01-01 00:00:00')`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("初始化失败 %q: %v", s, err)
		}
	}
}

func TestBackupRestoreRoundTrip(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "mortise.db")
	setupDB(t, src)

	backupPath := filepath.Join(dir, "backups", "snap.db")
	meta, err := Backup(src, backupPath)
	if err != nil {
		t.Fatalf("备份失败: %v", err)
	}
	if meta.SizeBytes <= 0 {
		t.Fatalf("备份大小应大于 0，得到 %d", meta.SizeBytes)
	}
	if meta.SHA256 == "" {
		t.Fatalf("sha256 不应为空")
	}
	if _, err := os.Stat(backupPath + ".meta.json"); err != nil {
		t.Fatalf("元信息文件缺失: %v", err)
	}

	if err := Verify(backupPath); err != nil {
		t.Fatalf("校验失败: %v", err)
	}

	// 删除原库
	if err := os.Remove(src); err != nil {
		t.Fatalf("删除原库失败: %v", err)
	}

	// 恢复
	if err := Restore(backupPath, src, false); err != nil {
		t.Fatalf("恢复失败: %v", err)
	}

	// 数据一致性校验
	db, err := sql.Open("sqlite", src)
	if err != nil {
		t.Fatalf("打开恢复库失败: %v", err)
	}
	defer db.Close()

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM "users"`).Scan(&count); err != nil {
		t.Fatalf("查询行数失败: %v", err)
	}
	if count != 2 {
		t.Fatalf("期望 2 行用户，得到 %d", count)
	}
	var value string
	if err := db.QueryRow(`SELECT "value" FROM "_m_watermarks" WHERE "source"='csv'`).Scan(&value); err != nil {
		t.Fatalf("查询水位线失败: %v", err)
	}
	if value != "2026-01-01 00:00:00" {
		t.Fatalf("水位线值不符: %q", value)
	}
}

func TestRestoreRefusesNonEmptyWithoutForce(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "mortise.db")
	setupDB(t, src)

	backupPath := filepath.Join(dir, "snap.db")
	if _, err := Backup(src, backupPath); err != nil {
		t.Fatalf("备份失败: %v", err)
	}

	// 目标存在且非空，不带 force 应拒绝
	if err := Restore(backupPath, src, false); err == nil {
		t.Fatalf("非空目标应拒绝恢复")
	}

	// 带 force 应成功，且旧库留底
	if err := Restore(backupPath, src, true); err != nil {
		t.Fatalf("force 恢复失败: %v", err)
	}
	// 至少有一个 *.bak-* 文件
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("读取目录失败: %v", err)
	}
	found := false
	for _, e := range entries {
		if !e.IsDir() && len(e.Name()) > 4 && e.Name()[:4] == "mort" && contains(e.Name(), ".bak-") {
			found = true
		}
	}
	if !found {
		t.Fatalf("未找到 *.bak-* 留底文件")
	}
}

func TestVerifyRejectsBadFile(t *testing.T) {
	dir := t.TempDir()
	bad := filepath.Join(dir, "bad.db")
	if err := os.WriteFile(bad, []byte("not a sqlite file"), 0o644); err != nil {
		t.Fatalf("写坏文件失败: %v", err)
	}
	if err := Verify(bad); err == nil {
		t.Fatalf("坏文件应校验失败")
	}
}

// contains 极简子串检查，避免引入 strings。
func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
