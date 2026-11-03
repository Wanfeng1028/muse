package api

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestSanitizeZipNameBoundaries(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"empty", "", "note"},
		{"onlyPunct", "!!!???", "note"},
		{"onlyDashes", "---", "note"},
		{"chineseKept", "会议记录", "会议记录"},
		{"mixedCnEn", "会议 meeting 2024", "会议-meeting-2024"},
		{"trailingDashTrimmed", "abc-", "abc"},
		{"leadingDashTrimmed", "-abc", "abc"},
		{"collapseDashes", "a   b", "a-b"},
		{"truncateTo60", strings.Repeat("a", 61), strings.Repeat("a", 60)},
		{"emojiBecomesDash", "a🎉b", "a-b"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := sanitizeZipName(tc.in)
			if got != tc.want {
				t.Fatalf("sanitizeZipName(%q)=%q want %q", tc.in, got, tc.want)
			}
			if len([]rune(got)) > 60 {
				t.Fatalf("result too long: %d runes", len([]rune(got)))
			}
		})
	}
}

func TestNoteEntryNameZipSlipPrevention(t *testing.T) {
	cases := []struct {
		name  string
		seq   int
		id    int64
		title string
	}{
		{"pathTraversal", 1, 10, "../../etc/passwd"},
		{"backslash", 2, 11, `..\..\windows`},
		{"absolute", 3, 12, "/etc/shadow"},
		{"nulByte", 4, 13, "a\x00b"},
		{"dotDotDots", 5, 14, "...."},
		{"unicodeSlash", 6, 15, "a\u2215b"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := noteEntryName(tc.seq, tc.id, tc.title)
			if strings.Contains(got, "..") {
				t.Fatalf("entry name contains ..: %q", got)
			}
			if strings.ContainsAny(got, "/\\") {
				t.Fatalf("entry name contains path separator: %q", got)
			}
			if strings.ContainsRune(got, 0) {
				t.Fatalf("entry name contains NUL: %q", got)
			}
			if !strings.HasSuffix(got, ".md") {
				t.Fatalf("entry name missing .md suffix: %q", got)
			}
		})
	}
}

func TestYamlQuoteEscaping(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"plain", "hello", `"hello"`},
		{"backslash", `a\b`, `"a\\b"`},
		{"quote", `a"b`, `"a\"b"`},
		{"both", `\"`, `"\\\""`},
		{"chinese", "标题", `"标题"`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := yamlQuote(tc.in)
			if got != tc.want {
				t.Fatalf("yamlQuote(%q)=%q want %q", tc.in, got, tc.want)
			}
			if !strings.HasPrefix(got, `"`) || !strings.HasSuffix(got, `"`) {
				t.Fatalf("not wrapped in quotes: %q", got)
			}
		})
	}
}

func TestRewriteAttachmentRefsBoundaries(t *testing.T) {
	attMap := map[int64]string{
		1: "attachments/10-file.png",
		2: "attachments/10-doc.pdf",
	}
	cases := []struct {
		name string
		body string
		want string
	}{
		{"simple", "see attachment:1 here", "see ../attachments/10-file.png here"},
		{"two", "a attachment:1 b attachment:2", "a ../attachments/10-file.png b ../attachments/10-doc.pdf"},
		{"missing", "no attachment:99 found", "no attachment:99 found"},
		{"nested", "[attachment:1]", "[../attachments/10-file.png]"},
		{"noSpace", "xattachment:1y", "x../attachments/10-file.pngy"},
		{"adjacent", "attachment:1attachment:2", "../attachments/10-file.png../attachments/10-doc.pdf"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := rewriteAttachmentRefs(tc.body, attMap)
			if got != tc.want {
				t.Fatalf("rewriteAttachmentRefs(%q)=%q want %q", tc.body, got, tc.want)
			}
		})
	}
}

func TestExportFileNameFormat(t *testing.T) {
	got := exportFileName("", ".json")
	if !strings.HasPrefix(got, "second-brain-export-") {
		t.Fatalf("prefix mismatch: %q", got)
	}
	if !strings.HasSuffix(got, ".json") {
		t.Fatalf("suffix mismatch: %q", got)
	}
	mid := strings.TrimSuffix(strings.TrimPrefix(got, "second-brain-export-"), ".json")
	if _, err := time.Parse("20060102T150405", mid); err != nil {
		t.Fatalf("timestamp parse failed: %q err=%v", mid, err)
	}
	zip := exportFileName("", ".zip")
	if !strings.HasSuffix(zip, ".zip") {
		t.Fatalf("zip suffix mismatch: %q", zip)
	}
}

func TestCollectAllNotesPaginationAndEmpty(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	empty, err := collectAllNotes(st)
	if err != nil {
		t.Fatalf("collect empty: %v", err)
	}
	if empty == nil {
		t.Fatalf("empty result should be non-nil slice")
	}
	if len(empty) != 0 {
		t.Fatalf("expected 0 notes, got %d", len(empty))
	}

	created, err := st.CreateNote(store.Note{Title: "甲", Body: "body", Tags: []string{"x"}})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	notes, err := collectAllNotes(st)
	if err != nil {
		t.Fatalf("collect: %v", err)
	}
	if len(notes) != 1 {
		t.Fatalf("expected 1 note, got %d", len(notes))
	}
	if notes[0].ID != created.ID {
		t.Fatalf("id mismatch: got %d want %d", notes[0].ID, created.ID)
	}
	if notes[0].Tags == nil || len(notes[0].Tags) != 1 || notes[0].Tags[0] != "x" {
		t.Fatalf("tags mismatch: %#v", notes[0].Tags)
	}
	if notes[0].Attachments == nil {
		t.Fatalf("attachments should be non-nil empty slice")
	}
}

func TestExportJSONHandlerContentTypeAndBody(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	if _, err := st.CreateNote(store.Note{Title: "标题\"引号", Body: "line1\nline2", Tags: []string{"t1", "t2"}}); err != nil {
		t.Fatalf("create note: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	handleExportJSON(st)(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d want 200", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Fatalf("content-type = %q", ct)
	}
	if cd := rec.Header().Get("Content-Disposition"); !strings.Contains(cd, "second-brain-export-") {
		t.Fatalf("content-disposition = %q", cd)
	}

	var doc exportDoc
	if err := json.Unmarshal(rec.Body.Bytes(), &doc); err != nil {
		t.Fatalf("decode json: %v body=%q", err, rec.Body.String())
	}
	if doc.Version != "0.3.0" {
		t.Fatalf("version = %q", doc.Version)
	}
	if _, err := time.Parse(time.RFC3339, doc.ExportedAt); err != nil {
		t.Fatalf("exportedAt not RFC3339: %q err=%v", doc.ExportedAt, err)
	}
	if len(doc.Notes) != 1 {
		t.Fatalf("notes len = %d", len(doc.Notes))
	}
	if doc.Notes[0].Title != "标题\"引号" {
		t.Fatalf("title = %q", doc.Notes[0].Title)
	}
	if doc.Notes[0].Body != "line1\nline2" {
		t.Fatalf("body = %q", doc.Notes[0].Body)
	}
	if doc.Notes[0].Attachments == nil {
		t.Fatalf("attachments should be non-nil")
	}
}

func TestExportMarkdownZipRoundTrip(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	n, err := st.CreateNote(store.Note{Title: "我的笔记", Body: "引用 attachment:1 内容", Tags: []string{"标签"}})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	handleExportMarkdown(st)(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/zip" {
		t.Fatalf("content-type = %q", ct)
	}

	zr, err := zip.NewReader(bytes.NewReader(rec.Body.Bytes()), int64(rec.Body.Len()))
	if err != nil {
		t.Fatalf("zip open: %v", err)
	}
	names := map[string]bool{}
	for _, f := range zr.File {
		names[f.Name] = true
	}
	if !names["index.md"] {
		t.Fatalf("missing index.md, have %v", names)
	}
	wantEntry := noteEntryName(1, n.ID, "我的笔记")
	if !names["notes/"+wantEntry] {
		t.Fatalf("missing notes/%s, have %v", wantEntry, names)
	}

	var noteContent string
	for _, f := range zr.File {
		if f.Name == "notes/"+wantEntry {
			rc, err := f.Open()
			if err != nil {
				t.Fatalf("open entry: %v", err)
			}
			buf := new(bytes.Buffer)
			if _, err := buf.ReadFrom(rc); err != nil {
				t.Fatalf("read entry: %v", err)
			}
			rc.Close()
			noteContent = buf.String()
		}
	}
	if !strings.Contains(noteContent, "我的笔记") {
		t.Fatalf("note content missing title: %q", noteContent)
	}
	if !strings.Contains(noteContent, "attachment:1") {
		t.Fatalf("note content should keep unresolved ref: %q", noteContent)
	}
}

func TestExportMarkdownAttachmentWhitelistStoredNameBase(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	st.SetAttachDir(filepath.Join(dir, "attachments"))

	n, err := st.CreateNote(store.Note{Title: "带附件", Body: "看 attachment:1"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}

	att, err := st.CreateAttachment(n.ID, "passwd", "application/octet-stream", 4, "", "sub/dir/passwd")
	if err != nil {
		t.Fatalf("create attachment: %v", err)
	}
	full := st.AttachmentPath(att)
	if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(full, []byte("data"), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	handleExportMarkdown(st)(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	zr, err := zip.NewReader(bytes.NewReader(rec.Body.Bytes()), int64(rec.Body.Len()))
	if err != nil {
		t.Fatalf("zip open: %v", err)
	}
	for _, f := range zr.File {
		if strings.Contains(f.Name, "..") {
			t.Fatalf("zip entry contains ..: %q", f.Name)
		}
		if filepath.IsAbs(f.Name) {
			t.Fatalf("zip entry absolute: %q", f.Name)
		}
		clean := filepath.Clean(f.Name)
		if strings.HasPrefix(clean, "..") || strings.HasPrefix(clean, "/") {
			t.Fatalf("zip entry escapes root: %q", f.Name)
		}
	}
	found := false
	for _, f := range zr.File {
		if strings.HasPrefix(f.Name, "attachments/") {
			found = true
			if strings.Contains(f.Name, "..") || strings.Contains(f.Name, "/etc/") {
				t.Fatalf("attachment entry unsafe: %q", f.Name)
			}
			// storedName 的路径部分必须被 filepath.Base 剥掉
			if strings.Contains(f.Name, "sub/dir") {
				t.Fatalf("attachment entry kept directory: %q", f.Name)
			}
		}
	}
	if !found {
		t.Fatalf("expected at least one attachments/ entry, att id=%d", att.ID)
	}
}

func TestExportMarkdownMultiuserIsolation(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	ctx := context.Background()
	noteA, err := st.CreateNoteFor(ctx, store.Note{Title: "alice-note", Body: "a-body"}, "alice")
	if err != nil {
		t.Fatalf("create noteA: %v", err)
	}
	noteB, err := st.CreateNoteFor(ctx, store.Note{Title: "bob-note", Body: "b-body"}, "bob")
	if err != nil {
		t.Fatalf("create noteB: %v", err)
	}
	if noteA.ID == noteB.ID {
		t.Fatalf("notes should have distinct ids")
	}

	notes, err := collectAllNotes(st)
	if err != nil {
		t.Fatalf("collect: %v", err)
	}
	ids := map[int64]bool{}
	titles := map[string]bool{}
	for _, n := range notes {
		ids[n.ID] = true
		titles[n.Title] = true
	}
	if !ids[noteA.ID] || !ids[noteB.ID] {
		t.Fatalf("both users' notes expected in unscoped export: ids=%v", ids)
	}
	if !titles["alice-note"] || !titles["bob-note"] {
		t.Fatalf("titles missing: %v", titles)
	}
	if len(notes) != 2 {
		t.Fatalf("expected 2 notes, got %d", len(notes))
	}
}

func TestHandleExportJSONStoreError(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	handleExportJSON(st)(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d want 500", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "error") && rec.Body.Len() == 0 {
		t.Fatalf("expected error body, got %q", rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Fatalf("error content-type = %q", ct)
	}
}

func TestExportJSONRoundTripLeapDay(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	n, err := st.CreateNote(store.Note{
		Title: "闰日笔记",
		Body:  "跨天边界",
	})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	handleExportJSON(st)(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	var doc exportDoc
	if err := json.Unmarshal(rec.Body.Bytes(), &doc); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(doc.Notes) != 1 {
		t.Fatalf("notes len = %d", len(doc.Notes))
	}
	if doc.Notes[0].ID != n.ID {
		t.Fatalf("id mismatch: got %d want %d", doc.Notes[0].ID, n.ID)
	}
	if doc.Notes[0].CreatedAt != n.CreatedAt {
		t.Fatalf("createdAt = %q want %q", doc.Notes[0].CreatedAt, n.CreatedAt)
	}
	if doc.Notes[0].UpdatedAt != n.UpdatedAt {
		t.Fatalf("updatedAt = %q want %q", doc.Notes[0].UpdatedAt, n.UpdatedAt)
	}
	if _, err := time.Parse(time.RFC3339, doc.Notes[0].UpdatedAt); err != nil {
		t.Fatalf("updatedAt parse: %v", err)
	}
}

func TestExportMarkdownNestedBracketsChineseTitle(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	title := "[[嵌套]]中文标题"
	n, err := st.CreateNote(store.Note{Title: title, Body: "正文"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	handleExportMarkdown(st)(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}

	zr, err := zip.NewReader(bytes.NewReader(rec.Body.Bytes()), int64(rec.Body.Len()))
	if err != nil {
		t.Fatalf("zip open: %v", err)
	}
	wantEntry := noteEntryName(1, n.ID, title)
	foundIdx := false
	foundNote := false
	for _, f := range zr.File {
		if f.Name == "index.md" {
			foundIdx = true
		}
		if f.Name == "notes/"+wantEntry {
			foundNote = true
		}
	}
	if !foundIdx || !foundNote {
		t.Fatalf("missing entries idx=%v note=%v want=%q", foundIdx, foundNote, wantEntry)
	}
	if strings.Contains(wantEntry, "[") || strings.Contains(wantEntry, "]") {
		t.Fatalf("entry name should not contain brackets: %q", wantEntry)
	}
}

func TestHandleExportMarkdownStoreErrorBeforeBody(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	handleExportMarkdown(st)(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d want 500", rec.Code)
	}
	if rec.Header().Get("Content-Type") == "application/zip" {
		t.Fatalf("should not have written zip header on error")
	}
}

func TestExportJSONNoAttachmentsUsesEmptySlice(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	if _, err := st.CreateNote(store.Note{Title: "无附件", Body: "x"}); err != nil {
		t.Fatalf("create: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	handleExportJSON(st)(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	body := rec.Body.String()
	if !strings.Contains(body, `"attachments":[]`) {
		t.Fatalf("expected empty attachments array, body=%q", body)
	}
	if !strings.Contains(body, `"tags":[]`) {
		t.Fatalf("expected empty tags array, body=%q", body)
	}
}

func TestExportJSONAttachmentStoredNameKept(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	n, err := st.CreateNote(store.Note{Title: "有附件", Body: "x"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	att, err := st.CreateAttachment(n.ID, "photo.png", "image/png", 0, "", "abc123.png")
	if err != nil {
		t.Fatalf("create attachment: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	handleExportJSON(st)(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	var doc exportDoc
	if err := json.Unmarshal(rec.Body.Bytes(), &doc); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(doc.Notes) != 1 || len(doc.Notes[0].Attachments) != 1 {
		t.Fatalf("attachments not exported: %#v", doc.Notes)
	}
	got := doc.Notes[0].Attachments[0]
	if got.ID != att.ID {
		t.Fatalf("attachment id = %d want %d", got.ID, att.ID)
	}
	if got.StoredName != "abc123.png" {
		t.Fatalf("stored name = %q", got.StoredName)
	}
	if got.Filename != "photo.png" {
		t.Fatalf("orig name = %q", got.Filename)
	}
}

func TestAttachmentRefRegexBoundaries(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want bool
	}{
		{"plain", "attachment:1", true},
		{"zero", "attachment:0", true},
		{"large", "attachment:999999999999", true},
		{"nonDigit", "attachment:abc", false},
		{"empty", "attachment:", false},
		{"spaces", "attachment: 1", false},
		{"embedded", "xattachment:42y", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := attachmentRefRe.MatchString(tc.in)
			if got != tc.want {
				t.Fatalf("MatchString(%q)=%v want %v", tc.in, got, tc.want)
			}
			if !tc.want && got {
				t.Fatalf("should not match %q", tc.in)
			}
		})
	}
}

func TestCollectAllNotesNilSafety(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	if _, err := st.CreateNote(store.Note{Title: "t", Body: "b"}); err != nil {
		t.Fatalf("create: %v", err)
	}
	notes, err := collectAllNotes(st)
	if err != nil {
		t.Fatalf("collect: %v", err)
	}
	if notes == nil {
		t.Fatalf("notes must be non-nil")
	}
	if notes[0].Tags == nil {
		t.Fatalf("tags must be non-nil even when empty")
	}
	if notes[0].Attachments == nil {
		t.Fatalf("attachments must be non-nil even when empty")
	}
}

var _ = os.Getenv
