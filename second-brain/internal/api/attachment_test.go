package api

import (
	"bytes"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newAttachTestServer(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	st.SetAttachDir(t.TempDir())
	t.Cleanup(func() { _ = st.Close() })
	return httptest.NewServer(NewServer(st)), st
}

func createNoteViaAPI(t *testing.T, srv *httptest.Server, title string) int64 {
	t.Helper()
	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{"title": title})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("createNoteViaAPI status = %d, body = %s", resp.StatusCode, raw)
	}
	var out struct {
		ID int64 `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode note: %v", err)
	}
	if out.ID == 0 {
		t.Fatalf("createNoteViaAPI returned id 0")
	}
	return out.ID
}

func uploadFile(t *testing.T, srv *httptest.Server, noteID int64, filename string, content []byte) *http.Response {
	t.Helper()
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	fw, err := mw.CreateFormFile("file", filename)
	if err != nil {
		t.Fatalf("CreateFormFile: %v", err)
	}
	if _, err := fw.Write(content); err != nil {
		t.Fatalf("write form file: %v", err)
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("mw.Close: %v", err)
	}

	url := srv.URL + "/api/notes/" + itoa64(noteID) + "/attachments"
	req, err := http.NewRequest(http.MethodPost, url, &buf)
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())
	resp, err := srv.Client().Do(req)
	if err != nil {
		t.Fatalf("upload: %v", err)
	}
	return resp
}

func itoa64(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

func TestUploadDownloadDeleteAttachment(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	noteID := createNoteViaAPI(t, srv, "上传下载")

	content := []byte("hello attachment")
	resp := uploadFile(t, srv, noteID, "hello.txt", content)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("upload status = %d, body = %s", resp.StatusCode, raw)
	}

	var att struct {
		ID       int64  `json:"id"`
		Filename string `json:"filename"`
		Mime     string `json:"mime"`
		Size     int64  `json:"size"`
		SHA256   string `json:"sha256"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&att); err != nil {
		t.Fatalf("decode attachment: %v", err)
	}
	if att.Filename != "hello.txt" {
		t.Errorf("filename = %q, want %q", att.Filename, "hello.txt")
	}
	if !strings.HasPrefix(att.Mime, "text/plain") {
		t.Errorf("mime = %q, want prefix text/plain", att.Mime)
	}
	if att.Size != int64(len(content)) {
		t.Errorf("size = %d, want %d", att.Size, len(content))
	}
	if len(att.SHA256) != 64 {
		t.Errorf("sha256 len = %d, want 64 (%q)", len(att.SHA256), att.SHA256)
	}

	// list
	listResp := doJSON(t, srv, http.MethodGet, "/api/notes/"+itoa64(noteID)+"/attachments", nil)
	defer listResp.Body.Close()
	if listResp.StatusCode != http.StatusOK {
		t.Fatalf("list status = %d", listResp.StatusCode)
	}
	var list []map[string]any
	if err := json.NewDecoder(listResp.Body).Decode(&list); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("list len = %d, want 1", len(list))
	}

	// download
	dlResp := doJSON(t, srv, http.MethodGet, "/api/attachments/"+itoa64(att.ID), nil)
	defer dlResp.Body.Close()
	if dlResp.StatusCode != http.StatusOK {
		t.Fatalf("download status = %d", dlResp.StatusCode)
	}
	if ct := dlResp.Header.Get("Content-Type"); !strings.HasPrefix(ct, "text/plain") {
		t.Errorf("download Content-Type = %q, want prefix text/plain", ct)
	}
	got, err := io.ReadAll(dlResp.Body)
	if err != nil {
		t.Fatalf("read download body: %v", err)
	}
	if !bytes.Equal(got, content) {
		t.Errorf("download body = %q, want %q", got, content)
	}

	// delete
	delResp := doJSON(t, srv, http.MethodDelete, "/api/attachments/"+itoa64(att.ID), nil)
	defer delResp.Body.Close()
	if delResp.StatusCode != http.StatusNoContent {
		t.Fatalf("delete status = %d, want 204", delResp.StatusCode)
	}

	// download again -> 404
	dlResp2 := doJSON(t, srv, http.MethodGet, "/api/attachments/"+itoa64(att.ID), nil)
	defer dlResp2.Body.Close()
	if dlResp2.StatusCode != http.StatusNotFound {
		t.Errorf("download after delete status = %d, want 404", dlResp2.StatusCode)
	}

	// delete again -> 404
	delResp2 := doJSON(t, srv, http.MethodDelete, "/api/attachments/"+itoa64(att.ID), nil)
	defer delResp2.Body.Close()
	if delResp2.StatusCode != http.StatusNotFound {
		t.Errorf("delete after delete status = %d, want 404", delResp2.StatusCode)
	}
}

func TestUploadImageAndSniff(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	noteID := createNoteViaAPI(t, srv, "图片")

	png := append([]byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A}, make([]byte, 100)...)
	resp := uploadFile(t, srv, noteID, "img.png", png)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("upload png status = %d, body = %s", resp.StatusCode, raw)
	}
	var att struct {
		Mime string `json:"mime"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&att); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if att.Mime != "image/png" {
		t.Errorf("mime = %q, want image/png", att.Mime)
	}
}

func TestUploadTooLarge(t *testing.T) {
	t.Setenv("SB_ATTACH_MAX_MB", "1")
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	noteID := createNoteViaAPI(t, srv, "太大")

	big := bytes.Repeat([]byte("a"), 2*1024*1024)
	resp := uploadFile(t, srv, noteID, "big.txt", big)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusRequestEntityTooLarge {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 413, body = %s", resp.StatusCode, raw)
	}
	raw, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(raw), "1 MB") {
		t.Errorf("error body = %q, want contains %q", raw, "1 MB")
	}
}

func TestUploadBadExtension(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	noteID := createNoteViaAPI(t, srv, "坏扩展")

	resp := uploadFile(t, srv, noteID, "evil.exe", []byte("MZ"))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnsupportedMediaType {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 415, body = %s", resp.StatusCode, raw)
	}
}

func TestUploadMimeMismatch(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	noteID := createNoteViaAPI(t, srv, "类型不符")

	resp := uploadFile(t, srv, noteID, "fake.png", []byte("just text"))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnsupportedMediaType {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 415, body = %s", resp.StatusCode, raw)
	}
}

func TestUploadPathTraversalSanitized(t *testing.T) {
	srv, st := newAttachTestServer(t)
	defer srv.Close()

	noteID := createNoteViaAPI(t, srv, "路径穿越")

	resp := uploadFile(t, srv, noteID, "../../../etc/passwd.txt", []byte("x"))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 201, body = %s", resp.StatusCode, raw)
	}
	var att struct {
		ID       int64  `json:"id"`
		Filename string `json:"filename"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&att); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if strings.Contains(att.Filename, "/") {
		t.Errorf("filename = %q, must not contain /", att.Filename)
	}
	if strings.Contains(att.Filename, "..") {
		t.Errorf("filename = %q, must not contain ..", att.Filename)
	}
	if att.Filename != "passwd.txt" {
		t.Errorf("filename = %q, want %q", att.Filename, "passwd.txt")
	}

	stored, err := st.GetAttachment(att.ID)
	if err != nil {
		t.Fatalf("GetAttachment: %v", err)
	}
	p := st.AttachmentPath(stored)
	if _, err := os.Stat(p); err != nil {
		t.Errorf("stored file %q missing: %v", p, err)
	}
	if !strings.HasPrefix(p, st.AttachDir()+string(filepath.Separator)) {
		t.Errorf("stored path %q escapes attach dir %q", p, st.AttachDir())
	}
}

func TestUploadNoteNotFound(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	resp := uploadFile(t, srv, 99999, "x.txt", []byte("x"))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 404, body = %s", resp.StatusCode, raw)
	}
}

func TestListAttachmentsNoteNotFound(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/notes/99999/attachments", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 404, body = %s", resp.StatusCode, raw)
	}
}
