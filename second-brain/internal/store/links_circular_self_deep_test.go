package store

import (
	"testing"
)

func TestCircularLinks_BothDirections(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "B", Body: "回链 [[A]]"})
	if err != nil {
		t.Fatalf("CreateNote(B) failed: %v", err)
	}
	if b.ID == 0 {
		t.Fatalf("expected non-zero B.ID, got %d", b.ID)
	}

	a, err := st.CreateNote(Note{Title: "A", Body: "前链 [[B]]"})
	if err != nil {
		t.Fatalf("CreateNote(A) failed: %v", err)
	}
	if a.ID == 0 {
		t.Fatalf("expected non-zero A.ID, got %d", a.ID)
	}
	if a.ID == b.ID {
		t.Fatalf("expected distinct note IDs, both are %d", a.ID)
	}

	blA, err := st.Backlinks(a.ID)
	if err != nil {
		t.Fatalf("Backlinks(a.ID=%d) failed: %v", a.ID, err)
	}
	if len(blA) != 1 {
		t.Fatalf("expected len(Backlinks(a.ID)) == 1, got %d (%+v)", len(blA), blA)
	}
	if blA[0].ID != b.ID {
		t.Errorf("expected blA[0].ID == %d, got %d", b.ID, blA[0].ID)
	}
	if blA[0].Title != "B" {
		t.Errorf("expected blA[0].Title == %q, got %q", "B", blA[0].Title)
	}

	blB, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(b.ID=%d) failed: %v", b.ID, err)
	}
	if len(blB) != 1 {
		t.Fatalf("expected len(Backlinks(b.ID)) == 1, got %d (%+v)", len(blB), blB)
	}
	if blB[0].ID != a.ID {
		t.Errorf("expected blB[0].ID == %d, got %d", a.ID, blB[0].ID)
	}
	if blB[0].Title != "A" {
		t.Errorf("expected blB[0].Title == %q, got %q", "A", blB[0].Title)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph() failed: %v", err)
	}

	hasAToB := false
	hasBToA := false
	for _, e := range gd.Edges {
		if e.Source == a.ID && e.Target == b.ID {
			hasAToB = true
		}
		if e.Source == b.ID && e.Target == a.ID {
			hasBToA = true
		}
	}
	if !hasAToB {
		t.Errorf("expected Graph edge {Source:%d, Target:%d}, got edges %+v", a.ID, b.ID, gd.Edges)
	}
	if !hasBToA {
		t.Errorf("expected Graph edge {Source:%d, Target:%d}, got edges %+v", b.ID, a.ID, gd.Edges)
	}
}

func TestSelfLink_BacklinkKept_GraphSkips(t *testing.T) {
	st := newTestStore(t)

	s, err := st.CreateNote(Note{Title: "S", Body: "自指 [[S]]"})
	if err != nil {
		t.Fatalf("CreateNote(S) failed: %v", err)
	}
	if s.ID == 0 {
		t.Fatalf("expected non-zero S.ID, got %d", s.ID)
	}

	bl, err := st.Backlinks(s.ID)
	if err != nil {
		t.Fatalf("Backlinks(s.ID=%d) failed: %v", s.ID, err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected len(Backlinks(s.ID)) == 1 (self-link kept), got %d (%+v)", len(bl), bl)
	}
	if bl[0].ID != s.ID {
		t.Errorf("expected bl[0].ID == %d, got %d", s.ID, bl[0].ID)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph() failed: %v", err)
	}

	for _, e := range gd.Edges {
		if e.Source == s.ID && e.Target == s.ID {
			t.Errorf("expected Graph to skip self-edge {Source:%d, Target:%d}, but it was present in edges %+v", s.ID, s.ID, gd.Edges)
		}
	}
}