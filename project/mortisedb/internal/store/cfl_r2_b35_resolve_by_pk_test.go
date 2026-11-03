package store

import (
	"testing"
)

func TestCflR2B35ResolveByPKOnlyPending(t *testing.T) {
	st, err := Open(t.TempDir() + "/cfl_r2_b35_only_pending.db")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	records := []Conflict{
		{TableName: "t1", PK: "p1", SourceA: "a", SourceB: "b", Status: "pending"},
		{TableName: "t1", PK: "p1", Status: "resolved_auto"},
		{TableName: "t1", PK: "p2", Status: "pending"},
		{TableName: "t2", PK: "p1", Status: "pending"},
	}
	ids := make([]int64, 0, len(records))
	for i, c := range records {
		id, err := st.RecordConflict(st.DB, c)
		if err != nil {
			t.Fatalf("RecordConflict[%d]: %v", i, err)
		}
		ids = append(ids, id)
	}

	n, err := st.ResolveConflictsByPK(st.DB, "t1", "p1", "resolved_x")
	if err != nil {
		t.Fatalf("ResolveConflictsByPK: %v", err)
	}
	if n != 1 {
		t.Fatalf("affected rows = %d, want 1", n)
	}

	all, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(all) != 4 {
		t.Fatalf("ListConflicts len = %d, want 4", len(all))
	}

	byID := make(map[int64]Conflict, len(all))
	for _, c := range all {
		byID[c.ID] = c
	}

	first, ok := byID[ids[0]]
	if !ok {
		t.Fatalf("first conflict id %d not found", ids[0])
	}
	if first.Status != "resolved_x" {
		t.Fatalf("first Status = %q, want %q", first.Status, "resolved_x")
	}
	if first.ResolvedAt == "" {
		t.Fatalf("first ResolvedAt is empty, want non-empty")
	}

	for i := 1; i < len(ids); i++ {
		c, ok := byID[ids[i]]
		if !ok {
			t.Fatalf("conflict id %d not found", ids[i])
		}
		if c.Status != records[i].Status {
			t.Fatalf("conflict[%d] Status = %q, want %q", i, c.Status, records[i].Status)
		}
		if c.ResolvedAt != "" {
			t.Fatalf("conflict[%d] ResolvedAt = %q, want empty", i, c.ResolvedAt)
		}
	}
}

func TestCflR2B35ResolveByPKNoMatchZero(t *testing.T) {
	st, err := Open(t.TempDir() + "/cfl_r2_b35_no_match.db")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	id, err := st.RecordConflict(st.DB, Conflict{TableName: "t1", PK: "p1", Status: "resolved_auto"})
	if err != nil {
		t.Fatalf("RecordConflict: %v", err)
	}

	n, err := st.ResolveConflictsByPK(st.DB, "t1", "p1", "resolved_x")
	if err != nil {
		t.Fatalf("ResolveConflictsByPK (non-pending): %v", err)
	}
	if n != 0 {
		t.Fatalf("affected rows = %d, want 0 (no pending)", n)
	}

	all, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(all) != 1 {
		t.Fatalf("ListConflicts len = %d, want 1", len(all))
	}
	if all[0].ID != id {
		t.Fatalf("conflict ID = %d, want %d", all[0].ID, id)
	}
	if all[0].Status != "resolved_auto" {
		t.Fatalf("Status = %q, want %q", all[0].Status, "resolved_auto")
	}
	if all[0].ResolvedAt != "" {
		t.Fatalf("ResolvedAt = %q, want empty", all[0].ResolvedAt)
	}

	n2, err := st.ResolveConflictsByPK(st.DB, "no_such_table", "no_such_pk", "resolved_x")
	if err != nil {
		t.Fatalf("ResolveConflictsByPK (missing): %v", err)
	}
	if n2 != 0 {
		t.Fatalf("affected rows = %d, want 0 (missing table+pk)", n2)
	}

	all2, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts after missing: %v", err)
	}
	if len(all2) != 1 {
		t.Fatalf("ListConflicts len = %d, want 1", len(all2))
	}
	if all2[0].Status != "resolved_auto" {
		t.Fatalf("Status = %q, want %q", all2[0].Status, "resolved_auto")
	}
}
