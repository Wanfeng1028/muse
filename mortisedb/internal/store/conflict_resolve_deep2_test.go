package store

import (
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"
)

func TestDeep2ResolveConflict_TwiceIsIdempotent(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_twice.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	id, err := st.RecordConflict(st.DB, Conflict{
		TableName: "t1",
		PK:        "1",
		SourceA:   "a",
		SourceB:   "b",
		RowJSON:   `{"x":1}`,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("record: %v", err)
	}

	if err := st.ResolveConflict(id, "resolved"); err != nil {
		t.Fatalf("resolve first: %v", err)
	}
	if err := st.ResolveConflict(id, "resolved"); err != nil {
		t.Fatalf("resolve second: %v", err)
	}

	list, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	count := 0
	var found Conflict
	for _, c := range list {
		if c.ID == id {
			count++
			found = c
		}
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 row with id %d, got %d", id, count)
	}
	if found.Status != "resolved" {
		t.Fatalf("expected status resolved, got %q", found.Status)
	}
	if found.ResolvedAt == "" {
		t.Fatalf("expected non-empty ResolvedAt")
	}
}

func TestDeep2ResolveConflict_StatusChain(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_chain.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	id, err := st.RecordConflict(st.DB, Conflict{
		TableName: "t1",
		PK:        "1",
		SourceA:   "a",
		SourceB:   "b",
		RowJSON:   `{"x":1}`,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("record: %v", err)
	}

	chain := []string{"resolved_auto", "resolved"}
	for _, target := range chain {
		if err := st.ResolveConflict(id, target); err != nil {
			t.Fatalf("resolve to %q: %v", target, err)
		}
		list, err := st.ListConflicts("")
		if err != nil {
			t.Fatalf("list: %v", err)
		}
		var got string
		found := false
		for _, c := range list {
			if c.ID == id {
				got = c.Status
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("id %d not found after resolving to %q", id, target)
		}
		if got != target {
			t.Fatalf("expected status %q, got %q", target, got)
		}
	}
}

func TestDeep2ResolveConflict_NotFoundIDs(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_notfound.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	ids := []int64{0, -1, 999999999}
	for _, id := range ids {
		err := st.ResolveConflict(id, "resolved")
		if !errors.Is(err, ErrNotFound) {
			t.Fatalf("id %d: expected ErrNotFound, got %v", id, err)
		}
	}
}

func TestDeep2ResolveConflict_PreservesCreatedAt(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_createdat.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	createdAt := time.Now().UTC().Format(time.RFC3339)
	id, err := st.RecordConflict(st.DB, Conflict{
		TableName: "t1",
		PK:        "1",
		SourceA:   "a",
		SourceB:   "b",
		RowJSON:   `{"x":1}`,
		Status:    "pending",
		CreatedAt: createdAt,
	})
	if err != nil {
		t.Fatalf("record: %v", err)
	}

	if err := st.ResolveConflict(id, "resolved"); err != nil {
		t.Fatalf("resolve: %v", err)
	}

	list, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	var found Conflict
	ok := false
	for _, c := range list {
		if c.ID == id {
			found = c
			ok = true
			break
		}
	}
	if !ok {
		t.Fatalf("id %d not found", id)
	}
	if found.CreatedAt != createdAt {
		t.Fatalf("CreatedAt changed: expected %q, got %q", createdAt, found.CreatedAt)
	}
	if found.ResolvedAt == "" {
		t.Fatalf("expected non-empty ResolvedAt")
	}
	ct, err := time.Parse(time.RFC3339Nano, found.CreatedAt)
	if err != nil {
		t.Fatalf("parse CreatedAt: %v", err)
	}
	rt, err := time.Parse(time.RFC3339Nano, found.ResolvedAt)
	if err != nil {
		t.Fatalf("parse ResolvedAt: %v", err)
	}
	if rt.Before(ct) {
		t.Fatalf("ResolvedAt %v is before CreatedAt %v", rt, ct)
	}
}

func TestDeep2ResolveByPK_OnlyPendingTouched(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_bypk_only.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	now := time.Now().UTC().Format(time.RFC3339Nano)
	table := "users"
	pk := "42"

	var ids []int64
	for i, status := range []string{"pending", "resolved_auto", "resolved"} {
		id, err := st.RecordConflict(st.DB, Conflict{
			TableName: table,
			PK:        pk,
			SourceA:   fmt.Sprintf("srcA%d", i),
			SourceB:   fmt.Sprintf("srcB%d", i),
			RowJSON:   fmt.Sprintf(`{"i":%d}`, i),
			Status:    status,
			CreatedAt: now,
		})
		if err != nil {
			t.Fatalf("record %d: %v", i, err)
		}
		ids = append(ids, id)
	}

	n, err := st.ResolveConflictsByPK(st.DB, table, pk, "resolved")
	if err != nil {
		t.Fatalf("resolve by pk: %v", err)
	}
	if n != 1 {
		t.Fatalf("expected 1 affected row, got %d", n)
	}

	list, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	statuses := map[int64]string{}
	for _, c := range list {
		statuses[c.ID] = c.Status
	}
	if statuses[ids[0]] != "resolved" {
		t.Fatalf("pending row: expected resolved, got %q", statuses[ids[0]])
	}
	if statuses[ids[1]] != "resolved_auto" {
		t.Fatalf("resolved_auto row changed: got %q", statuses[ids[1]])
	}
	if statuses[ids[2]] != "resolved" {
		t.Fatalf("resolved row changed: got %q", statuses[ids[2]])
	}
}

func TestDeep2ResolveByPK_NoPendingReturnsZero(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_bypk_zero.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	now := time.Now().UTC().Format(time.RFC3339Nano)
	for i := 0; i < 3; i++ {
		if _, err := st.RecordConflict(st.DB, Conflict{
			TableName: "t",
			PK:        "7",
			SourceA:   "a",
			SourceB:   "b",
			RowJSON:   `{}`,
			Status:    "resolved",
			CreatedAt: now,
		}); err != nil {
			t.Fatalf("record %d: %v", i, err)
		}
	}

	n, err := st.ResolveConflictsByPK(st.DB, "t", "7", "resolved")
	if err != nil {
		t.Fatalf("resolve by pk: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 affected rows, got %d", n)
	}
}

func TestDeep2ResolveByPK_IsolatesOtherPKs(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_bypk_isolate.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	now := time.Now().UTC().Format(time.RFC3339Nano)
	idA, err := st.RecordConflict(st.DB, Conflict{
		TableName: "t",
		PK:        "A",
		SourceA:   "a",
		SourceB:   "b",
		RowJSON:   `{}`,
		Status:    "pending",
		CreatedAt: now,
	})
	if err != nil {
		t.Fatalf("record A: %v", err)
	}
	idB, err := st.RecordConflict(st.DB, Conflict{
		TableName: "t",
		PK:        "B",
		SourceA:   "a",
		SourceB:   "b",
		RowJSON:   `{}`,
		Status:    "pending",
		CreatedAt: now,
	})
	if err != nil {
		t.Fatalf("record B: %v", err)
	}

	n, err := st.ResolveConflictsByPK(st.DB, "t", "A", "resolved")
	if err != nil {
		t.Fatalf("resolve by pk: %v", err)
	}
	if n != 1 {
		t.Fatalf("expected 1 affected row, got %d", n)
	}

	list, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	statuses := map[int64]string{}
	for _, c := range list {
		statuses[c.ID] = c.Status
	}
	if statuses[idA] != "resolved" {
		t.Fatalf("pk A expected resolved, got %q", statuses[idA])
	}
	if statuses[idB] != "pending" {
		t.Fatalf("pk B expected pending, got %q", statuses[idB])
	}
}

func TestDeep2RecordConflict_ConcurrentUniqueIDs(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_concurrent_ids.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	const n = 50
	var wg sync.WaitGroup
	errCh := make(chan error, n)
	idCh := make(chan int64, n)

	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			id, err := st.RecordConflict(st.DB, Conflict{
				TableName: "t",
				PK:        fmt.Sprintf("pk-%d", i),
				SourceA:   "a",
				SourceB:   "b",
				RowJSON:   fmt.Sprintf(`{"i":%d}`, i),
				Status:    "pending",
				CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
			})
			if err != nil {
				errCh <- err
				return
			}
			idCh <- id
		}(i)
	}

	wg.Wait()
	close(errCh)
	close(idCh)

	for err := range errCh {
		t.Fatalf("concurrent record error: %v", err)
	}

	seen := map[int64]bool{}
	for id := range idCh {
		if seen[id] {
			t.Fatalf("duplicate id %d", id)
		}
		seen[id] = true
	}
	if len(seen) != n {
		t.Fatalf("expected %d unique ids, got %d", n, len(seen))
	}

	list, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != n {
		t.Fatalf("expected %d rows, got %d", n, len(list))
	}
}

func TestDeep2ResolveConflict_ConcurrentSameID(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_concurrent_same.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	id, err := st.RecordConflict(st.DB, Conflict{
		TableName: "t",
		PK:        "1",
		SourceA:   "a",
		SourceB:   "b",
		RowJSON:   `{}`,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("record: %v", err)
	}

	const n = 20
	var wg sync.WaitGroup
	errCh := make(chan error, n)

	for i := 0; i < n; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := st.ResolveConflict(id, "resolved"); err != nil {
				errCh <- err
			}
		}()
	}

	wg.Wait()
	close(errCh)

	for err := range errCh {
		t.Fatalf("concurrent resolve error: %v", err)
	}

	list, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	count := 0
	var found Conflict
	for _, c := range list {
		if c.ID == id {
			count++
			found = c
		}
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 row with id %d, got %d", id, count)
	}
	if found.Status != "resolved" {
		t.Fatalf("expected resolved, got %q", found.Status)
	}
}

func TestDeep2ListConflicts_StatusFilterExact(t *testing.T) {
	st, err := Open(t.TempDir() + "/deep2_filter_exact.db")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	defer st.DB.Close()

	now := time.Now().UTC().Format(time.RFC3339Nano)
	statuses := []string{"pending", "pending", "resolved_auto", "resolved_auto", "resolved", "resolved"}
	for i, s := range statuses {
		if _, err := st.RecordConflict(st.DB, Conflict{
			TableName: "t",
			PK:        fmt.Sprintf("pk-%d", i),
			SourceA:   "a",
			SourceB:   "b",
			RowJSON:   fmt.Sprintf(`{"i":%d}`, i),
			Status:    s,
			CreatedAt: now,
		}); err != nil {
			t.Fatalf("record %d: %v", i, err)
		}
	}

	pending, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 2 {
		t.Fatalf("expected 2 pending, got %d", len(pending))
	}
	for _, c := range pending {
		if c.Status != "pending" {
			t.Fatalf("expected pending, got %q", c.Status)
		}
	}

	resolved, err := st.ListConflicts("resolved")
	if err != nil {
		t.Fatalf("list resolved: %v", err)
	}
	if len(resolved) != 2 {
		t.Fatalf("expected 2 resolved, got %d", len(resolved))
	}
	for _, c := range resolved {
		if c.Status != "resolved" {
			t.Fatalf("expected resolved, got %q", c.Status)
		}
	}

	all, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list all: %v", err)
	}
	if len(all) != 6 {
		t.Fatalf("expected 6 total, got %d", len(all))
	}
}
