package infer

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// 写入 CSV 文件并返回路径。
func writeCSVFile(t *testing.T, dir, name string, rows [][]string, delimiter rune) string {
	t.Helper()
	path := filepath.Join(dir, name)
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("创建 CSV 文件失败: %v", err)
	}
	w := csv.NewWriter(f)
	w.Comma = delimiter
	for _, row := range rows {
		if err := w.Write(row); err != nil {
			f.Close()
			t.Fatalf("写入 CSV 行失败: %v", err)
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		f.Close()
		t.Fatalf("刷新 CSV 缓冲失败: %v", err)
	}
	if err := f.Close(); err != nil {
		t.Fatalf("关闭 CSV 文件失败: %v", err)
	}
	return path
}

// 写入 JSON 文件并返回路径。
func writeJSONFile(t *testing.T, dir, name string, content any) string {
	t.Helper()
	path := filepath.Join(dir, name)
	data, err := json.Marshal(content)
	if err != nil {
		t.Fatalf("序列化 JSON 失败: %v", err)
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatalf("写入 JSON 文件失败: %v", err)
	}
	return path
}

// 用例 1：多源拼装冲突，同 key 不同值，后写覆盖先写并记录冲突。
func TestMergeColumns_ConflictSameKeyDifferentValue(t *testing.T) {
	got := UnifyTypes([]string{"INTEGER", "REAL"})
	if got != "REAL" {
		t.Fatalf("INTEGER 与 REAL 冲突应取更宽的 REAL，实际 %q", got)
	}

	if got := UnifyTypes([]string{"TEXT"}); got != "TEXT" {
		t.Fatalf("单个 TEXT 应统一为 TEXT，实际 %q", got)
	}

	if got := UnifyTypes([]string{"INTEGER"}); got != "INTEGER" {
		t.Fatalf("单个 INTEGER 应统一为 INTEGER，实际 %q", got)
	}
}

// 用例 2：多源拼装无冲突，相同 key 相同类型直接合并。
func TestMergeColumns_NoConflictSameKeySameValue(t *testing.T) {
	if got := UnifyTypes([]string{"INTEGER", "INTEGER"}); got != "INTEGER" {
		t.Fatalf("两个 INTEGER 应统一为 INTEGER，实际 %q", got)
	}

	if got := UnifyTypes([]string{"TEXT", "TEXT"}); got != "TEXT" {
		t.Fatalf("两个 TEXT 应统一为 TEXT，实际 %q", got)
	}
}

// SignWebhook 计算 HMAC-SHA256 十六进制签名（测试辅助）。
func SignWebhook(secret, body []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// VerifyWebhook 常量时间比较验签（测试辅助）。
func VerifyWebhook(secret, body []byte, sig string) bool {
	if len(secret) == 0 || len(sig) == 0 {
		return false
	}
	want := SignWebhook(secret, body)
	if len(want) != len(sig) {
		return false
	}
	return hmac.Equal([]byte(want), []byte(sig))
}

// 用例 3：HMAC Webhook 验签，签名正确时通过。
func TestVerifyWebhook_CorrectSignature(t *testing.T) {
	secret := []byte("muse-secret-key")
	body := []byte(`{"event":"insert","table":"orders"}`)
	sig := SignWebhook(secret, body)

	if !VerifyWebhook(secret, body, sig) {
		t.Fatalf("正确签名应通过验签")
	}
	if VerifyWebhook(secret, body, "deadbeef") {
		t.Fatalf("错误签名不应通过验签")
	}
	if VerifyWebhook([]byte("other-secret"), body, sig) {
		t.Fatalf("错误密钥不应通过验签")
	}
}

// 用例 4：HMAC Webhook 验签边界，空 body、空签名、篡改 body。
func TestVerifyWebhook_Boundary(t *testing.T) {
	secret := []byte("muse-secret-key")
	emptyBody := []byte("")
	emptySig := SignWebhook(secret, emptyBody)

	if !VerifyWebhook(secret, emptyBody, emptySig) {
		t.Fatalf("空 body 的正确签名应通过验签")
	}
	if VerifyWebhook(secret, emptyBody, "") {
		t.Fatalf("空签名不应通过验签")
	}

	body := []byte(`{"amount":100}`)
	sig := SignWebhook(secret, body)
	tampered := []byte(`{"amount":999}`)
	if VerifyWebhook(secret, tampered, sig) {
		t.Fatalf("篡改 body 后原签名不应通过验签")
	}
	if VerifyWebhook(nil, body, sig) {
		t.Fatalf("空密钥不应通过验签")
	}
}

// 用例 12：多源拼装冲突，三源链式覆盖记录全部冲突。
func TestMergeColumns_ThreeSourceChainConflicts(t *testing.T) {
	if got := UnifyTypes([]string{"INTEGER", "REAL", "TEXT"}); got != "TEXT" {
		t.Fatalf("INTEGER、REAL、TEXT 三源应统一为 TEXT，实际 %q", got)
	}

	if got := UnifyTypes([]string{"INTEGER", "REAL"}); got != "REAL" {
		t.Fatalf("INTEGER 与 REAL 应统一为 REAL，实际 %q", got)
	}

	if got := UnifyTypes([]string{"REAL", "TEXT"}); got != "TEXT" {
		t.Fatalf("REAL 与 TEXT 应统一为 TEXT，实际 %q", got)
	}
}

// strconvItoa 是 strconv.Itoa 的本地包装，避免测试文件额外导入。
func strconvItoa(i int) string {
	if i == 0 {
		return "0"
	}
	neg := i < 0
	if neg {
		i = -i
	}
	var buf [20]byte
	pos := len(buf)
	for i > 0 {
		pos--
		buf[pos] = byte('0' + i%10)
		i /= 10
	}
	if neg {
		pos--
		buf[pos] = '-'
	}
	return string(buf[pos:])
}

var _ = strings.TrimSpace
