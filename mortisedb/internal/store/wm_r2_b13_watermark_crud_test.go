package store

import "testing"

func TestWmR2B13SetGetOverwrite(t *testing.T) {
	dir := t.TempDir()
	s, err := Open(dir + "/wm_r2_b13_crud.db")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()
	if err := s.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	if err := s.SetWatermark("s1", "t", "c", "v1"); err != nil {
		t.Fatalf("SetWatermark v1: %v", err)
	}
	got, err := s.GetWatermark("s1", "t", "c")
	if err != nil {
		t.Fatalf("GetWatermark v1: %v", err)
	}
	if got != "v1" {
		t.Fatalf("GetWatermark v1 = %q, want %q", got, "v1")
	}

	if err := s.SetWatermark("s1", "t", "c", "v2"); err != nil {
		t.Fatalf("SetWatermark v2: %v", err)
	}
	got, err = s.GetWatermark("s1", "t", "c")
	if err != nil {
		t.Fatalf("GetWatermark v2: %v", err)
	}
	if got != "v2" {
		t.Fatalf("GetWatermark after overwrite = %q, want %q", got, "v2")
	}

	missing, err := s.GetWatermark("s1", "nope", "c")
	if err != nil {
		t.Fatalf("GetWatermark missing: %v", err)
	}
	if missing != "" {
		t.Fatalf("GetWatermark missing = %q, want empty", missing)
	}
}

func TestWmR2B13ListOrdering(t *testing.T) {
	dir := t.TempDir()
	s, err := Open(dir + "/wm_r2_b13_list.db")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()
	if err := s.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	seed := []Watermark{
		{Source: "b", Table: "t", Column: "c", Value: "1"},
		{Source: "a", Table: "t2", Column: "c", Value: "2"},
		{Source: "a", Table: "t1", Column: "c", Value: "3"},
		{Source: "a", Table: "t1", Column: "b", Value: "4"},
	}
	for _, w := range seed {
		if err := s.SetWatermark(w.Source, w.Table, w.Column, w.Value); err != nil {
			t.Fatalf("SetWatermark %+v: %v", w, err)
		}
	}

	list, err := s.ListWatermarks()
	if err != nil {
		t.Fatalf("ListWatermarks: %v", err)
	}
	if len(list) != 4 {
		t.Fatalf("ListWatermarks len = %d, want 4 (%+v)", len(list), list)
	}
	want := []Watermark{
		{Source: "a", Table: "t1", Column: "b", Value: "4"},
		{Source: "a", Table: "t1", Column: "c", Value: "3"},
		{Source: "a", Table: "t2", Column: "c", Value: "2"},
		{Source: "b", Table: "t", Column: "c", Value: "1"},
	}
	for i := range want {
		if list[i] != want[i] {
			t.Fatalf("ListWatermarks[%d] = %+v, want %+v", i, list[i], want[i])
		}
	}
}

func TestWmR2B13DeleteIdempotent(t *testing.T) {
	dir := t.TempDir()
	s, err := Open(dir + "/wm_r2_b13_delete.db")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()
	if err := s.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	if err := s.SetWatermark("s1", "t", "c", "v"); err != nil {
		t.Fatalf("SetWatermark: %v", err)
	}
	got, err := s.GetWatermark("s1", "t", "c")
	if err != nil {
		t.Fatalf("GetWatermark before delete: %v", err)
	}
	if got != "v" {
		t.Fatalf("GetWatermark before delete = %q, want %q", got, "v")
	}

	if err := s.DeleteWatermark("s1", "t", "c"); err != nil {
		t.Fatalf("DeleteWatermark: %v", err)
	}
	got, err = s.GetWatermark("s1", "t", "c")
	if err != nil {
		t.Fatalf("GetWatermark after delete: %v", err)
	}
	if got != "" {
		t.Fatalf("GetWatermark after delete = %q, want empty", got)
	}

	if err := s.DeleteWatermark("s1", "t", "c"); err != nil {
		t.Fatalf("DeleteWatermark second (idempotent): %v", err)
	}
	if err := s.DeleteWatermark("s1", "missing", "c"); err != nil {
		t.Fatalf("DeleteWatermark nonexistent: %v", err)
	}

	list, err := s.ListWatermarks()
	if err != nil {
		t.Fatalf("ListWatermarks: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("ListWatermarks len = %d, want 0 (%+v)", len(list), list)
	}
}
