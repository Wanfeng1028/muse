package store

import (
	"database/sql"
	"testing"
)

func TestDuplicateLinks_DedupedToOneRow(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "B", Body: "B 正文"})
	if err != nil {
		t.Fatalf("CreateNote(B) failed: %v", err)
	}
	if b.ID == 0 {
		t.Fatalf("expected B.ID to be non-zero, got %d", b.ID)
	}

	a, err := st.CreateNote(Note{
		Title: "A",
		Body:  "[[B]] 第一次 [[B]] 第二次 [[ B ]] 带空格第三次",
	})
	if err != nil {
		t.Fatalf("CreateNote(A) failed: %v", err)
	}
	if a.ID == 0 {
		t.Fatalf("expected A.ID to be non-zero, got %d", a.ID)
	}

	var count int
	if err := st.db.QueryRow(
		`SELECT COUNT(*) FROM links WHERE source_id=?`, a.ID,
	).Scan(&count); err != nil {
		t.Fatalf("query links count for source_id=%d failed: %v", a.ID, err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 link row for source A after dedup, got %d", count)
	}

	var targetID sql.NullInt64
	if err := st.db.QueryRow(
		`SELECT target_id FROM links WHERE source_id=?`, a.ID,
	).Scan(&targetID); err != nil {
		t.Fatalf("query target_id for source_id=%d failed: %v", a.ID, err)
	}
	if !targetID.Valid {
		t.Fatalf("expected links.target_id to be valid (resolved to B), got NULL")
	}
	if targetID.Int64 != b.ID {
		t.Fatalf("expected links.target_id == b.ID (%d), got %d", b.ID, targetID.Int64)
	}

	bl, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(b.ID=%d) failed: %v", b.ID, err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected exactly 1 backlink for B after dedup, got %d", len(bl))
	}
	if bl[0].ID != a.ID {
		t.Fatalf("expected backlink[0].ID == a.ID (%d), got %d", a.ID, bl[0].ID)
	}
}