package store

import (
	"database/sql"
	"testing"
)

func TestLinkBlockRef_NotResolved_Documented(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "标题", Body: "B"})
	if err != nil {
		t.Fatalf("CreateNote B failed: %v", err)
	}
	_ = b

	a, err := st.CreateNote(Note{Title: "A", Body: "见 [[标题#^块id]] 处"})
	if err != nil {
		t.Fatalf("CreateNote A failed: %v", err)
	}

	var (
		targetTitle string
		targetID    sql.NullInt64
	)
	err = st.db.QueryRow(
		`SELECT target_title, target_id FROM links WHERE source_id=?`,
		a.ID,
	).Scan(&targetTitle, &targetID)
	if err != nil {
		t.Fatalf("query links for source_id=%d failed: %v", a.ID, err)
	}
	if targetTitle != "标题#^块id" {
		t.Fatalf("target_title = %q, want %q", targetTitle, "标题#^块id")
	}
	if targetID.Valid {
		t.Fatalf("target_id should be NULL for block ref, got Valid=true Int64=%d", targetID.Int64)
	}

	rowCount := 0
	rows, err := st.db.Query(`SELECT 1 FROM links WHERE source_id=?`, a.ID)
	if err != nil {
		t.Fatalf("count links for source_id=%d failed: %v", a.ID, err)
	}
	for rows.Next() {
		rowCount++
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		t.Fatalf("iterate links failed: %v", err)
	}
	rows.Close()
	if rowCount != 1 {
		t.Fatalf("links rows for source_id=%d = %d, want 1", a.ID, rowCount)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph failed: %v", err)
	}
	if len(gd.Edges) != 0 {
		t.Fatalf("Graph().Edges length = %d, want 0; edges=%+v", len(gd.Edges), gd.Edges)
	}
}

func TestLinkEmptyBrackets_Skipped(t *testing.T) {
	st := newTestStore(t)

	a, err := st.CreateNote(Note{Title: "A", Body: "空链接 [[ ]] 和 [[  ]] 应该被忽略"})
	if err != nil {
		t.Fatalf("CreateNote A failed: %v", err)
	}

	rowCount := 0
	rows, err := st.db.Query(`SELECT 1 FROM links WHERE source_id=?`, a.ID)
	if err != nil {
		t.Fatalf("count links for source_id=%d failed: %v", a.ID, err)
	}
	for rows.Next() {
		rowCount++
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		t.Fatalf("iterate links failed: %v", err)
	}
	rows.Close()
	if rowCount != 0 {
		t.Fatalf("links rows for source_id=%d = %d, want 0 (empty brackets should be skipped)", a.ID, rowCount)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph failed: %v", err)
	}
	if len(gd.Edges) != 0 {
		t.Fatalf("Graph().Edges length = %d, want 0; edges=%+v", len(gd.Edges), gd.Edges)
	}
}