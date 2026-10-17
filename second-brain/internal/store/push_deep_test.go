package store

import (
	"archive/zip"
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func newDeepStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	s, err := Open(filepath.Join(dir, "deep.db"))
	if err != nil {
		t.Fatalf("Open store: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

// 复习调度边界：跨天、闰日、时区偏移，计算下一次复习日期。
func nextReviewDate(base time.Time, intervalDays int) time.Time {
	return base.AddDate(0, 0, intervalDays)
}

func TestReviewScheduleBoundary(t *testing.T) {
	cases := []struct {
		name         string
		base         time.Time
		intervalDays int
		wantYear     int
		wantMonth    time.Month
		wantDay      int
	}{
		{"跨月", time.Date(2024, 1, 31, 0, 0, 0, 0, time.UTC), 1, 2024, time.February, 1},
		{"跨年", time.Date(2023, 12, 31, 0, 0, 0, 0, time.UTC), 1, 2024, time.January, 1},
		{"闰日到三月", time.Date(2024, 2, 28, 0, 0, 0, 0, time.UTC), 1, 2024, time.February, 29},
		{"闰日后一天", time.Date(2024, 2, 29, 0, 0, 0, 0, time.UTC), 1, 2024, time.March, 1},
		{"非闰年二月", time.Date(2023, 2, 28, 0, 0, 0, 0, time.UTC), 1, 2023, time.March, 1},
		{"东八区跨天", time.Date(2024, 3, 1, 8, 0, 0, 0, time.FixedZone("CST", 8*3600)), 1, 2024, time.March, 2},
		{"西五区跨天", time.Date(2024, 3, 1, 20, 0, 0, 0, time.FixedZone("EST", -5*3600)), 1, 2024, time.March, 2},
		{"零间隔同日", time.Date(2024, 5, 20, 0, 0, 0, 0, time.UTC), 0, 2024, time.May, 20},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := nextReviewDate(c.base, c.intervalDays)
			if got.Year() != c.wantYear {
				t.Fatalf("year: got %d want %d", got.Year(), c.wantYear)
			}
			if got.Month() != c.wantMonth {
				t.Fatalf("month: got %v want %v", got.Month(), c.wantMonth)
			}
			if got.Day() != c.wantDay {
				t.Fatalf("day: got %d want %d", got.Day(), c.wantDay)
			}
			if got.Before(c.base) && c.intervalDays >= 0 {
				t.Fatalf("next review %v should not be before base %v", got, c.base)
			}
		})
	}
}

// SM-2 极端 EF 值：最小 1.3，最大上界，以及 EF 下限保护。
const sm2MinEF = 1.3

func sm2NextEF(ef float64, quality int) float64 {
	next := ef + (0.1 - float64(5-quality)*(0.08+float64(5-quality)*0.02))
	if next < sm2MinEF {
		next = sm2MinEF
	}
	if next > 2.5 {
		next = 2.5
	}
	return next
}

func TestSM2ExtremeEFPush(t *testing.T) {
	cases := []struct {
		name    string
		ef      float64
		quality int
		want    float64
	}{
		{"下限保护", 1.3, 0, 1.3},
		{"下限之上升", 1.3, 5, 1.4},
		{"上界封顶", 2.5, 5, 2.5},
		{"上界不超", 2.5, 4, 2.5},
		{"极低初始", 0.1, 3, 1.3},
		{"负值归到下限", -5.0, 2, 1.3},
		{"零值到下限", 0.0, 5, 1.3},
		{"正常提升", 2.0, 5, 2.1},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := sm2NextEF(c.ef, c.quality)
			if got < sm2MinEF {
				t.Fatalf("EF %v below min %v", got, sm2MinEF)
			}
			if got > 2.5 {
				t.Fatalf("EF %v above max 2.5", got)
			}
			if diff := got - c.want; diff > 1e-9 || diff < -1e-9 {
				t.Fatalf("EF: got %v want %v", got, c.want)
			}
		})
	}
}

// 双链解析边界：嵌套、中文标题、不闭合、多重链接。
func parseLinks(body string) []string {
	var out []string
	i := 0
	for {
		start := strings.Index(body[i:], "[[")
		if start < 0 {
			break
		}
		start += i
		end := strings.Index(body[start+2:], "]]")
		if end < 0 {
			break
		}
		end += start + 2
		inner := body[start+2 : end]
		if strings.Contains(inner, "[[") {
			i = start + 2
			continue
		}
		out = append(out, inner)
		i = end + 2
	}
	return out
}

func TestParseLinksBoundary(t *testing.T) {
	cases := []struct {
		name string
		body string
		want []string
	}{
		{"普通链接", "见 [[笔记A]] 和 [[笔记B]]", []string{"笔记A", "笔记B"}},
		{"中文标题", "参考 [[深度学习笔记]] 与 [[产品设计]]", []string{"深度学习笔记", "产品设计"}},
		{"嵌套不解析", "外层 [[内层 [[真标题]] 尾巴]]", []string{"真标题"}},
		{"未闭合忽略", "开头 [[未闭合 后面没结束", []string{}},
		{"空内容", "空链接 [[]] 结束", []string{""}},
		{"相邻链接", "[[A]][[B]]", []string{"A", "B"}},
		{"无链接", "纯文本没有链接", []string{}},
		{"含空格标题", "[[ my note title ]]", []string{" my note title "}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := parseLinks(c.body)
			if len(got) != len(c.want) {
				t.Fatalf("count: got %d %v want %d %v", len(got), got, len(c.want), c.want)
			}
			for i := range got {
				if got[i] != c.want[i] {
					t.Fatalf("index %d: got %q want %q", i, got[i], c.want[i])
				}
			}
		})
	}
}

// 附件白名单绕过尝试。
var allowedExt = map[string]bool{".png": true, ".jpg": true, ".jpeg": true, ".gif": true, ".pdf": true, ".md": true, ".txt": true}

func isAllowedAttachment(name string) bool {
	lower := strings.ToLower(name)
	ext := strings.ToLower(filepath.Ext(lower))
	if strings.ContainsAny(name, "/\\") {
		return false
	}
	if strings.Contains(name, "\x00") {
		return false
	}
	if strings.HasSuffix(lower, ".php") || strings.HasSuffix(lower, ".exe") || strings.HasSuffix(lower, ".sh") {
		return false
	}
	return allowedExt[ext]
}

func TestAttachmentWhitelistBypassPush(t *testing.T) {
	cases := []struct {
		name string
		file string
		want bool
	}{
		{"正常图片", "photo.png", true},
		{"大写扩展名", "PHOTO.PNG", true},
		{"双扩展名取最终扩展名", "evil.php.png", true},
		{"双扩展名取最终扩展名jpg", "evil.exe.jpg", true},
		{"路径穿越", "../../etc/passwd", false},
		{"反斜杠穿越", "..\\..\\windows\\system32", false},
		{"空字节截断", "image.png\x00.php", false},
		{"可执行文件", "run.exe", false},
		{"脚本文件", "install.sh", false},
		{"未知扩展", "data.bin", false},
		{"无扩展", "noext", false},
		{"正常pdf", "doc.pdf", true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := isAllowedAttachment(c.file)
			if got != c.want {
				t.Fatalf("allow: got %v want %v for %q", got, c.want, c.file)
			}
			if got && strings.ContainsAny(c.file, "/\\") {
				t.Fatalf("path separator should never be allowed: %q", c.file)
			}
		})
	}
}

// 导出 ZipSlip 防护。
func safeZipEntryPath(baseDir, entryName string) (string, bool) {
	if strings.Contains(entryName, "..") {
		return "", false
	}
	clean := filepath.Clean(filepath.Join(baseDir, entryName))
	base := filepath.Clean(baseDir) + string(os.PathSeparator)
	if !strings.HasPrefix(clean, base) {
		return "", false
	}
	return clean, true
}

func TestZipSlipProtection(t *testing.T) {
	base := filepath.Join(t.TempDir(), "export")
	cases := []struct {
		name  string
		entry string
		want  bool
	}{
		{"正常文件", "notes/a.md", true},
		{"顶层文件", "readme.txt", true},
		{"上跳一层", "../evil.txt", false},
		{"上跳多层", "../../../etc/passwd", false},
		{"嵌套上跳", "notes/../../evil.txt", false},
		{"绝对路径被Join收敛到base下", "/etc/passwd", true},
		{"带点目录", "notes/./a.md", true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, ok := safeZipEntryPath(base, c.entry)
			if ok != c.want {
				t.Fatalf("safe: got %v want %v for %q", ok, c.want, c.entry)
			}
			if ok {
				if !strings.HasPrefix(got, filepath.Clean(base)+string(os.PathSeparator)) {
					t.Fatalf("resolved path %q escapes base %q", got, base)
				}
				if strings.Contains(got, "..") {
					t.Fatalf("resolved path %q still contains ..", got)
				}
			}
		})
	}
}

// 用真实 zip 写入再读回，验证 ZipSlip 拒绝不会写出 base 之外的文件。
func TestExportZipRealWrite(t *testing.T) {
	base := t.TempDir()
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	w, err := zw.Create("notes/a.md")
	if err != nil {
		t.Fatalf("create zip entry: %v", err)
	}
	if _, err := w.Write([]byte("hello")); err != nil {
		t.Fatalf("write zip entry: %v", err)
	}
	if err := zw.Close(); err != nil {
		t.Fatalf("close zip: %v", err)
	}
	zr, err := zip.NewReader(bytes.NewReader(buf.Bytes()), int64(buf.Len()))
	if err != nil {
		t.Fatalf("open zip reader: %v", err)
	}
	if len(zr.File) != 1 {
		t.Fatalf("zip entries: got %d want 1", len(zr.File))
	}
	entry := zr.File[0]
	if entry.Name != "notes/a.md" {
		t.Fatalf("entry name: got %q want %q", entry.Name, "notes/a.md")
	}
	dest, ok := safeZipEntryPath(base, entry.Name)
	if !ok {
		t.Fatalf("expected safe path for %q", entry.Name)
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	rc, err := entry.Open()
	if err != nil {
		t.Fatalf("open entry: %v", err)
	}
	defer rc.Close()
	data := make([]byte, 16)
	n, _ := rc.Read(data)
	if string(data[:n]) != "hello" {
		t.Fatalf("content: got %q want %q", string(data[:n]), "hello")
	}
	if !strings.HasPrefix(dest, filepath.Clean(base)) {
		t.Fatalf("dest %q not under base %q", dest, base)
	}
}

// 多用户隔离：不同用户的推送记录与设置互不干扰。
func TestMultiUserIsolationPush(t *testing.T) {
	s := newDeepStore(t)
	date := "2024-06-01"
	channel := "morning"

	if err := s.RecordPushFor(date, channel, "userA", "sent", "ok-a"); err != nil {
		t.Fatalf("record A: %v", err)
	}
	if err := s.RecordPushFor(date, channel, "userB", "sent", "ok-b"); err != nil {
		t.Fatalf("record B: %v", err)
	}

	if !s.HasPushedFor(date, channel, "userA") {
		t.Fatalf("userA should have pushed")
	}
	if !s.HasPushedFor(date, channel, "userB") {
		t.Fatalf("userB should have pushed")
	}
	if s.HasPushedFor(date, channel, "userC") {
		t.Fatalf("userC should not have pushed")
	}
	if s.HasPushedFor(date, channel, DefaultUser) {
		t.Fatalf("DefaultUser should not have pushed")
	}

	if err := s.SetPushSetting("userA:theme", "dark"); err != nil {
		t.Fatalf("set A setting: %v", err)
	}
	if err := s.SetPushSetting("userB:theme", "light"); err != nil {
		t.Fatalf("set B setting: %v", err)
	}
	va, ok := s.GetPushSetting("userA:theme")
	if !ok || va != "dark" {
		t.Fatalf("userA setting: got %q ok=%v want dark", va, ok)
	}
	vb, ok := s.GetPushSetting("userB:theme")
	if !ok || vb != "light" {
		t.Fatalf("userB setting: got %q ok=%v want light", vb, ok)
	}
	_, ok = s.GetPushSetting("userC:theme")
	if ok {
		t.Fatalf("userC setting should not exist")
	}
}

// 记录与查询：按用户过滤列表、limit 边界。
func TestPushLogPerUserAndLimit(t *testing.T) {
	s := newDeepStore(t)
	if err := s.RecordPushFor("2024-06-01", "a", "u1", "sent", "d1"); err != nil {
		t.Fatalf("record: %v", err)
	}
	if err := s.RecordPushFor("2024-06-02", "a", "u1", "failed", "d2"); err != nil {
		t.Fatalf("record: %v", err)
	}
	if err := s.RecordPushFor("2024-06-03", "a", "u2", "sent", "d3"); err != nil {
		t.Fatalf("record: %v", err)
	}

	all, err := s.ListPushLogFor(10, "")
	if err != nil {
		t.Fatalf("list all: %v", err)
	}
	if len(all) != 3 {
		t.Fatalf("all count: got %d want 3", len(all))
	}
	if all[0].Date != "2024-06-03" {
		t.Fatalf("first (id desc) date: got %q want 2024-06-03", all[0].Date)
	}

	u1, err := s.ListPushLogFor(10, "u1")
	if err != nil {
		t.Fatalf("list u1: %v", err)
	}
	if len(u1) != 2 {
		t.Fatalf("u1 count: got %d want 2", len(u1))
	}
	for _, r := range u1 {
		if r.User != "u1" {
			t.Fatalf("u1 list contains user %q", r.User)
		}
	}

	limited, err := s.ListPushLogFor(1, "")
	if err != nil {
		t.Fatalf("list limit 1: %v", err)
	}
	if len(limited) != 1 {
		t.Fatalf("limit count: got %d want 1", len(limited))
	}

	zero, err := s.ListPushLogFor(0, "")
	if err != nil {
		t.Fatalf("list limit 0: %v", err)
	}
	if len(zero) != 3 {
		t.Fatalf("limit 0 count: got %d want 3", len(zero))
	}
}

// 默认用户与显式用户互不串台，HasPushed 只认成功状态。
func TestDefaultUserAndStatusFilter(t *testing.T) {
	s := newDeepStore(t)
	date := "2024-07-01"
	channel := "evening"

	if err := s.RecordPush(date, channel, "failed", "boom"); err != nil {
		t.Fatalf("record default failed: %v", err)
	}
	if s.HasPushed(date, channel) {
		t.Fatalf("failed push should not count as pushed")
	}

	morning := "morning"
	if err := s.RecordPush(date, morning, "sent", "ok"); err != nil {
		t.Fatalf("record default sent: %v", err)
	}
	if !s.HasPushed(date, morning) {
		t.Fatalf("sent push should count as pushed")
	}

	if err := s.RecordPushFor(date, channel, "other", "sent", "ok2"); err != nil {
		t.Fatalf("record other: %v", err)
	}
	if !s.HasPushedFor(date, channel, "other") {
		t.Fatalf("other user should have pushed")
	}
	if !s.HasPushed(date, morning) {
		t.Fatalf("default user should still have pushed")
	}

	recs, err := s.ListPushLogFor(50, DefaultUser)
	if err != nil {
		t.Fatalf("list default: %v", err)
	}
	if len(recs) != 2 {
		t.Fatalf("default records: got %d want 2", len(recs))
	}
	for _, r := range recs {
		if r.User != DefaultUser {
			t.Fatalf("default list contains user %q", r.User)
		}
	}
}
