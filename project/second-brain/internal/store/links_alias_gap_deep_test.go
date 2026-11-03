package store

import (
	"database/sql"
	"testing"
)

func TestLinkAliasSyntax_NotResolved_Documented(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "目标", Body: "B 正文"})
	if err != nil {
		t.Fatalf("CreateNote B failed: %v", err)
	}

	a, err := st.CreateNote(Note{Title: "A", Body: "请看 [[目标|别名]] 这一节"})
	if err != nil {
		t.Fatalf("CreateNote A failed: %v", err)
	}

	rows, err := st.db.Query(`SELECT target_title, target_id FROM links WHERE source_id=?`, a.ID)
	if err != nil {
		t.Fatalf("query links for source_id=%d failed: %v", a.ID, err)
	}
	defer rows.Close()

	var (
		count      int
		targetTitle string
		targetID    sql.NullInt64
	)
	for rows.Next() {
		if err := rows.Scan(&targetTitle, &targetID); err != nil {
			t.Fatalf("scan links row failed: %v", err)
		}
		count++
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows iteration error: %v", err)
	}

	if count != 1 {
		t.Fatalf("expected exactly 1 link row for note A, got %d", count)
	}
	if targetTitle != "目标|别名" {
		t.Errorf("expected target_title to be %q (alias syntax stored verbatim), got %q", "目标|别名", targetTitle)
	}
	if targetID.Valid {
		t.Errorf("expected target_id to be NULL (unresolved alias), got valid target_id=%d", targetID.Int64)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph() failed: %v", err)
	}
	if len(gd.Edges) != 0 {
		t.Errorf("expected 0 edges (alias link must not resolve to an edge), got %d edges: %+v", len(gd.Edges), gd.Edges)
	}

	foundA := false
	foundB := false
	for _, n := range gd.Nodes {
		if n.ID == a.ID {
			foundA = true
		}
		if n.ID == b.ID {
			foundB = true
		}
	}
	if !foundA {
		t.Errorf("expected Graph() nodes to contain note A (id=%d), got nodes: %+v", a.ID, gd.Nodes)
	}
	if !foundB {
		t.Errorf("expected Graph() nodes to contain note B (id=%d), got nodes: %+v", b.ID, gd.Nodes)
	}
	if len(gd.Nodes) != 2 {
		t.Errorf("expected exactly 2 graph nodes, got %d: %+v", len(gd.Nodes), gd.Nodes)
	}
}