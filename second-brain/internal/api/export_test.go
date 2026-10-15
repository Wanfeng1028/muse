package api

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestExportJSON(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	id1 := createNoteViaAPI(t, srv, "第一篇")
	id2 := createNoteViaAPI(t, srv, "第二篇")

	put1 := doJSON(t, srv, http.MethodPut, "/api/notes/"+itoa64(id1),
		map[string]any{"title": "第一篇", "body": "c1", "tags": []string{"go"}})
	put1.Body.Close()
	if put1.StatusCode != http.StatusOK && put1.StatusCode != http.StatusNoContent {
		t.Fatalf("put note1 status = %d", put1.StatusCode)
	}
	put2 := doJSON(t, srv, http.MethodPut, "/api/notes/"+itoa64(id2),
		map[string]any{"title": "第二篇", "body": "c2", "tags": []string{"rust"}})
	put2.Body.Close()
	if put2.StatusCode != http.StatusOK && put2.StatusCode != http.StatusNoContent {
		t.Fatalf("put note2 status = %d", put2.StatusCode)
	}

	up := uploadFile(t, srv, id1, "file.txt", []byte("data"))
	defer up.Body.Close()
	if up.StatusCode != http.StatusCreated {
		raw, _ := io.ReadAll(up.Body)
		t.Fatalf("upload status = %d, body = %s", up.StatusCode, raw)
	}

	resp := doJSON(t, srv, http.MethodGet, "/api/export/json", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("export status = %d, body = %s", resp.StatusCode, raw)
	}
	cd := resp.Header.Get("Content-Disposition")
	if !strings.Contains(cd, "attachment") {
		t.Errorf("Content-Disposition = %q, want contains attachment", cd)
	}
	if !strings.Contains(cd, ".json") {
		t.Errorf("Content-Disposition = %q, want .json", cd)
	}

	type noteJSON struct {
		ID          int64    `json:"id"`
		Title       string   `json:"title"`
		Tags        []string `json:"tags"`
		Attachments []struct {
			Filename string `json:"filename"`
		} `json:"attachments"`
	}
	var out struct {
		Version    string     `json:"version"`
		ExportedAt string     `json:"exportedAt"`
		Notes      []noteJSON `json:"notes"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode export: %v", err)
	}
	if out.Version != "0.3.0" {
		t.Errorf("version = %q, want 0.3.0", out.Version)
	}
	if out.ExportedAt == "" {
		t.Errorf("exportedAt is empty")
	}
	if len(out.Notes) != 2 {
		t.Fatalf("notes len = %d, want 2", len(out.Notes))
	}

	var first *noteJSON
	for i := range out.Notes {
		if out.Notes[i].ID == id1 {
			first = &out.Notes[i]
		}
	}
	if first == nil {
		t.Fatalf("first note (id %d) not found in export", id1)
	}
	if len(first.Attachments) != 1 {
		t.Fatalf("first note attachments len = %d, want 1", len(first.Attachments))
	}
	if first.Attachments[0].Filename != "file.txt" {
		t.Errorf("attachment filename = %q, want %q", first.Attachments[0].Filename, "file.txt")
	}
}

func TestExportMarkdownZip(t *testing.T) {
	srv, _ := newAttachTestServer(t)
	defer srv.Close()

	// Note A with an attachment reference.
	idA := createNoteViaAPI(t, srv, "Go 学习笔记")

	content := append([]byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A}, bytes.Repeat([]byte("x"), 32)...)
	up := uploadFile(t, srv, idA, "diagram.png", content)
	up.Body.Close()
	if up.StatusCode != http.StatusCreated {
		t.Fatalf("upload png status = %d", up.StatusCode)
	}

	listResp := doJSON(t, srv, http.MethodGet, "/api/notes/"+itoa64(idA)+"/attachments", nil)
	var list []struct {
		ID int64 `json:"id"`
	}
	if err := json.NewDecoder(listResp.Body).Decode(&list); err != nil {
		listResp.Body.Close()
		t.Fatalf("decode list: %v", err)
	}
	listResp.Body.Close()
	if len(list) != 1 {
		t.Fatalf("attachments len = %d, want 1", len(list))
	}
	attID := list[0].ID

	body := "![图](attachment:" + itoa64(attID) + ")"
	put := doJSON(t, srv, http.MethodPut, "/api/notes/"+itoa64(idA),
		map[string]any{"title": "Go 学习笔记", "body": body})
	put.Body.Close()
	if put.StatusCode != http.StatusOK && put.StatusCode != http.StatusNoContent {
		t.Fatalf("put note A status = %d", put.StatusCode)
	}

	// Note B: ZipSlip-ish title.
	createNoteViaAPI(t, srv, "../../evil")

	resp := doJSON(t, srv, http.MethodGet, "/api/export/markdown", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("export status = %d, body = %s", resp.StatusCode, raw)
	}
	if ct := resp.Header.Get("Content-Type"); ct != "application/zip" {
		t.Errorf("Content-Type = %q, want application/zip", ct)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read zip: %v", err)
	}
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		t.Fatalf("zip.NewReader: %v", err)
	}

	var hasIndex bool
	var noteCount, attachCount int
	for _, f := range zr.File {
		if strings.Contains(f.Name, "..") {
			t.Errorf("zip entry %q contains ..", f.Name)
		}
		switch {
		case f.Name == "index.md":
			hasIndex = true
		case strings.HasPrefix(f.Name, "notes/"):
			noteCount++
		case strings.HasPrefix(f.Name, "attachments/"):
			attachCount++
		}
	}
	if !hasIndex {
		t.Errorf("index.md missing from zip")
	}
	if noteCount != 2 {
		t.Errorf("notes/ entries = %d, want 2", noteCount)
	}
	if attachCount != 1 {
		t.Errorf("attachments/ entries = %d, want 1", attachCount)
	}

	var noteAMD string
	for _, f := range zr.File {
		if !strings.HasPrefix(f.Name, "notes/") {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			t.Fatalf("open %s: %v", f.Name, err)
		}
		b, err := io.ReadAll(rc)
		rc.Close()
		if err != nil {
			t.Fatalf("read %s: %v", f.Name, err)
		}
		if strings.Contains(string(b), "Go 学习笔记") {
			noteAMD = string(b)
		}
	}
	if noteAMD == "" {
		t.Fatalf("note A markdown not found in zip")
	}
	if !strings.Contains(noteAMD, `title: "Go 学习笔记"`) {
		t.Errorf("note A markdown missing title header; got:\n%s", noteAMD)
	}
	if !strings.Contains(noteAMD, "../attachments/") {
		t.Errorf("note A markdown missing rewritten ../attachments/ reference; got:\n%s", noteAMD)
	}
	if strings.Contains(noteAMD, "attachment:") {
		t.Errorf("note A markdown still contains raw attachment: reference; got:\n%s", noteAMD)
	}

	for _, f := range zr.File {
		if !strings.HasPrefix(f.Name, "attachments/") {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			t.Fatalf("open %s: %v", f.Name, err)
		}
		b, err := io.ReadAll(rc)
		rc.Close()
		if err != nil {
			t.Fatalf("read %s: %v", f.Name, err)
		}
		if !bytes.Equal(b, content) {
			t.Errorf("attachment content mismatch: got %d bytes, want %d", len(b), len(content))
		}
	}
}

func TestSanitizeZipName(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"../../etc/passwd", "etc-passwd"},
		{"正常标题", "正常标题"},
		{"", "note"},
		{"a/b\\c", "a-b-c"},
	}
	for _, c := range cases {
		got := sanitizeZipName(c.in)
		if got != c.want {
			t.Errorf("sanitizeZipName(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func jsonString(s string) string {
	b, _ := json.Marshal(s)
	return string(b)
}
