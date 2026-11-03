package store

import (
	"database/sql"
	"sort"
	"testing"
)

func TestMultipleLinks_UnresolvedSkippedInGraph(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "B", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote B failed: %v", err)
	}
	c, err := st.CreateNote(Note{Title: "C", Body: "c"})
	if err != nil {
		t.Fatalf("CreateNote C failed: %v", err)
	}
	a, err := st.CreateNote(Note{Title: "A", Body: "[[B]] 和 [[C]] 还有 [[不存在的标题]]"})
	if err != nil {
		t.Fatalf("CreateNote A failed: %v", err)
	}

	rows, err := st.db.Query(
		`SELECT target_title, target_id FROM links WHERE source_id=? ORDER BY target_title ASC`,
		a.ID,
	)
	if err != nil {
		t.Fatalf("query links failed: %v", err)
	}
	defer rows.Close()

	type linkRow struct {
		title  string
		target sql.NullInt64
	}
	var got []linkRow
	for rows.Next() {
		var lr linkRow
		if err := rows.Scan(&lr.title, &lr.target); err != nil {
			t.Fatalf("scan link row failed: %v", err)
		}
		got = append(got, lr)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows.Err failed: %v", err)
	}

	if len(got) != 3 {
		t.Fatalf("expected 3 link rows for note A, got %d: %+v", len(got), got)
	}

	// Sort by title explicitly to guarantee order regardless of collation.
	sort.Slice(got, func(i, j int) bool { return got[i].title < got[j].title })

	byTitle := map[string]sql.NullInt64{}
	for _, lr := range got {
		byTitle[lr.title] = lr.target
	}

	if v, ok := byTitle["B"]; !ok {
		t.Fatalf("expected link row with target_title=%q, got rows: %+v", "B", got)
	} else if !v.Valid {
		t.Fatalf("expected target_id for %q to be valid, got NULL", "B")
	} else if v.Int64 != b.ID {
		t.Fatalf("expected target_id for %q to be %d, got %d", "B", b.ID, v.Int64)
	}

	if v, ok := byTitle["C"]; !ok {
		t.Fatalf("expected link row with target_title=%q, got rows: %+v", "C", got)
	} else if !v.Valid {
		t.Fatalf("expected target_id for %q to be valid, got NULL", "C")
	} else if v.Int64 != c.ID {
		t.Fatalf("expected target_id for %q to be %d, got %d", "C", c.ID, v.Int64)
	}

	if v, ok := byTitle["不存在的标题"]; !ok {
		t.Fatalf("expected link row with target_title=%q, got rows: %+v", "不存在的标题", got)
	} else if v.Valid {
		t.Fatalf("expected target_id for %q to be NULL, got valid id %d", "不存在的标题", v.Int64)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph() failed: %v", err)
	}

	edgeSet := map[[2]int64]bool{}
	for _, e := range gd.Edges {
		edgeSet[[2]int64{e.Source, e.Target}] = true
	}

	if len(gd.Edges) != 2 {
		t.Fatalf("expected exactly 2 edges, got %d: %+v", len(gd.Edges), gd.Edges)
	}

	if !edgeSet[[2]int64{a.ID, b.ID}] {
		t.Fatalf("expected edge {Source:%d, Target:%d} in graph, got edges: %+v", a.ID, b.ID, gd.Edges)
	}
	if !edgeSet[[2]int64{a.ID, c.ID}] {
		t.Fatalf("expected edge {Source:%d, Target:%d} in graph, got edges: %+v", a.ID, c.ID, gd.Edges)
	}

	validIDs := map[int64]bool{b.ID: true, c.ID: true, a.ID: true}
	for _, e := range gd.Edges {
		if !validIDs[e.Target] {
			t.Fatalf("edge Target=%d does not correspond to any existing note; unresolved link was not skipped: %+v", e.Target, gd.Edges)
		}
		if e.Source != a.ID {
			t.Fatalf("expected all edges to originate from note A (id=%d), got Source=%d", a.ID, e.Source)
		}
	}
}