package store

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAttachmentCRUD(t *testing.T) {
	tmp := t.TempDir()
	st, err := Open(filepath.Join(tmp, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer st.Close()

	note, err := st.CreateNote(Note{Title: "附件测试"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	content := []byte("abcd")
	att, err := st.CreateAttachment(note.ID, "报告.pdf", "application/pdf", int64(len(content)), "abc123", "rand1.pdf")
	if err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}

	p := st.AttachmentPath(att)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}
	if err := os.WriteFile(p, content, 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	got, err := st.GetAttachment(att.ID)
	if err != nil {
		t.Fatalf("GetAttachment: %v", err)
	}
	if got.Filename != "报告.pdf" {
		t.Errorf("Filename = %q, want %q", got.Filename, "报告.pdf")
	}
	if got.Mime != "application/pdf" {
		t.Errorf("Mime = %q, want %q", got.Mime, "application/pdf")
	}
	if got.Size != int64(len(content)) {
		t.Errorf("Size = %d, want %d", got.Size, len(content))
	}
	if got.SHA256 != "abc123" {
		t.Errorf("SHA256 = %q, want %q", got.SHA256, "abc123")
	}
	if got.NoteID != note.ID {
		t.Errorf("NoteID = %d, want %d", got.NoteID, note.ID)
	}

	att2, err := st.CreateAttachment(note.ID, "second.txt", "text/plain", 2, "def456", "rand2.txt")
	if err != nil {
		t.Fatalf("CreateAttachment(2): %v", err)
	}

	list, err := st.ListAttachments(note.ID)
	if err != nil {
		t.Fatalf("ListAttachments: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("ListAttachments len = %d, want 2", len(list))
	}
	if list[0].ID >= list[1].ID {
		t.Errorf("attachments not in ascending ID order: %d, %d", list[0].ID, list[1].ID)
	}
	if list[0].ID != att.ID || list[1].ID != att2.ID {
		t.Errorf("attachment IDs = [%d %d], want [%d %d]", list[0].ID, list[1].ID, att.ID, att2.ID)
	}

	deleted, err := st.DeleteAttachment(att.ID)
	if err != nil {
		t.Fatalf("DeleteAttachment: %v", err)
	}
	if deleted.ID != att.ID {
		t.Errorf("deleted.ID = %d, want %d", deleted.ID, att.ID)
	}
	if _, err := os.Stat(p); !os.IsNotExist(err) {
		t.Errorf("disk file still exists (stat err = %v)", err)
	}

	if _, err := st.GetAttachment(att.ID); !errors.Is(err, ErrNotFound) {
		t.Errorf("GetAttachment after delete = %v, want ErrNotFound", err)
	}
	if _, err := st.DeleteAttachment(att.ID); !errors.Is(err, ErrNotFound) {
		t.Errorf("DeleteAttachment twice = %v, want ErrNotFound", err)
	}
}

func TestCreateAttachmentNoteNotFound(t *testing.T) {
	tmp := t.TempDir()
	st, err := Open(filepath.Join(tmp, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer st.Close()

	_, err = st.CreateAttachment(99999, "x.txt", "text/plain", 1, "hash", "stored.txt")
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("CreateAttachment for missing note = %v, want ErrNotFound", err)
	}
}

func TestDeleteNoteCleansAttachmentDir(t *testing.T) {
	tmp := t.TempDir()
	st, err := Open(filepath.Join(tmp, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer st.Close()

	note, err := st.CreateNote(Note{Title: "清理测试"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	a1, err := st.CreateAttachment(note.ID, "a.txt", "text/plain", 3, "h1", "s1.txt")
	if err != nil {
		t.Fatalf("CreateAttachment(1): %v", err)
	}
	a2, err := st.CreateAttachment(note.ID, "b.txt", "text/plain", 3, "h2", "s2.txt")
	if err != nil {
		t.Fatalf("CreateAttachment(2): %v", err)
	}
	for _, a := range []Attachment{a1, a2} {
		p := st.AttachmentPath(a)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatalf("MkdirAll: %v", err)
		}
		if err := os.WriteFile(p, []byte("abc"), 0o644); err != nil {
			t.Fatalf("WriteFile: %v", err)
		}
	}

	dir := filepath.Join(st.AttachDir(), itoa(note.ID))
	if _, err := os.Stat(dir); err != nil {
		t.Fatalf("attachment dir should exist before delete: %v", err)
	}

	if err := st.DeleteNote(note.ID); err != nil {
		t.Fatalf("DeleteNote: %v", err)
	}

	if _, err := os.Stat(dir); !os.IsNotExist(err) {
		t.Errorf("attachment dir still exists after DeleteNote (stat err = %v)", err)
	}

	list, err := st.ListAttachments(note.ID)
	if err != nil {
		t.Fatalf("ListAttachments after DeleteNote: %v", err)
	}
	if len(list) != 0 {
		t.Errorf("ListAttachments len = %d, want 0", len(list))
	}
}

func TestAttachmentPathLayout(t *testing.T) {
	tmp := t.TempDir()
	st, err := Open(filepath.Join(tmp, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer st.Close()

	note, err := st.CreateNote(Note{Title: "路径测试"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	att, err := st.CreateAttachment(note.ID, "p.txt", "text/plain", 1, "h", "stored-name.txt")
	if err != nil {
		t.Fatalf("CreateAttachment: %v", err)
	}

	want := filepath.Join(st.AttachDir(), itoa(note.ID), "stored-name.txt")
	got := st.AttachmentPath(att)
	if got != want {
		t.Errorf("AttachmentPath = %q, want %q", got, want)
	}
	if !strings.HasPrefix(got, st.AttachDir()+string(filepath.Separator)) {
		t.Errorf("AttachmentPath %q not under attach dir %q", got, st.AttachDir())
	}
}

// itoa avoids importing strconv only for the store tests' formatting needs.
func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
