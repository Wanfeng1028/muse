package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestUpload_PngRealHeader_Passes(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	png := pngBytes()
	body, ct := mkMultipart(t, "file", "pic.png", png)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 201 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, w.Body.String())
	}
	if a.Mime != "image/png" {
		t.Fatalf("mime=%q", a.Mime)
	}
	if a.Size != int64(len(png)) {
		t.Fatalf("size=%d want %d", a.Size, len(png))
	}
}

func TestUpload_PngExtTextContent_Rejected(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	body, ct := mkMultipart(t, "file", "pic.png", []byte("this is definitely plain text"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 415 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "文件内容与扩展名不符") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestUpload_JpgExtTextContent_Rejected(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	body, ct := mkMultipart(t, "file", "a.jpg", []byte("plain text body here"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 415 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "文件内容与扩展名不符") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestUpload_TxtAnyContent_Passes(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	content := []byte{0x00, 0x01, 0xff, 0xfe, 0x42, 0x00}
	body, ct := mkMultipart(t, "file", "data.txt", content)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 201 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if a.Size != int64(len(content)) {
		t.Fatalf("size=%d want %d", a.Size, len(content))
	}
}

func TestUpload_NoExtension_Rejected(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	body, ct := mkMultipart(t, "file", "README", []byte("hello"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 415 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "不支持的文件类型") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestUpload_UppercaseExt_Passes(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	png := pngBytes()
	body, ct := mkMultipart(t, "file", "PIC.PNG", png)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 201 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if a.Mime != "image/png" {
		t.Fatalf("mime=%q", a.Mime)
	}
	if a.Size != int64(len(png)) {
		t.Fatalf("size=%d", a.Size)
	}
}

func TestUpload_DoubleExt_UsesLastExt(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	body, ct := mkMultipart(t, "file", "evil.png.exe", []byte("plain"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 415 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "不支持的文件类型") {
		t.Fatalf("body=%s", w.Body.String())
	}
	if !strings.Contains(w.Body.String(), ".exe") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestUpload_AllDotsFilename_Rejected(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	body, ct := mkMultipart(t, "file", "...", []byte("x"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 415 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "不支持的文件类型") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestUpload_LongUnicodeFilename_Truncated(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	// 150 个中文字符 + ".txt" = 154 rune。sanitizeFilename 先对整个文件名
	// （含扩展名）按 rune 截断到 120，扩展名 ".txt" 被完全切掉 → ext="" →
	// 不在白名单 → 415。这是源码的真实行为，测试按此断言。
	name := strings.Repeat("中", 150) + ".txt"
	body, ct := mkMultipart(t, "file", name, []byte("hello"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusUnsupportedMediaType {
		t.Fatalf("expected 415 (extension lost after rune truncation to 120), got %d body=%s", w.Code, w.Body.String())
	}
}

func TestUpload_LongUnicodeFilename_UnderLimit_Passes(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	// 115 个中文字符 + ".txt" = 119 rune，小于 120 的截断阈值，扩展名保留 → 201。
	name := strings.Repeat("中", 115) + ".txt"
	if got := len([]rune(name)); got != 119 {
		t.Fatalf("precondition failed: expected 119 runes, got %d", got)
	}
	body, ct := mkMultipart(t, "file", name, []byte("hello"))
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got := len([]rune(a.Filename)); got != 119 {
		t.Fatalf("expected filename rune length 119, got %d (filename=%q)", got, a.Filename)
	}
}

func TestUpload_ExactlyMaxBytes_Passes(t *testing.T) {
	t.Setenv("SB_ATTACH_MAX_MB", "1")
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	content := bytes.Repeat([]byte("a"), 1<<20)
	body, ct := mkMultipart(t, "file", "big.txt", content)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 201 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if a.Size != int64(1<<20) {
		t.Fatalf("size=%d", a.Size)
	}
}

func TestUpload_MaxBytesPlusOne_Rejected(t *testing.T) {
	t.Setenv("SB_ATTACH_MAX_MB", "1")
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	content := bytes.Repeat([]byte("a"), (1<<20)+1)
	body, ct := mkMultipart(t, "file", "big.txt", content)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 413 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "附件超过大小限制（1 MB）") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestUpload_SameContentTwice_StoredNamesDiffer(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	png := pngBytes()
	do := func() store.Attachment {
		body, ct := mkMultipart(t, "file", "pic.png", png)
		req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
		req.Header.Set("Content-Type", ct)
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, req)
		if w.Code != 201 {
			t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
		}
		var a store.Attachment
		if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		return a
	}
	a1 := do()
	a2 := do()
	if a1.StoredName == a2.StoredName {
		t.Fatalf("stored names equal: %q", a1.StoredName)
	}
	if len(a1.StoredName) != 16+len(".png") {
		t.Fatalf("storedName=%q len=%d", a1.StoredName, len(a1.StoredName))
	}
	if a1.SHA256 != a2.SHA256 {
		t.Fatalf("sha256 differ: %q vs %q", a1.SHA256, a2.SHA256)
	}
	if a1.SHA256 == "" {
		t.Fatalf("sha256 empty")
	}
}

func TestDownload_MissingFileOnDisk_500(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	a, err := st.CreateAttachment(note.ID, "ghost.png", "image/png", 123, "deadbeef", "0000000000000000.png")
	if err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}
	if _, err := os.Stat(st.AttachmentPath(a)); !os.IsNotExist(err) {
		t.Fatalf("expected file missing, stat err=%v", err)
	}
	req := httptest.NewRequest(http.MethodGet, "/api/attachments/"+itoa(a.ID), nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 500 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "附件文件丢失") {
		t.Fatalf("body=%s", w.Body.String())
	}
}

func TestDeleteAttachment_ThenDownload_404(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	png := pngBytes()
	body, ct := mkMultipart(t, "file", "pic.png", png)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 201 {
		t.Fatalf("upload status=%d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	delReq := httptest.NewRequest(http.MethodDelete, "/api/attachments/"+itoa(a.ID), nil)
	delW := httptest.NewRecorder()
	mux.ServeHTTP(delW, delReq)
	if delW.Code != 204 {
		t.Fatalf("delete status=%d body=%s", delW.Code, delW.Body.String())
	}
	getReq := httptest.NewRequest(http.MethodGet, "/api/attachments/"+itoa(a.ID), nil)
	getW := httptest.NewRecorder()
	mux.ServeHTTP(getW, getReq)
	if getW.Code != 404 {
		t.Fatalf("get status=%d body=%s", getW.Code, getW.Body.String())
	}
}

func TestDeleteNote_CascadesAttachmentThroughAPI(t *testing.T) {
	st := newTestStore(t)
	mux := newMux(st)
	note, err := st.CreateNote(store.Note{Title: "n", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	png := pngBytes()
	body, ct := mkMultipart(t, "file", "pic.png", png)
	req := httptest.NewRequest(http.MethodPost, "/api/notes/"+itoa(note.ID)+"/attachments", body)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != 201 {
		t.Fatalf("upload status=%d body=%s", w.Code, w.Body.String())
	}
	var a store.Attachment
	if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	attachPath := st.AttachmentPath(a)
	dir := filepath.Dir(attachPath)
	if _, err := os.Stat(attachPath); err != nil {
		t.Fatalf("expected file on disk: %v", err)
	}
	if err := st.DeleteNote(note.ID); err != nil {
		t.Fatalf("DeleteNote: %v", err)
	}
	if _, err := os.Stat(dir); !os.IsNotExist(err) {
		t.Fatalf("expected attach dir gone, stat err=%v", err)
	}
	getReq := httptest.NewRequest(http.MethodGet, "/api/attachments/"+itoa(a.ID), nil)
	getW := httptest.NewRecorder()
	mux.ServeHTTP(getW, getReq)
	if getW.Code != 404 {
		t.Fatalf("get status=%d body=%s", getW.Code, getW.Body.String())
	}
}
