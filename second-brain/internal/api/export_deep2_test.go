package api

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func readZipEntries(t *testing.T, data []byte) map[string][]byte {
	t.Helper()
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		t.Fatalf("zip.NewReader: %v", err)
	}
	out := map[string][]byte{}
	for _, f := range zr.File {
		rc, err := f.Open()
		if err != nil {
			t.Fatalf("open zip entry %q: %v", f.Name, err)
		}
		var buf bytes.Buffer
		if _, err := buf.ReadFrom(rc); err != nil {
			rc.Close()
			t.Fatalf("read zip entry %q: %v", f.Name, err)
		}
		rc.Close()
		out[f.Name] = buf.Bytes()
	}
	return out
}

func TestExportMarkdown_AttachmentBytesIdentical(t *testing.T) {
	st := newTestStore(t)
	n, err := st.CreateNote(store.Note{Title: "with-att", Body: "body attachment:1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	a, err := st.CreateAttachment(n.ID, "orig.png", "image/png", 4, "deadbeef", "stored.png")
	if err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}
	payload := []byte{0x00, 0x01, 0xfe, 0xff}
	p := st.AttachmentPath(a)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(p, payload, 0o644); err != nil {
		t.Fatalf("write attachment: %v", err)
	}

	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	entries := readZipEntries(t, rec.Body.Bytes())
	wantName := fmt.Sprintf("attachments/%d-%s", n.ID, filepath.Base("stored.png"))
	got, ok := entries[wantName]
	if !ok {
		names := make([]string, 0, len(entries))
		for k := range entries {
			names = append(names, k)
		}
		t.Fatalf("missing attachment entry %q, have %v", wantName, names)
	}
	if !bytes.Equal(got, payload) {
		t.Fatalf("attachment bytes mismatch: got %x want %x", got, payload)
	}
}

func TestExportMarkdown_MissingAttachmentFile_SkippedNoteStillExported(t *testing.T) {
	st := newTestStore(t)
	n, err := st.CreateNote(store.Note{Title: "no-file", Body: "hello attachment:1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := st.CreateAttachment(n.ID, "ghost.png", "image/png", 10, "aa", "ghost-stored.png"); err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}

	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	entries := readZipEntries(t, rec.Body.Bytes())
	for name := range entries {
		if strings.HasPrefix(name, "attachments/") {
			t.Fatalf("unexpected attachment entry %q", name)
		}
	}
	noteName := fmt.Sprintf("notes/0001-%d-no-file.md", n.ID)
	body, ok := entries[noteName]
	if !ok {
		names := make([]string, 0, len(entries))
		for k := range entries {
			names = append(names, k)
		}
		t.Fatalf("missing note entry %q, have %v", noteName, names)
	}
	if !strings.Contains(string(body), "hello") {
		t.Fatalf("note body missing content: %q", string(body))
	}
}

func TestExportMarkdown_StoredNameTraversal_NoDotDotInZip(t *testing.T) {
	st := newTestStore(t)
	n, err := st.CreateNote(store.Note{Title: "traversal", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := st.CreateAttachment(n.ID, "evil.txt", "text/plain", 1, "aa", "sub/../../evil.txt"); err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}

	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	entries := readZipEntries(t, rec.Body.Bytes())
	for name := range entries {
		if strings.Contains(name, "..") {
			t.Fatalf("entry name contains dotdot: %q", name)
		}
	}
}

func TestExportMarkdown_TitleTraversal_NoDotDotInZip(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateNote(store.Note{Title: "../../../etc/passwd", Body: "x"}); err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	entries := readZipEntries(t, rec.Body.Bytes())
	if len(entries) == 0 {
		t.Fatalf("expected some zip entries")
	}
	for name := range entries {
		if strings.Contains(name, "..") {
			t.Fatalf("entry name contains dotdot: %q", name)
		}
	}
}

func TestCollectAllNotes_PaginationBoundary_501(t *testing.T) {
	st := newTestStore(t)
	for i := 0; i < 501; i++ {
		if _, err := st.CreateNote(store.Note{Title: fmt.Sprintf("n-%03d", i), Body: "b"}); err != nil {
			t.Fatalf("CreateNote %d: %v", i, err)
		}
	}
	notes, err := collectAllNotes(st)
	if err != nil {
		t.Fatalf("collectAllNotes: %v", err)
	}
	if len(notes) != 501 {
		t.Fatalf("got %d notes, want 501", len(notes))
	}
}

func TestCollectAllNotes_Exactly500(t *testing.T) {
	st := newTestStore(t)
	for i := 0; i < 500; i++ {
		if _, err := st.CreateNote(store.Note{Title: fmt.Sprintf("n-%03d", i), Body: "b"}); err != nil {
			t.Fatalf("CreateNote %d: %v", i, err)
		}
	}
	notes, err := collectAllNotes(st)
	if err != nil {
		t.Fatalf("collectAllNotes: %v", err)
	}
	if len(notes) != 500 {
		t.Fatalf("got %d notes, want 500", len(notes))
	}
}

func TestRewriteAttachmentRefs_MultipleSameID(t *testing.T) {
	attMap := map[int64]string{5: "attachments/1-ab.png"}
	body := "看 attachment:5 和 attachment:5 以及 attachment:999"
	got := rewriteAttachmentRefs(body, attMap)
	want := "看 ../attachments/1-ab.png 和 ../attachments/1-ab.png 以及 attachment:999"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestExportMarkdown_IndexEntryFormat(t *testing.T) {
	st := newTestStore(t)
	n, err := st.CreateNote(store.Note{Title: "会议记录", Body: "内容"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/markdown", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	entries := readZipEntries(t, rec.Body.Bytes())
	idx, ok := entries["index.md"]
	if !ok {
		t.Fatalf("index.md missing, have %v", entries)
	}
	entry := fmt.Sprintf("%04d-%d-%s.md", 1, n.ID, sanitizeZipName("会议记录"))
	wantLine := fmt.Sprintf("- [会议记录](notes/%s)", entry)
	if !strings.Contains(string(idx), wantLine) {
		t.Fatalf("index.md missing line %q, got:\n%s", wantLine, string(idx))
	}
}

func TestBuildNoteMarkdown_TitleBackslashQuoteEscaped(t *testing.T) {
	n := exportNote{
		ID:    1,
		Title: `a\b"c`,
		Body:  "body",
		Tags:  []string{`x"y`, `p\q`},
	}
	md := buildNoteMarkdown(n, "body")
	if !strings.Contains(md, `title: "a\\b\"c"`) {
		t.Fatalf("missing escaped title line, got:\n%s", md)
	}
	if !strings.Contains(md, `tags: ["x\"y", "p\\q"]`) {
		t.Fatalf("missing escaped tags line, got:\n%s", md)
	}
}

func TestBuildNoteMarkdown_TitleNewlineKeptVerbatim(t *testing.T) {
	n := exportNote{
		ID:    1,
		Title: "第一行\n第二行",
		Body:  "body",
		Tags:  []string{},
	}
	md := buildNoteMarkdown(n, "body")
	if !strings.Contains(md, "title: \"第一行\n第二行\"") {
		t.Fatalf("expected newline kept verbatim in title line, got:\n%s", md)
	}
	if !strings.Contains(md, "tags: []") {
		t.Fatalf("expected empty tags line, got:\n%s", md)
	}
}

func TestExportJSON_EmptyLibrary(t *testing.T) {
	st := newTestStore(t)
	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	var doc exportDoc
	if err := json.Unmarshal(rec.Body.Bytes(), &doc); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, rec.Body.String())
	}
	if doc.Version != "0.3.0" {
		t.Fatalf("version=%q want 0.3.0", doc.Version)
	}
	if doc.Notes == nil {
		t.Fatalf("notes is nil, want empty array; raw=%s", rec.Body.String())
	}
	if len(doc.Notes) != 0 {
		t.Fatalf("notes len=%d want 0", len(doc.Notes))
	}
	if !strings.Contains(rec.Body.String(), `"notes":[]`) {
		t.Fatalf("expected notes encoded as [], raw=%s", rec.Body.String())
	}
}

func TestWriteZipEntry_AbsolutePathSkipped(t *testing.T) {
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	if err := writeZipEntry(zw, "/etc/passwd", []byte("x"), time.Now()); err != nil {
		t.Fatalf("writeZipEntry absolute: %v", err)
	}
	if err := writeZipEntry(zw, "a/../../b.txt", []byte("y"), time.Now()); err != nil {
		t.Fatalf("writeZipEntry dotdot: %v", err)
	}
	if err := zw.Close(); err != nil {
		t.Fatalf("zip close: %v", err)
	}
	zr, err := zip.NewReader(bytes.NewReader(buf.Bytes()), int64(buf.Len()))
	if err != nil {
		t.Fatalf("zip.NewReader: %v", err)
	}
	if len(zr.File) != 0 {
		names := make([]string, 0, len(zr.File))
		for _, f := range zr.File {
			names = append(names, f.Name)
		}
		t.Fatalf("expected no entries, got %v", names)
	}
}

func TestExportJSON_AttachmentStoredNameVerbatim(t *testing.T) {
	st := newTestStore(t)
	n, err := st.CreateNote(store.Note{Title: "att-json", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	const stored = "ab12 cd.png"
	const filename = "weird name.png"
	if _, err := st.CreateAttachment(n.ID, filename, "image/png", 3, "bb", stored); err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}

	mux := http.NewServeMux()
	RegisterExportRoutes(mux, st)
	req := httptest.NewRequest(http.MethodGet, "/api/export/json", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	var doc exportDoc
	if err := json.Unmarshal(rec.Body.Bytes(), &doc); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, rec.Body.String())
	}
	if len(doc.Notes) != 1 {
		t.Fatalf("notes len=%d want 1", len(doc.Notes))
	}
	if len(doc.Notes[0].Attachments) != 1 {
		t.Fatalf("attachments len=%d want 1", len(doc.Notes[0].Attachments))
	}
	got := doc.Notes[0].Attachments[0]
	if got.StoredName != stored {
		t.Fatalf("storedName=%q want %q", got.StoredName, stored)
	}
	if got.Filename != filename {
		t.Fatalf("filename=%q want %q", got.Filename, filename)
	}
}
