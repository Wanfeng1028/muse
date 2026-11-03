package store

import (
	"testing"
)

func TestOrphanNote_NoBacklinksNoEdges(t *testing.T) {
	st := newTestStore(t)

	o, err := st.CreateNote(Note{Title: "孤儿", Body: "没有任何链接的正文"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if o.ID == 0 {
		t.Fatalf("CreateNote returned zero ID for orphan note")
	}

	bl, err := st.Backlinks(o.ID)
	if err != nil {
		t.Fatalf("Backlinks(%d) expected err==nil, got err=%v", o.ID, err)
	}
	if bl == nil {
		t.Fatalf("Backlinks(%d) expected non-nil slice, got nil", o.ID)
	}
	if len(bl) != 0 {
		t.Fatalf("Backlinks(%d) expected len==0 for orphan note, got len=%d (%+v)", o.ID, len(bl), bl)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph() expected err==nil, got err=%v", err)
	}

	found := false
	for _, n := range gd.Nodes {
		if n.ID == o.ID {
			found = true
			if n.Title != "孤儿" {
				t.Errorf("Graph node ID=%d expected Title=%q, got %q", o.ID, "孤儿", n.Title)
			}
			break
		}
	}
	if !found {
		t.Fatalf("Graph() expected Nodes to contain node with ID=%d, got nodes=%+v", o.ID, gd.Nodes)
	}

	for _, e := range gd.Edges {
		if e.Source == o.ID {
			t.Errorf("Graph() expected no edge with Source==%d, got edge=%+v", o.ID, e)
		}
		if e.Target == o.ID {
			t.Errorf("Graph() expected no edge with Target==%d, got edge=%+v", o.ID, e)
		}
	}
}