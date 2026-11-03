package store

import (
	"errors"
	"reflect"
	"testing"
)

func newTestStore(t *testing.T) *Store {
	t.Helper()
	st, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open(:memory:) failed: %v", err)
	}
	t.Cleanup(func() {
		if err := st.Close(); err != nil {
			t.Errorf("Close failed: %v", err)
		}
	})
	return st
}

func TestCreateAndGetNote(t *testing.T) {
	st := newTestStore(t)

	created, err := st.CreateNote(Note{
		Title: "First Note",
		Body:  "Hello world. See [[Second Note]] and [[Third Note]].",
		Tags:  []string{"  Go ", "go", "TEST", ""},
	})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if created.ID == 0 {
		t.Fatalf("expected non-zero ID")
	}
	if created.Title != "First Note" {
		t.Errorf("unexpected title: %q", created.Title)
	}
	if created.CreatedAt == "" || created.UpdatedAt == "" {
		t.Errorf("expected timestamps set, got created=%q updated=%q", created.CreatedAt, created.UpdatedAt)
	}

	wantTags := []string{"go", "test"}
	if !reflect.DeepEqual(created.Tags, wantTags) {
		t.Errorf("expected normalized tags %v, got %v", wantTags, created.Tags)
	}

	got, err := st.GetNote(created.ID)
	if err != nil {
		t.Fatalf("GetNote failed: %v", err)
	}
	if got.ID != created.ID {
		t.Errorf("expected ID %d, got %d", created.ID, got.ID)
	}
	if got.Title != created.Title {
		t.Errorf("expected title %q, got %q", created.Title, got.Title)
	}
	if got.Body != created.Body {
		t.Errorf("expected body %q, got %q", created.Body, got.Body)
	}
	if !reflect.DeepEqual(got.Tags, wantTags) {
		t.Errorf("expected tags %v, got %v", wantTags, got.Tags)
	}
	if got.CreatedAt != created.CreatedAt {
		t.Errorf("expected createdAt %q, got %q", created.CreatedAt, got.CreatedAt)
	}

	var linkCount int
	if err := st.db.QueryRow("SELECT COUNT(*) FROM links WHERE source_id = ?", created.ID).Scan(&linkCount); err != nil {
		t.Fatalf("querying links failed: %v", err)
	}
	if linkCount != 2 {
		t.Errorf("expected 2 links, got %d", linkCount)
	}
}

func TestGetNoteNotFound(t *testing.T) {
	st := newTestStore(t)
	_, err := st.GetNote(99999)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestListNotesTagFilterAndPinnedOrder(t *testing.T) {
	st := newTestStore(t)

	n1, err := st.CreateNote(Note{Title: "Alpha", Body: "one", Tags: []string{"x"}})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	n2, err := st.CreateNote(Note{Title: "Beta", Body: "two", Tags: []string{"y"}})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	n3, err := st.CreateNote(Note{Title: "Gamma", Body: "three", Tags: []string{"x"}, Pinned: true})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	all, err := st.ListNotes("", 100, 0)
	if err != nil {
		t.Fatalf("ListNotes failed: %v", err)
	}
	if len(all) != 3 {
		t.Fatalf("expected 3 notes, got %d", len(all))
	}
	if all[0].ID != n3.ID {
		t.Errorf("expected pinned note first, got ID %d", all[0].ID)
	}

	tagged, err := st.ListNotes("x", 100, 0)
	if err != nil {
		t.Fatalf("ListNotes tag filter failed: %v", err)
	}
	if len(tagged) != 2 {
		t.Fatalf("expected 2 tagged notes, got %d", len(tagged))
	}
	if tagged[0].ID != n3.ID {
		t.Errorf("expected pinned note first in filtered list, got ID %d", tagged[0].ID)
	}
	foundN1 := false
	for _, n := range tagged {
		if n.ID == n1.ID {
			foundN1 = true
		}
		if n.ID == n2.ID {
			t.Errorf("did not expect note %d in tag filter result", n2.ID)
		}
	}
	if !foundN1 {
		t.Errorf("expected note %d in tag filter result", n1.ID)
	}

	limited, err := st.ListNotes("", 1, 0)
	if err != nil {
		t.Fatalf("ListNotes limit failed: %v", err)
	}
	if len(limited) != 1 {
		t.Fatalf("expected 1 note with limit, got %d", len(limited))
	}
}

func TestUpdateNote(t *testing.T) {
	st := newTestStore(t)

	created, err := st.CreateNote(Note{Title: "Orig", Body: "body [[Target]]", Tags: []string{"a"}})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	created.Title = "Updated"
	created.Body = "new body"
	created.Tags = []string{"B", "a", "b"}
	created.Pinned = true

	updated, err := st.UpdateNote(created)
	if err != nil {
		t.Fatalf("UpdateNote failed: %v", err)
	}
	if updated.Title != "Updated" {
		t.Errorf("expected title Updated, got %q", updated.Title)
	}
	if !updated.Pinned {
		t.Errorf("expected pinned true")
	}
	wantTags := []string{"a", "b"}
	if !reflect.DeepEqual(updated.Tags, wantTags) {
		t.Errorf("expected tags %v, got %v", wantTags, updated.Tags)
	}

	got, err := st.GetNote(created.ID)
	if err != nil {
		t.Fatalf("GetNote failed: %v", err)
	}
	if got.Title != "Updated" || got.Body != "new body" {
		t.Errorf("update not persisted: %+v", got)
	}
	if !reflect.DeepEqual(got.Tags, wantTags) {
		t.Errorf("expected tags %v, got %v", wantTags, got.Tags)
	}

	var linkCount int
	if err := st.db.QueryRow("SELECT COUNT(*) FROM links WHERE source_id = ?", created.ID).Scan(&linkCount); err != nil {
		t.Fatalf("querying links failed: %v", err)
	}
	if linkCount != 0 {
		t.Errorf("expected links cleared after update, got %d", linkCount)
	}
}

func TestDeleteNote(t *testing.T) {
	st := newTestStore(t)

	created, err := st.CreateNote(Note{Title: "ToDelete", Body: "x", Tags: []string{"t"}})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	if err := st.DeleteNote(created.ID); err != nil {
		t.Fatalf("DeleteNote failed: %v", err)
	}

	_, err = st.GetNote(created.ID)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound after delete, got %v", err)
	}
}

func TestSearchNotesMultiKeyword(t *testing.T) {
	st := newTestStore(t)

	if _, err := st.CreateNote(Note{Title: "Go Concurrency", Body: "goroutines and channels"}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := st.CreateNote(Note{Title: "Go Basics", Body: "syntax and types"}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := st.CreateNote(Note{Title: "Rust", Body: "ownership"}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	res, err := st.SearchNotes("go channels")
	if err != nil {
		t.Fatalf("SearchNotes failed: %v", err)
	}
	if len(res) != 1 {
		t.Fatalf("expected 1 result, got %d", len(res))
	}
	if res[0].Title != "Go Concurrency" {
		t.Errorf("expected 'Go Concurrency', got %q", res[0].Title)
	}

	res, err = st.SearchNotes("go")
	if err != nil {
		t.Fatalf("SearchNotes failed: %v", err)
	}
	if len(res) != 2 {
		t.Fatalf("expected 2 results for 'go', got %d", len(res))
	}

	res, err = st.SearchNotes("nonexistentterm")
	if err != nil {
		t.Fatalf("SearchNotes failed: %v", err)
	}
	if len(res) != 0 {
		t.Fatalf("expected 0 results, got %d", len(res))
	}
}

func TestStats(t *testing.T) {
	st := newTestStore(t)

	if _, err := st.CreateNote(Note{Title: "One", Body: "alpha beta gamma", Tags: []string{"a", "b"}}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := st.CreateNote(Note{Title: "Two", Body: "delta [[One]]", Tags: []string{"b"}}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	stats, err := st.Stats()
	if err != nil {
		t.Fatalf("Stats failed: %v", err)
	}
	if stats.Notes != 2 {
		t.Errorf("expected 2 notes, got %d", stats.Notes)
	}
	if stats.Tags != 2 {
		t.Errorf("expected 2 tags, got %d", stats.Tags)
	}
	if stats.Links != 1 {
		t.Errorf("expected 1 link, got %d", stats.Links)
	}
	if stats.Words <= 0 {
		t.Errorf("expected positive word count, got %d", stats.Words)
	}
}

func TestGraph(t *testing.T) {
	st := newTestStore(t)

	n1, err := st.CreateNote(Note{Title: "Alpha", Body: "links to [[Beta]]", Tags: []string{"x"}})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	n2, err := st.CreateNote(Note{Title: "Beta", Body: "no links", Tags: []string{"y"}})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	graph, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph failed: %v", err)
	}
	if len(graph.Nodes) != 2 {
		t.Fatalf("expected 2 nodes, got %d", len(graph.Nodes))
	}
	if len(graph.Edges) != 1 {
		t.Fatalf("expected 1 edge, got %d", len(graph.Edges))
	}
	edge := graph.Edges[0]
	if edge.Source != n1.ID {
		t.Errorf("expected edge source %d, got %d", n1.ID, edge.Source)
	}
	if edge.Target != n2.ID {
		t.Errorf("expected edge target %d, got %d", n2.ID, edge.Target)
	}

	nodeByID := make(map[int64]GraphNode)
	for _, n := range graph.Nodes {
		nodeByID[n.ID] = n
	}
	if node, ok := nodeByID[n1.ID]; !ok {
		t.Errorf("expected node %d present", n1.ID)
	} else if node.Title != "Alpha" {
		t.Errorf("expected node title Alpha, got %q", node.Title)
	}
}

func TestListTags(t *testing.T) {
	st := newTestStore(t)

	if _, err := st.CreateNote(Note{Title: "A", Tags: []string{"shared", "only1"}}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := st.CreateNote(Note{Title: "B", Tags: []string{"shared"}}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	tags, err := st.ListTags()
	if err != nil {
		t.Fatalf("ListTags failed: %v", err)
	}
	if len(tags) != 2 {
		t.Fatalf("expected 2 tags, got %d", len(tags))
	}
	counts := make(map[string]int)
	for _, tg := range tags {
		counts[tg.Name] = tg.Count
	}
	if counts["shared"] != 2 {
		t.Errorf("expected shared count 2, got %d", counts["shared"])
	}
	if counts["only1"] != 1 {
		t.Errorf("expected only1 count 1, got %d", counts["only1"])
	}
}
