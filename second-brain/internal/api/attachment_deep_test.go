package api

import (
	"bytes"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	st.SetAttachDir(filepath.Join(dir, "attachments"))
	t.Cleanup(func() { st.Close() })
	return st
}

func newMux(st *store.Store) *http.ServeMux {
	mux := http.NewServeMux()
	RegisterAttachmentRoutes(mux, st)
	return mux
}

func mkMultipart(t *testing.T, field, filename string, content []byte) (*bytes.Buffer, string) {
	t.Helper()
	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)
	fw, err := w.CreateFormFile(field, filename)
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}
	if _, err := fw.Write(content); err != nil {
		t.Fatalf("write form file: %v", err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("close writer: %v", err)
	}
	return &buf, w.FormDataContentType()
}

func pngBytes() []byte {
	return []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
		0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
		0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
		0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
		0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
		0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
		0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
		0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
		0x42, 0x60, 0x82}
}

func TestSanitizeFilename_Deep(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"path traversal", "../../etc/passwd", "passwd"},
		{"windows backslash", `..\..\win\system32\cmd.exe`, "winsystem32cmd.exe"},
		{"colon and star", "a:b*c?.txt", "abc.txt"},
		{"control chars", "a\x01b\x7fc.txt", "abc.txt"},
		{"leading dots and spaces", "  ..hidden..  ", "hidden"},
		{"empty after trim", "...   ", "file"},
		{"quote and pipe", `we"ird|name<>`, "weirdname"},
		{"chinese preserved", "笔记附件.png", "笔记附件.png"},
		{"long name truncated", strings.Repeat("a", 200) + ".txt", strings.Repeat("a", 120)},
		{"nul byte removed", "a\x00b.txt", "ab.txt"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := sanitizeFilename(c.in)
			if got != c.want {
				t.Fatalf("sanitizeFilename(%q) = %q, want %q", c.in, got, c.want)
			}
			if strings.ContainsAny(got, `/\:*?"<>|`) {
				t.Fatalf("result still contains unsafe chars: %q", got)
			}
			if len([]rune(got)) > 120 {
				t.Fatalf("result exceeds 120 runes: %d", len([]rune(got)))
			}
		})
	}
}

func TestAttachMaxBytes_Env(t *testing.T) {
	cases := []struct {
		name string
		env  string
		want int64
	}{
		{"unset", "", 10 << 20},
		{"valid", "5", 5 << 20},
		{"zero ignored", "0", 10 << 20},
		{"negative ignored", "-3", 10 << 20},
		{"garbage ignored", "abc", 10 << 20},
		{"spaces trimmed", "  7  ", 7 << 20},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			old, had := os.LookupEnv("SB_ATTACH_MAX_MB")
			defer func() {
				if had {
					os.Setenv("SB_ATTACH_MAX_MB", old)
				} else {
					os.Unsetenv("SB_ATTACH_MAX_MB")
				}
			}()
			if c.env == "" {
				os.Unsetenv("SB_ATTACH_MAX_MB")
			} else {
				os.Setenv("SB_ATTACH_MAX_MB", c.env)
			}
			got := attachMaxBytes()
			if got != c.want {
				t.Fatalf("attachMaxBytes() = %d, want %d", got, c.want)
			}
			if got <= 0 {
				t.Fatalf("attachMaxBytes() must be positive, got %d", got)
			}
		})
	}
}

func TestUploadAttachment_ExtensionWhitelist(t *testing.T) {
	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	cases := []struct {
		name       string
		filename   string
		content    []byte
		wantStatus int
	}{
		{"png ok", "pic.png", pngBytes(), http.StatusCreated},
		{"uppercase ext normalized", "PIC.PNG", pngBytes(), http.StatusCreated},
		{"double ext picks last", "evil.png.exe", []byte("MZ"), http.StatusUnsupportedMediaType},
		{"no ext rejected", "plainfile", []byte("hello"), http.StatusUnsupportedMediaType},
		{"sh rejected", "script.sh", []byte("#!/bin/sh"), http.StatusUnsupportedMediaType},
		{"svg rejected", "vector.svg", []byte("<svg/>"), http.StatusUnsupportedMediaType},
		{"png with wrong content", "fake.png", []byte("not an image at all"), http.StatusUnsupportedMediaType},
		{"trailing dot stripped", "photo.png.", pngBytes(), http.StatusCreated},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			body, ct := mkMultipart(t, "file", c.filename, c.content)
			req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
			req.Header.Set("Content-Type", ct)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)
			if rec.Code != c.wantStatus {
				t.Fatalf("status = %d, want %d, body=%s", rec.Code, c.wantStatus, rec.Body.String())
			}
			if c.wantStatus == http.StatusCreated {
				var a store.Attachment
				if err := json.Unmarshal(rec.Body.Bytes(), &a); err != nil {
					t.Fatalf("decode: %v", err)
				}
				if a.ID == 0 || a.NoteID != note.ID {
					t.Fatalf("bad attachment: %+v", a)
				}
			}
		})
	}
}

func TestUploadAttachment_PathTraversalName(t *testing.T) {
	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	body, ct := mkMultipart(t, "file", "../../../../tmp/evil.png", pngBytes())
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want 201, body=%s", rec.Code, rec.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &a); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if a.Filename != "evil.png" {
		t.Fatalf("filename = %q, want evil.png", a.Filename)
	}
	dir := filepath.Join(st.AttachDir(), itoaAttachment(note.ID))
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("read dir: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 stored file, got %d", len(entries))
	}
	stored := entries[0].Name()
	if !strings.HasSuffix(stored, ".png") {
		t.Fatalf("stored name should end with .png: %q", stored)
	}
	if strings.Contains(stored, "..") || strings.ContainsAny(stored, `/\`) {
		t.Fatalf("stored name not sanitized: %q", stored)
	}
}

func TestUploadAttachment_OversizeRejected(t *testing.T) {
	old, had := os.LookupEnv("SB_ATTACH_MAX_MB")
	defer func() {
		if had {
			os.Setenv("SB_ATTACH_MAX_MB", old)
		} else {
			os.Unsetenv("SB_ATTACH_MAX_MB")
		}
	}()
	os.Setenv("SB_ATTACH_MAX_MB", "1")

	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	big := bytes.Repeat([]byte("A"), 2<<20)
	body, ct := mkMultipart(t, "file", "big.png", big)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status = %d, want 413, body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "附件超过大小限制") {
		t.Fatalf("expected size limit message, got %s", rec.Body.String())
	}
	dir := filepath.Join(st.AttachDir(), itoaAttachment(note.ID))
	if entries, err := os.ReadDir(dir); err == nil && len(entries) != 0 {
		t.Fatalf("no file should be stored on oversize, got %d", len(entries))
	}
}

func TestListAttachments_EmptyAndNonEmpty(t *testing.T) {
	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", nil)
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("empty list status = %d", rec.Code)
	}
	var list []store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &list); err != nil {
		t.Fatalf("decode empty: %v", err)
	}
	if list == nil {
		t.Fatalf("expected non-nil empty slice")
	}
	if len(list) != 0 {
		t.Fatalf("expected 0, got %d", len(list))
	}

	body, ct := mkMultipart(t, "file", "a.png", pngBytes())
	req = httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec = httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload status = %d", rec.Code)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", nil)
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list status = %d", rec.Code)
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &list); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1, got %d", len(list))
	}
	if list[0].Filename != "a.png" {
		t.Fatalf("filename = %q", list[0].Filename)
	}
}

func TestDownloadAttachment_MissingNoteAndFile(t *testing.T) {
	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/notes/99999/attachments", nil)
	req.SetPathValue("id", "99999")
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("missing note status = %d, want 404", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "note not found") {
		t.Fatalf("expected note not found, got %s", rec.Body.String())
	}

	body, ct := mkMultipart(t, "file", "gone.png", pngBytes())
	req = httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec = httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload status = %d", rec.Code)
	}
	var a store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &a); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if err := os.Remove(st.AttachmentPath(a)); err != nil {
		t.Fatalf("remove stored file: %v", err)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/api/attachments/"+itoaAttachment(a.ID), nil)
	req.SetPathValue("id", itoaAttachment(a.ID))
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("missing file status = %d, want 500, body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "附件文件丢失") {
		t.Fatalf("expected file missing message, got %s", rec.Body.String())
	}
}

func TestDownloadAttachment_ContentDispositionQuoted(t *testing.T) {
	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	body, ct := mkMultipart(t, "file", `we"ird.png`, pngBytes())
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload status = %d, body=%s", rec.Code, rec.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &a); err != nil {
		t.Fatalf("decode: %v", err)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/api/attachments/"+itoaAttachment(a.ID), nil)
	req.SetPathValue("id", itoaAttachment(a.ID))
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("download status = %d, body=%s", rec.Code, rec.Body.String())
	}
	cd := rec.Header().Get("Content-Disposition")
	if !strings.HasPrefix(cd, "inline; filename=\"") {
		t.Fatalf("unexpected Content-Disposition: %q", cd)
	}
	if strings.Count(cd, `"`) != 2 {
		t.Fatalf("filename quotes not escaped: %q", cd)
	}
	if rec.Header().Get("Content-Type") == "" {
		t.Fatalf("missing Content-Type header")
	}
	if rec.Body.Len() == 0 {
		t.Fatalf("empty body")
	}
}

func TestDeleteAttachment_RemovesFileAndRecord(t *testing.T) {
	st := newTestStore(t)
	note, err := st.CreateNote(store.Note{Title: "t", Body: "b"})
	if err != nil {
		t.Fatalf("create note: %v", err)
	}
	mux := newMux(st)

	body, ct := mkMultipart(t, "file", "del.png", pngBytes())
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload status = %d", rec.Code)
	}
	var a store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &a); err != nil {
		t.Fatalf("decode: %v", err)
	}
	path := st.AttachmentPath(a)
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("stored file missing: %v", err)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodDelete, "/api/attachments/"+itoaAttachment(a.ID), nil)
	req.SetPathValue("id", itoaAttachment(a.ID))
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK && rec.Code != http.StatusNoContent {
		t.Fatalf("delete status = %d, body=%s", rec.Code, rec.Body.String())
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("file should be removed, stat err = %v", err)
	}
	if _, err := st.GetAttachment(a.ID); err == nil {
		t.Fatalf("record should be removed")
	}
}

func TestAttachment_MultiUserIsolation(t *testing.T) {
	st := newTestStore(t)
	n1, err := st.CreateNote(store.Note{Title: "user1", Body: "body1"})
	if err != nil {
		t.Fatalf("create n1: %v", err)
	}
	n2, err := st.CreateNote(store.Note{Title: "user2", Body: "body2"})
	if err != nil {
		t.Fatalf("create n2: %v", err)
	}
	if n1.ID == n2.ID {
		t.Fatalf("note ids must differ")
	}
	mux := newMux(st)

	body, ct := mkMultipart(t, "file", "u1.png", pngBytes())
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoaAttachment(n1.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload n1 status = %d", rec.Code)
	}
	var a1 store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &a1); err != nil {
		t.Fatalf("decode: %v", err)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/api/notes/"+itoaAttachment(n2.ID)+"/attachments", nil)
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list n2 status = %d", rec.Code)
	}
	var list []store.Attachment
	if err := json.Unmarshal(rec.Body.Bytes(), &list); err != nil {
		t.Fatalf("decode n2 list: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("user2 must not see user1 attachments, got %d", len(list))
	}

	dir1 := filepath.Join(st.AttachDir(), itoaAttachment(n1.ID))
	dir2 := filepath.Join(st.AttachDir(), itoaAttachment(n2.ID))
	if dir1 == dir2 {
		t.Fatalf("attach dirs must differ per note")
	}
	if _, err := os.Stat(dir1); err != nil {
		t.Fatalf("dir1 missing: %v", err)
	}
	if _, err := os.Stat(dir2); !os.IsNotExist(err) {
		t.Fatalf("dir2 should not exist yet")
	}
}

func itoaAttachment(v int64) string {
	return strconvFormatInt(v)
}

func strconvFormatInt(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var b [20]byte
	i := len(b)
	for v > 0 {
		i--
		b[i] = byte('0' + v%10)
		v /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

var _ = time.Now
