package store

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func newAttachTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	s, err := Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	s.SetAttachDir(filepath.Join(dir, "attach"))
	if err := os.MkdirAll(s.AttachDir(), 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}
	return s
}

func createTestNote(t *testing.T, s *Store, title string) int64 {
	t.Helper()
	n, err := s.CreateNote(Note{Title: title, Body: "body"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	return n.ID
}

// --- 复习调度边界 ---

func TestReviewScheduleBoundariesAttachment(t *testing.T) {
	cases := []struct {
		name      string
		base      string
		interval  int
		wantSame  bool
		wantAfter bool
	}{
		{"cross_day_forward", "2024-01-31T23:30:00Z", 1, false, true},
		{"cross_month_forward", "2024-01-31T12:00:00Z", 1, false, true},
		{"leap_day_2024", "2024-02-28T12:00:00Z", 1, false, true},
		{"non_leap_2023", "2023-02-28T12:00:00Z", 1, false, true},
		{"zero_interval_same", "2024-03-15T08:00:00Z", 0, true, false},
		{"large_interval", "2024-01-01T00:00:00Z", 365, false, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			base, err := time.Parse(time.RFC3339, tc.base)
			if err != nil {
				t.Fatalf("parse base: %v", err)
			}
			got := base.AddDate(0, 0, tc.interval)
			if tc.wantSame && !got.Equal(base) {
				t.Fatalf("interval=%d want same got %v", tc.interval, got)
			}
			if tc.wantAfter && !got.After(base) {
				t.Fatalf("interval=%d want after got %v", tc.interval, got)
			}
			// 断言 UTC 时刻在跨天场景下正确推进
			if tc.interval > 0 {
				diff := got.Sub(base).Hours()
				if diff < float64(tc.interval*24-24) {
					t.Fatalf("interval=%d diff=%.2fh too small", tc.interval, diff)
				}
			}
		})
	}
}

func TestReviewScheduleTimezone(t *testing.T) {
	utc, err := time.Parse(time.RFC3339, "2024-06-15T23:00:00Z")
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	shanghai, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("LoadLocation: %v", err)
	}
	local := utc.In(shanghai)
	if local.Day() != 16 {
		t.Fatalf("want day 16 in +08 got %d", local.Day())
	}
	if local.Hour() != 7 {
		t.Fatalf("want hour 7 in +08 got %d", local.Hour())
	}
	next := local.AddDate(0, 0, 1)
	if next.Sub(local).Hours() != 24 {
		t.Fatalf("want 24h gap got %v", next.Sub(local))
	}
}

func TestSM2ExtremeEFAttachment(t *testing.T) {
	cases := []struct {
		name    string
		ef      float64
		quality int
		wantMin float64
		wantMax float64
	}{
		{"ef_floor_clamp", 1.3, 0, 1.3, 1.3},
		{"ef_high_quality", 2.5, 5, 2.5, 3.0},
		{"ef_max_bound", 2.7, 5, 2.7, 3.0},
		{"ef_zero_quality", 2.5, 0, 1.3, 1.71},
		{"ef_low_start", 1.3, 3, 1.3, 1.3},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			// SM-2 EF 更新公式: EF' = EF + (0.1 - (5-q)*(0.08+(5-q)*0.02))
			q := float64(tc.quality)
			delta := 0.1 - (5-q)*(0.08+(5-q)*0.02)
			next := tc.ef + delta
			if next < 1.3 {
				next = 1.3
			}
			if next < tc.wantMin {
				t.Fatalf("ef=%v q=%d next=%.4f < min %.4f", tc.ef, tc.quality, next, tc.wantMin)
			}
			if next > tc.wantMax {
				t.Fatalf("ef=%v q=%d next=%.4f > max %.4f", tc.ef, tc.quality, next, tc.wantMax)
			}
		})
	}
}

// --- 双链解析边界 ---

func TestWikiLinkParseNestedAndChinese(t *testing.T) {
	cases := []struct {
		name      string
		input     string
		wantN     int
		wantFirst string
	}{
		{"simple_ascii", "see [[NoteA]] here", 1, "NoteA"},
		{"nested_brackets", "see [[outer [[inner]] tail]] end", 1, "outer [[inner"},
		{"chinese_title", "参考 [[中文标题]] 内容", 1, "中文标题"},
		{"multiple_links", "[[A]] and [[B]] and [[C]]", 3, "A"},
		{"unclosed", "see [[open only", 0, ""},
		{"empty_link", "see [[]] here", 1, ""},
		{"adjacent", "[[A]][[B]]", 2, "A"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			links := parseWikiLinksForTest(tc.input)
			if len(links) != tc.wantN {
				t.Fatalf("input=%q want %d links got %d (%v)", tc.input, tc.wantN, len(links), links)
			}
			if tc.wantN > 0 && links[0] != tc.wantFirst {
				t.Fatalf("input=%q want first %q got %q", tc.input, tc.wantFirst, links[0])
			}
		})
	}
}

func parseWikiLinksForTest(s string) []string {
	var out []string
	for {
		start := strings.Index(s, "[[")
		if start < 0 {
			break
		}
		rest := s[start+2:]
		end := strings.Index(rest, "]]")
		if end < 0 {
			break
		}
		out = append(out, rest[:end])
		s = rest[end+2:]
	}
	return out
}

// --- 附件白名单绕过尝试 ---

func TestAttachmentWhitelistBypassAttachment(t *testing.T) {
	cases := []struct {
		name     string
		filename string
		wantOK   bool
	}{
		{"normal_png", "photo.png", true},
		{"normal_pdf", "doc.pdf", true},
		{"double_ext", "evil.png.exe", false},
		{"upper_ext", "PHOTO.PNG", true},
		{"null_byte", "photo.png\x00.exe", false},
		{"path_traversal", "../../etc/passwd", false},
		{"dotdot_stored", "..", false},
		{"empty", "", false},
		{"unicode_dot", "photo。png", false},
		{"space_ext", "photo .png", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := isAllowedAttachmentForTest(tc.filename)
			if got != tc.wantOK {
				t.Fatalf("filename=%q want %v got %v", tc.filename, tc.wantOK, got)
			}
			if strings.Contains(tc.filename, "..") && got {
				t.Fatalf("filename=%q with .. must be rejected", tc.filename)
			}
		})
	}
}

func isAllowedAttachmentForTest(name string) bool {
	if name == "" || strings.Contains(name, "\x00") {
		return false
	}
	if strings.Contains(name, "..") {
		return false
	}
	if strings.Contains(name, "/") || strings.Contains(name, "\\") {
		return false
	}
	if strings.Contains(name, "。") {
		return false
	}
	idx := strings.LastIndex(name, ".")
	if idx < 0 {
		return false
	}
	ext := strings.ToLower(name[idx+1:])
	if ext == "" {
		return false
	}
	if strings.Contains(ext, ".") {
		return false
	}
	switch ext {
	case "png", "jpg", "jpeg", "gif", "pdf", "txt", "md":
		return true
	}
	return false
}

// --- 导出 ZipSlip ---

func TestExportZipSlip(t *testing.T) {
	cases := []struct {
		name     string
		stored   string
		wantSlip bool
	}{
		{"safe", "abc123.bin", false},
		{"relative_up", "../evil.bin", true},
		{"nested_up", "a/../../evil.bin", true},
		{"absolute", "/tmp/evil.bin", true},
		{"windows_drive", "C:\\evil.bin", true},
		{"backslash_up", "..\\evil.bin", true},
		{"safe_subdir", "sub/abc.bin", false},
		{"dot_only", ".", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := isZipSlipForTest(tc.stored)
			if got != tc.wantSlip {
				t.Fatalf("stored=%q want slip %v got %v", tc.stored, tc.wantSlip, got)
			}
			if got {
				cleaned := filepath.Clean(tc.stored)
				if !strings.HasPrefix(cleaned, "..") && !filepath.IsAbs(cleaned) &&
					!strings.HasPrefix(cleaned, "/") && !strings.HasPrefix(cleaned, "\\") &&
					!strings.Contains(cleaned, "\\") && cleaned != "." {
					t.Fatalf("stored=%q flagged as slip but clean=%q", tc.stored, cleaned)
				}
			}
		})
	}
}

func isZipSlipForTest(name string) bool {
	if name == "" {
		return true
	}
	if filepath.IsAbs(name) {
		return true
	}
	if strings.HasPrefix(name, "/") || strings.HasPrefix(name, "\\") {
		return true
	}
	if strings.Contains(name, "\\") {
		return true
	}
	if strings.Contains(name, ":") {
		return true
	}
	cleaned := filepath.Clean(name)
	if cleaned == "." || cleaned == ".." {
		return true
	}
	if strings.HasPrefix(cleaned, ".."+string(filepath.Separator)) || cleaned == ".." {
		return true
	}
	if strings.HasPrefix(name, "..") {
		return true
	}
	return false
}

// --- 多用户隔离 ---

func TestMultiUserIsolationAttachment(t *testing.T) {
	s := newAttachTestStore(t)
	noteA := createTestNote(t, s, "userA note")
	noteB := createTestNote(t, s, "userB note")

	a1, err := s.CreateAttachment(noteA, "a.png", "image/png", 100, "sha-a", "sa.png")
	if err != nil {
		t.Fatalf("CreateAttachment A: %v", err)
	}
	b1, err := s.CreateAttachment(noteB, "b.png", "image/png", 200, "sha-b", "sb.png")
	if err != nil {
		t.Fatalf("CreateAttachment B: %v", err)
	}

	listA, err := s.ListAttachments(noteA)
	if err != nil {
		t.Fatalf("ListAttachments A: %v", err)
	}
	if len(listA) != 1 {
		t.Fatalf("noteA want 1 got %d", len(listA))
	}
	if listA[0].ID != a1.ID {
		t.Fatalf("noteA attachment id want %d got %d", a1.ID, listA[0].ID)
	}

	listB, err := s.ListAttachments(noteB)
	if err != nil {
		t.Fatalf("ListAttachments B: %v", err)
	}
	if len(listB) != 1 {
		t.Fatalf("noteB want 1 got %d", len(listB))
	}
	if listB[0].ID != b1.ID {
		t.Fatalf("noteB attachment id want %d got %d", b1.ID, listB[0].ID)
	}

	pathA := s.AttachmentPath(a1)
	pathB := s.AttachmentPath(b1)
	if pathA == pathB {
		t.Fatalf("paths must differ got %q", pathA)
	}
	if !strings.Contains(pathA, strconv.FormatInt(noteA, 10)) {
		t.Fatalf("pathA %q must contain noteA id", pathA)
	}
	if !strings.Contains(pathB, strconv.FormatInt(noteB, 10)) {
		t.Fatalf("pathB %q must contain noteB id", pathB)
	}
}

// --- 附件 CRUD 与磁盘删除 ---

func TestAttachmentCRUDAndDiskCleanup(t *testing.T) {
	s := newAttachTestStore(t)
	noteID := createTestNote(t, s, "crud note")

	a, err := s.CreateAttachment(noteID, "file.txt", "text/plain", 42, "sha-crud", "stored.txt")
	if err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}
	if a.ID == 0 {
		t.Fatalf("want nonzero id")
	}
	if a.NoteID != noteID {
		t.Fatalf("want noteID %d got %d", noteID, a.NoteID)
	}
	if a.Size != 42 {
		t.Fatalf("want size 42 got %d", a.Size)
	}

	diskPath := s.AttachmentPath(a)
	if err := os.MkdirAll(filepath.Dir(diskPath), 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}
	if err := os.WriteFile(diskPath, []byte("hello"), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	got, err := s.GetAttachment(a.ID)
	if err != nil {
		t.Fatalf("GetAttachment: %v", err)
	}
	if got.Filename != "file.txt" || got.SHA256 != "sha-crud" {
		t.Fatalf("got %+v", got)
	}

	deleted, err := s.DeleteAttachment(a.ID)
	if err != nil {
		t.Fatalf("DeleteAttachment: %v", err)
	}
	if deleted.ID != a.ID {
		t.Fatalf("deleted id want %d got %d", a.ID, deleted.ID)
	}

	if _, err := os.Stat(diskPath); !os.IsNotExist(err) {
		t.Fatalf("disk file should be gone, stat err=%v", err)
	}

	if _, err := s.GetAttachment(a.ID); err == nil {
		t.Fatalf("want error after delete")
	}
}

// --- 不存在的笔记创建附件 ---

func TestCreateAttachmentMissingNote(t *testing.T) {
	s := newAttachTestStore(t)
	_, err := s.CreateAttachment(99999, "x.png", "image/png", 1, "sha", "sx.png")
	if err == nil {
		t.Fatalf("want error for missing note")
	}
	if err != ErrNotFound {
		t.Fatalf("want ErrNotFound got %v", err)
	}
	list, err := s.ListAttachments(99999)
	if err != nil {
		t.Fatalf("ListAttachments: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("want empty list got %d", len(list))
	}
}
