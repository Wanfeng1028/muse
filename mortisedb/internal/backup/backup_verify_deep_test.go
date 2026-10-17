package backup

import (
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// verify2MakeDB 建立一个真实的 MortiseDB 库（含 _m_watermarks 表）。
func verify2MakeDB(t *testing.T, dir, name string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	st, err := store.Open(p)
	if err != nil {
		t.Fatalf("store.Open 失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		st.DB.Close()
		t.Fatalf("Migrate 失败: %v", err)
	}
	if err := st.DB.Close(); err != nil {
		t.Fatalf("关闭源库失败: %v", err)
	}
	return p
}

// verify2ReadFile 读取整个文件内容。
func verify2ReadFile(t *testing.T, path string) []byte {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取文件失败 %s: %v", path, err)
	}
	return b
}

func TestVerify2BackupMetaFields(t *testing.T) {
	dir := t.TempDir()
	src := verify2MakeDB(t, dir, "src.db")
	dst := filepath.Join(dir, "bak.db")

	meta, err := Backup(src, dst)
	if err != nil {
		t.Fatalf("Backup 失败: %v", err)
	}

	if len(meta.SHA256) != 64 {
		t.Fatalf("SHA256 长度期望 64，实际 %d (%q)", len(meta.SHA256), meta.SHA256)
	}
	if _, err := hex.DecodeString(meta.SHA256); err != nil {
		t.Fatalf("SHA256 非合法 hex: %v (%q)", err, meta.SHA256)
	}
	if meta.SizeBytes <= 0 {
		t.Fatalf("SizeBytes 期望 > 0，实际 %d", meta.SizeBytes)
	}
	if _, err := time.Parse(time.RFC3339, meta.CreatedAt); err != nil {
		t.Fatalf("CreatedAt 无法按 RFC3339 解析: %v (%q)", err, meta.CreatedAt)
	}
	if meta.Version != Version {
		t.Fatalf("Version 期望 %q，实际 %q", Version, meta.Version)
	}
	if meta.SourceDB != src {
		t.Fatalf("SourceDB 期望 %q，实际 %q", src, meta.SourceDB)
	}

	metaPath := dst + ".meta.json"
	if _, err := os.Stat(metaPath); err != nil {
		t.Fatalf("元信息文件不存在 %s: %v", metaPath, err)
	}
	if !strings.HasSuffix(metaPath, ".meta.json") {
		t.Fatalf("元信息文件名异常: %s", metaPath)
	}
}

func TestVerify2TamperedPayloadRejected(t *testing.T) {
	dir := t.TempDir()
	src := verify2MakeDB(t, dir, "src.db")
	bak := filepath.Join(dir, "bak.db")

	if _, err := Backup(src, bak); err != nil {
		t.Fatalf("Backup 失败: %v", err)
	}

	data := verify2ReadFile(t, bak)
	if len(data) <= 100 {
		t.Fatalf("备份文件过小，无法在第 100 字节篡改: %d", len(data))
	}
	tampered := filepath.Join(dir, "tampered.db")
	data[100] ^= 0xFF
	if err := os.WriteFile(tampered, data, 0o644); err != nil {
		t.Fatalf("写入篡改文件失败: %v", err)
	}

	if err := Verify(tampered); err == nil {
		t.Fatalf("篡改后的备份竟然通过 Verify")
	}
}

func TestVerify2TruncatedFileRejected(t *testing.T) {
	dir := t.TempDir()
	src := verify2MakeDB(t, dir, "src.db")
	bak := filepath.Join(dir, "bak.db")

	if _, err := Backup(src, bak); err != nil {
		t.Fatalf("Backup 失败: %v", err)
	}

	data := verify2ReadFile(t, bak)
	if len(data) < 100 {
		t.Fatalf("备份文件过小，无法截断到 100 字节: %d", len(data))
	}
	trunc := filepath.Join(dir, "trunc.db")
	if err := os.WriteFile(trunc, data[:100], 0o644); err != nil {
		t.Fatalf("写入截断文件失败: %v", err)
	}

	if err := Verify(trunc); err == nil {
		t.Fatalf("截断后的备份竟然通过 Verify")
	}
}

func TestVerify2DirectoryRejected(t *testing.T) {
	dir := t.TempDir()
	if err := Verify(dir); err == nil {
		t.Fatalf("对目录调用 Verify 竟然成功")
	}
}

func TestVerify2BackupNonexistentSource(t *testing.T) {
	dir := t.TempDir()
	missing := filepath.Join(dir, "nope.db")
	dst := filepath.Join(dir, "out.db")

	if _, err := Backup(missing, dst); err == nil {
		t.Fatalf("对不存在源库的 Backup 竟然成功")
	}
	if _, err := os.Stat(dst); !os.IsNotExist(err) {
		t.Fatalf("失败备份不应创建目标文件，stat err=%v", err)
	}
}

func TestVerify2RestoreEmptyExistingTargetNoForce(t *testing.T) {
	dir := t.TempDir()
	src := verify2MakeDB(t, dir, "src.db")
	bak := filepath.Join(dir, "bak.db")

	if _, err := Backup(src, bak); err != nil {
		t.Fatalf("Backup 失败: %v", err)
	}

	target := filepath.Join(dir, "target.db")
	if err := os.WriteFile(target, []byte{}, 0o644); err != nil {
		t.Fatalf("创建空目标文件失败: %v", err)
	}

	if err := Restore(bak, target, false); err != nil {
		t.Fatalf("对空目标文件 Restore 失败: %v", err)
	}
	if err := Verify(target); err != nil {
		t.Fatalf("恢复后的目标库 Verify 失败: %v", err)
	}
}

func TestVerify2CopyStillVerifies(t *testing.T) {
	dir := t.TempDir()
	src := verify2MakeDB(t, dir, "src.db")
	bak := filepath.Join(dir, "bak.db")

	if _, err := Backup(src, bak); err != nil {
		t.Fatalf("Backup 失败: %v", err)
	}

	data := verify2ReadFile(t, bak)
	copied := filepath.Join(dir, "copied.db")
	if err := os.WriteFile(copied, data, 0o644); err != nil {
		t.Fatalf("复制备份文件失败: %v", err)
	}

	if err := Verify(copied); err != nil {
		t.Fatalf("复制后的备份 Verify 失败: %v", err)
	}
}
