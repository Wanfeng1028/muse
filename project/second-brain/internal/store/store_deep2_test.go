package store

import (
	"context"
	"fmt"
	"path/filepath"
	"reflect"
	"sync"
	"testing"
)

func TestOpenTwice_Idempotent_Deep2(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "twice.db")

	s1, err := Open(dbPath)
	if err != nil {
		t.Fatalf("first Open failed: %v", err)
	}
	n, err := s1.CreateNote(Note{Title: "persisted", Body: "hello"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if n.ID == 0 {
		t.Fatalf("expected non-zero note id after CreateNote")
	}
	if err := s1.Close(); err != nil {
		t.Fatalf("Close first store failed: %v", err)
	}

	s2, err := Open(dbPath)
	if err != nil {
		t.Fatalf("second Open failed: %v", err)
	}
	defer s2.Close()

	got, err := s2.GetNote(n.ID)
	if err != nil {
		t.Fatalf("GetNote after reopen failed: %v", err)
	}
	if got.ID != n.ID {
		t.Fatalf("GetNote returned id=%d, want %d", got.ID, n.ID)
	}
	if got.Title != "persisted" {
		t.Fatalf("GetNote title=%q, want %q", got.Title, "persisted")
	}
	if got.Body != "hello" {
		t.Fatalf("GetNote body=%q, want %q", got.Body, "hello")
	}
}

func TestOpen_CreatesNestedDir_Deep2(t *testing.T) {
	nested := filepath.Join(t.TempDir(), "a", "b", "deep.db")
	s, err := Open(nested)
	if err != nil {
		t.Fatalf("Open with nested path failed: %v", err)
	}
	defer s.Close()

	n, err := s.CreateNote(Note{Title: "nested", Body: "x"})
	if err != nil {
		t.Fatalf("CreateNote on nested-dir store failed: %v", err)
	}
	if n.ID == 0 {
		t.Fatalf("expected non-zero id after CreateNote on nested-dir store")
	}
}

func TestForeignKeyViolation_Deep2(t *testing.T) {
	s := newDeepTestStore(t)

	_, err := s.db.Exec(`INSERT INTO reviews(note_id, user_id, ef, interval_days, repetitions, due_date) VALUES(999999, 'local', 2.5, 0, 0, '2026-10-19')`)
	if err == nil {
		t.Fatalf("expected foreign key violation error, got nil")
	}
}

func TestTagsUniqueConstraint_Deep2(t *testing.T) {
	s := newDeepTestStore(t)

	if _, err := s.db.Exec(`INSERT INTO tags(name) VALUES('duptag')`); err != nil {
		t.Fatalf("first tag insert failed: %v", err)
	}
	_, err := s.db.Exec(`INSERT INTO tags(name) VALUES('duptag')`)
	if err == nil {
		t.Fatalf("expected UNIQUE constraint error on duplicate tag, got nil")
	}
}

func TestNoteTagsPrimaryKey_Deep2(t *testing.T) {
	s := newDeepTestStore(t)
	nid := seedNote(t, s, "pktag note", "body")

	if _, err := s.db.Exec(`INSERT INTO tags(name) VALUES('pktag')`); err != nil {
		t.Fatalf("insert tag failed: %v", err)
	}
	var tid int64
	if err := s.db.QueryRow(`SELECT id FROM tags WHERE name = ?`, "pktag").Scan(&tid); err != nil {
		t.Fatalf("select tag id failed: %v", err)
	}

	if _, err := s.db.Exec(`INSERT INTO note_tags(note_id, tag_id) VALUES(?,?)`, nid, tid); err != nil {
		t.Fatalf("first note_tags insert failed: %v", err)
	}
	_, err := s.db.Exec(`INSERT INTO note_tags(note_id, tag_id) VALUES(?,?)`, nid, tid)
	if err == nil {
		t.Fatalf("expected composite primary key conflict, got nil")
	}
}

func TestCascadeDeleteReviews_Deep2(t *testing.T) {
	s := newDeepTestStore(t)
	nid := seedNote(t, s, "cascade note", "body")

	var c1 int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM reviews WHERE note_id=?`, nid).Scan(&c1); err != nil {
		t.Fatalf("count reviews before delete failed: %v", err)
	}
	if c1 != 1 {
		t.Fatalf("reviews before delete = %d, want 1", c1)
	}

	if err := s.DeleteNote(nid); err != nil {
		t.Fatalf("DeleteNote failed: %v", err)
	}

	var c2 int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM reviews WHERE note_id=?`, nid).Scan(&c2); err != nil {
		t.Fatalf("count reviews after delete failed: %v", err)
	}
	if c2 != 0 {
		t.Fatalf("reviews after delete = %d, want 0 (cascade)", c2)
	}
}

func TestListNotes_LimitOffsetClamp_Deep2(t *testing.T) {
	s := newDeepTestStore(t)
	seedNote(t, s, "n1", "b1")
	seedNote(t, s, "n2", "b2")
	seedNote(t, s, "n3", "b3")

	notes, err := s.ListNotes("", 0, -5)
	if err != nil {
		t.Fatalf("ListNotes with limit=0 offset=-5 failed: %v", err)
	}
	if len(notes) != 3 {
		t.Fatalf("ListNotes returned %d notes, want 3", len(notes))
	}
}

func TestSearchNotes_EmptyQueryReturnsAll_Deep2(t *testing.T) {
	s := newDeepTestStore(t)
	seedNote(t, s, "alpha", "first")
	seedNote(t, s, "beta", "second")

	got1, err := s.SearchNotes("")
	if err != nil {
		t.Fatalf("SearchNotes empty failed: %v", err)
	}
	if len(got1) != 2 {
		t.Fatalf("SearchNotes(\"\") returned %d notes, want 2", len(got1))
	}

	got2, err := s.SearchNotes(" ")
	if err != nil {
		t.Fatalf("SearchNotes spaces failed: %v", err)
	}
	if len(got2) != 2 {
		t.Fatalf("SearchNotes(\" \") returned %d notes, want 2", len(got2))
	}
}

func TestNormalizeTags_Deep2(t *testing.T) {
	got := normalizeTags([]string{" Go ", "go", "", " ", "Python", "PYTHON"})
	want := []string{"go", "python"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("normalizeTags = %#v, want %#v", got, want)
	}
}

func TestConcurrentCreateNotes_NoRace_Deep2(t *testing.T) {
	s := newDeepTestStore(t)

	const goroutines = 20
	const perGoroutine = 5

	var wg sync.WaitGroup
	errCh := make(chan error, goroutines*perGoroutine)

	for g := 0; g < goroutines; g++ {
		wg.Add(1)
		go func(g int) {
			defer wg.Done()
			for i := 0; i < perGoroutine; i++ {
				title := fmt.Sprintf("c-%d-%d", g, i)
				if _, err := s.CreateNote(Note{Title: title, Body: "concurrent"}); err != nil {
					errCh <- fmt.Errorf("CreateNote(%s): %w", title, err)
					return
				}
			}
		}(g)
	}

	wg.Wait()
	close(errCh)

	for err := range errCh {
		t.Fatalf("concurrent CreateNote failed: %v", err)
	}

	notes, err := s.ListNotes("", 0, 0)
	if err != nil {
		t.Fatalf("ListNotes after concurrent creates failed: %v", err)
	}
	if len(notes) != goroutines*perGoroutine {
		t.Fatalf("ListNotes returned %d notes, want %d", len(notes), goroutines*perGoroutine)
	}

	// 每个用户的 reviews 行应各回填一条，共 goroutines*perGoroutine 条。
	var reviewCount int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM reviews`).Scan(&reviewCount); err != nil {
		t.Fatalf("count reviews failed: %v", err)
	}
	if reviewCount != goroutines*perGoroutine {
		t.Fatalf("reviews count = %d, want %d", reviewCount, goroutines*perGoroutine)
	}
}

var _ = context.Background
