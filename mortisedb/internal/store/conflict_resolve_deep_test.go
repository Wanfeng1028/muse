package store

import (
	"database/sql"
	"fmt"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
)

func newConflictTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "conflict_deep_test.db")
	s, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open(%q) failed: %v", dbPath, err)
	}
	if err := s.Migrate(); err != nil {
		t.Fatalf("Migrate failed: %v", err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Logf("Close failed: %v", err)
		}
	})
	return s
}

func mustRecordConflict(t *testing.T, s *Store, c Conflict) int64 {
	t.Helper()
	id, err := s.RecordConflict(s.DB, c)
	if err != nil {
		t.Fatalf("RecordConflict failed: %v", err)
	}
	return id
}

func TestRecordConflictThenListFieldsExact(t *testing.T) {
	s := newConflictTestStore(t)

	rowJSON := `{"name":"晚风","note":"中文与特殊字符 <>\"'&\\ / \n\t","emoji_like":"☂"}`
	c := Conflict{
		TableName: "users",
		PK:        "42",
		SourceA:   "node-a",
		SourceB:   "node-b",
		RowJSON:   rowJSON,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}
	id := mustRecordConflict(t, s, c)
	if id <= 0 {
		t.Fatalf("RecordConflict returned non-positive id: %d", id)
	}

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("ListConflicts(pending) length = %d, want 1", len(list))
	}
	got := list[0]
	if got.ID != id {
		t.Errorf("ID = %d, want %d", got.ID, id)
	}
	if got.TableName != "users" {
		t.Errorf("TableName = %q, want %q", got.TableName, "users")
	}
	if got.PK != "42" {
		t.Errorf("PK = %q, want %q", got.PK, "42")
	}
	if got.SourceA != "node-a" {
		t.Errorf("SourceA = %q, want %q", got.SourceA, "node-a")
	}
	if got.SourceB != "node-b" {
		t.Errorf("SourceB = %q, want %q", got.SourceB, "node-b")
	}
	if got.RowJSON != rowJSON {
		t.Errorf("RowJSON = %q, want %q", got.RowJSON, rowJSON)
	}
	if got.Status != "pending" {
		t.Errorf("Status = %q, want %q", got.Status, "pending")
	}
	if got.CreatedAt == "" {
		t.Errorf("CreatedAt is zero, want non-zero")
	}
	if got.ResolvedAt != "" {
		t.Errorf("ResolvedAt = %q, want empty for pending conflict", got.ResolvedAt)
	}
}

func TestListConflictsFilterByStatus(t *testing.T) {
	s := newConflictTestStore(t)

	pendingID := mustRecordConflict(t, s, Conflict{
		TableName: "t1", PK: "1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v1"}`, Status: "pending",
	})
	resolvedID := mustRecordConflict(t, s, Conflict{
		TableName: "t2", PK: "2", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v2"}`, Status: "pending",
	})
	if err := s.ResolveConflict(resolvedID, "resolved"); err != nil {
		t.Fatalf("ResolveConflict(%d, resolved) failed: %v", resolvedID, err)
	}

	pending, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("ListConflicts(pending) length = %d, want 1", len(pending))
	}
	if pending[0].ID != pendingID {
		t.Errorf("pending[0].ID = %d, want %d", pending[0].ID, pendingID)
	}
	if pending[0].Status != "pending" {
		t.Errorf("pending[0].Status = %q, want %q", pending[0].Status, "pending")
	}

	resolved, err := s.ListConflicts("resolved")
	if err != nil {
		t.Fatalf("ListConflicts(resolved) failed: %v", err)
	}
	if len(resolved) != 1 {
		t.Fatalf("ListConflicts(resolved) length = %d, want 1", len(resolved))
	}
	if resolved[0].ID != resolvedID {
		t.Errorf("resolved[0].ID = %d, want %d", resolved[0].ID, resolvedID)
	}
	if resolved[0].Status != "resolved" {
		t.Errorf("resolved[0].Status = %q, want %q", resolved[0].Status, "resolved")
	}

	all, err := s.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts(\"\") failed: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("ListConflicts(\"\") length = %d, want 2", len(all))
	}
	if all[0].ID != resolvedID || all[1].ID != pendingID {
		t.Errorf("ListConflicts(\"\") order = [%d, %d], want [%d, %d]",
			all[0].ID, all[1].ID, resolvedID, pendingID)
	}
}

func TestListConflictsOrderByIDDesc(t *testing.T) {
	s := newConflictTestStore(t)

	var ids []int64
	for i := 0; i < 5; i++ {
		id := mustRecordConflict(t, s, Conflict{
			TableName: "t", PK: fmt.Sprintf("%d", i), SourceA: "a", SourceB: "b",
			RowJSON: fmt.Sprintf(`{"i":%d}`, i), Status: "pending",
		})
		ids = append(ids, id)
	}

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != 5 {
		t.Fatalf("ListConflicts(pending) length = %d, want 5", len(list))
	}
	for i := 0; i < 5; i++ {
		want := ids[4-i]
		if list[i].ID != want {
			t.Errorf("list[%d].ID = %d, want %d (id DESC)", i, list[i].ID, want)
		}
	}
	if list[0].ID <= list[4].ID {
		t.Errorf("first ID %d not greater than last ID %d", list[0].ID, list[4].ID)
	}
}

func TestResolveConflictSetsResolvedAtAndStatus(t *testing.T) {
	s := newConflictTestStore(t)

	id := mustRecordConflict(t, s, Conflict{
		TableName: "t", PK: "1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v"}`, Status: "pending",
	})

	before, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) before resolve failed: %v", err)
	}
	if len(before) != 1 {
		t.Fatalf("before resolve length = %d, want 1", len(before))
	}
	if before[0].ResolvedAt != "" {
		t.Fatalf("before resolve ResolvedAt.Valid = true, want false")
	}

	if err := s.ResolveConflict(id, "resolved"); err != nil {
		t.Fatalf("ResolveConflict failed: %v", err)
	}

	pendingAfter, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) after resolve failed: %v", err)
	}
	if len(pendingAfter) != 0 {
		t.Fatalf("pending after resolve length = %d, want 0", len(pendingAfter))
	}

	resolvedAfter, err := s.ListConflicts("resolved")
	if err != nil {
		t.Fatalf("ListConflicts(resolved) after resolve failed: %v", err)
	}
	if len(resolvedAfter) != 1 {
		t.Fatalf("resolved after resolve length = %d, want 1", len(resolvedAfter))
	}
	got := resolvedAfter[0]
	if got.ID != id {
		t.Errorf("ID = %d, want %d", got.ID, id)
	}
	if got.Status != "resolved" {
		t.Errorf("Status = %q, want %q", got.Status, "resolved")
	}
	if got.ResolvedAt == "" {
		t.Errorf("ResolvedAt.Valid = false, want true")
	}
	if got.ResolvedAt == "" {
		t.Errorf("ResolvedAt.Time is zero, want non-zero")
	}
}

func TestResolveConflictNonexistentID(t *testing.T) {
	s := newConflictTestStore(t)

	const missingID int64 = 999999

	err := s.ResolveConflict(missingID, "resolved")
	if err == nil {
		t.Fatalf("ResolveConflict(missing id) returned nil, want not found error")
	}

	list, err := s.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts(\"\") failed: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("ListConflicts(\"\") length = %d, want 0 after resolving missing id", len(list))
	}

	if err := s.ResolveConflict(missingID, "resolved"); err == nil {
		t.Fatalf("second ResolveConflict(missing id) returned nil, want not found error")
	}
}

func TestResolveConflictAlreadyResolved(t *testing.T) {
	s := newConflictTestStore(t)

	id := mustRecordConflict(t, s, Conflict{
		TableName: "t", PK: "1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v"}`, Status: "pending",
	})

	if err := s.ResolveConflict(id, "resolved"); err != nil {
		t.Fatalf("first ResolveConflict failed: %v", err)
	}
	first, err := s.ListConflicts("resolved")
	if err != nil {
		t.Fatalf("ListConflicts(resolved) failed: %v", err)
	}
	if len(first) != 1 {
		t.Fatalf("resolved length = %d, want 1", len(first))
	}
	firstResolvedAt := first[0].ResolvedAt

	time.Sleep(5 * time.Millisecond)

	if err := s.ResolveConflict(id, "resolved"); err != nil {
		t.Fatalf("second ResolveConflict failed: %v", err)
	}
	second, err := s.ListConflicts("resolved")
	if err != nil {
		t.Fatalf("ListConflicts(resolved) second failed: %v", err)
	}
	if len(second) != 1 {
		t.Fatalf("resolved length after second = %d, want 1", len(second))
	}
	if second[0].ID != id {
		t.Errorf("ID = %d, want %d", second[0].ID, id)
	}
	if second[0].Status != "resolved" {
		t.Errorf("Status = %q, want %q", second[0].Status, "resolved")
	}
	if second[0].ResolvedAt == "" {
		t.Errorf("ResolvedAt.Valid = false, want true")
	}
	if firstResolvedAt != "" && second[0].ResolvedAt < firstResolvedAt {
		t.Errorf("ResolvedAt went backwards: first=%v second=%v",
			firstResolvedAt, second[0].ResolvedAt)
	}
}

func counterValue() float64 {
	for _, line := range strings.Split(metrics.Default().Render(), "\n") {
		if strings.HasPrefix(line, "mortise_conflicts_total ") {
			var v float64
			fmt.Sscanf(strings.TrimPrefix(line, "mortise_conflicts_total "), "%f", &v)
			return v
		}
	}
	return -1
}

func TestRecordConflictMetricsCounterIncrements(t *testing.T) {
	metrics.Default().RegisterStandard()
	s := newConflictTestStore(t)

	before := counterValue()

	for i := 0; i < 3; i++ {
		mustRecordConflict(t, s, Conflict{
			TableName: "t", PK: fmt.Sprintf("%d", i), SourceA: "a", SourceB: "b",
			RowJSON: fmt.Sprintf(`{"i":%d}`, i), Status: "pending",
		})
	}

	after := counterValue()
	if after-before < 3 {
		t.Errorf("counter delta = %v, want >= 3", after-before)
	}
	if after <= before {
		t.Errorf("counter after = %v, want > before = %v", after, before)
	}
}

func TestRecordConflictConcurrentNoBusy(t *testing.T) {
	s := newConflictTestStore(t)

	const workers = 20
	var wg sync.WaitGroup
	wg.Add(workers)
	errCh := make(chan error, workers)
	ids := make([]int64, workers)
	var mu sync.Mutex

	start := make(chan struct{})
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			id, err := s.RecordConflict(s.DB, Conflict{
				TableName: "t",
				PK:        fmt.Sprintf("pk-%d", idx),
				SourceA:   fmt.Sprintf("a-%d", idx),
				SourceB:   fmt.Sprintf("b-%d", idx),
				RowJSON:   fmt.Sprintf(`{"idx":%d}`, idx),
				Status:    "pending",
			})
			if err != nil {
				errCh <- fmt.Errorf("worker %d: %w", idx, err)
				return
			}
			mu.Lock()
			ids[idx] = id
			mu.Unlock()
		}(i)
	}
	close(start)
	wg.Wait()
	close(errCh)

	for err := range errCh {
		if err == nil {
			continue
		}
		msg := err.Error()
		if strings.Contains(msg, "SQLITE_BUSY") || strings.Contains(msg, "database is locked") {
			t.Fatalf("got SQLITE_BUSY/locked error despite v1.4.1 busy_timeout fix: %v", err)
		}
		t.Fatalf("RecordConflict concurrent error: %v", err)
	}

	seen := make(map[int64]bool, workers)
	for i, id := range ids {
		if id <= 0 {
			t.Fatalf("worker %d produced non-positive id %d", i, id)
		}
		if seen[id] {
			t.Fatalf("duplicate id %d produced by concurrent workers", id)
		}
		seen[id] = true
	}

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != workers {
		t.Fatalf("ListConflicts(pending) length = %d, want %d", len(list), workers)
	}
}

func TestRecordConflictLargeRowJSONRoundTrip(t *testing.T) {
	s := newConflictTestStore(t)

	chunk := strings.Repeat("A", 1024)
	var sb strings.Builder
	for sb.Len() < 100*1024 {
		sb.WriteString(chunk)
	}
	large := sb.String()
	if len(large) < 100*1024 {
		t.Fatalf("large payload too small: %d bytes, want >= 102400", len(large))
	}

	id := mustRecordConflict(t, s, Conflict{
		TableName: "big", PK: "big-1", SourceA: "a", SourceB: "b",
		RowJSON: large, Status: "pending",
	})

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("ListConflicts(pending) length = %d, want 1", len(list))
	}
	got := list[0]
	if got.ID != id {
		t.Errorf("ID = %d, want %d", got.ID, id)
	}
	if len(got.RowJSON) != len(large) {
		t.Fatalf("RowJSON length = %d, want %d", len(got.RowJSON), len(large))
	}
	if got.RowJSON != large {
		t.Errorf("RowJSON content mismatch after large round trip")
	}
}

func TestRecordConflictLargeRowJSONWithUnicode(t *testing.T) {
	s := newConflictTestStore(t)

	unit := "中文晚风☂<>&\"'\\"
	var sb strings.Builder
	for sb.Len() < 100*1024 {
		sb.WriteString(unit)
	}
	payload := sb.String()

	id := mustRecordConflict(t, s, Conflict{
		TableName: "big", PK: "big-2", SourceA: "a", SourceB: "b",
		RowJSON: payload, Status: "pending",
	})

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("ListConflicts(pending) length = %d, want 1", len(list))
	}
	if list[0].ID != id {
		t.Errorf("ID = %d, want %d", list[0].ID, id)
	}
	if list[0].RowJSON != payload {
		t.Errorf("unicode large RowJSON content mismatch")
	}
	if len(list[0].RowJSON) != len(payload) {
		t.Errorf("unicode large RowJSON length = %d, want %d", len(list[0].RowJSON), len(payload))
	}
}

func TestListConflictsEmptyDatabase(t *testing.T) {
	s := newConflictTestStore(t)

	all, err := s.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts(\"\") failed: %v", err)
	}
	if len(all) != 0 {
		t.Fatalf("ListConflicts(\"\") length = %d, want 0", len(all))
	}

	pending, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("ListConflicts(pending) length = %d, want 0", len(pending))
	}
}

func TestListConflictsUnknownStatusReturnsEmpty(t *testing.T) {
	s := newConflictTestStore(t)

	mustRecordConflict(t, s, Conflict{
		TableName: "t", PK: "1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v"}`, Status: "pending",
	})

	got, err := s.ListConflicts("no_such_status")
	if err != nil {
		t.Fatalf("ListConflicts(no_such_status) failed: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("ListConflicts(no_such_status) length = %d, want 0", len(got))
	}

	all, err := s.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts(\"\") failed: %v", err)
	}
	if len(all) != 1 {
		t.Fatalf("ListConflicts(\"\") length = %d, want 1", len(all))
	}
}

func TestResolveConflictIsolatesOtherRows(t *testing.T) {
	s := newConflictTestStore(t)

	keepID := mustRecordConflict(t, s, Conflict{
		TableName: "keep", PK: "k1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"keep"}`, Status: "pending",
	})
	resolveID := mustRecordConflict(t, s, Conflict{
		TableName: "resolve", PK: "r1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"resolve"}`, Status: "pending",
	})

	if err := s.ResolveConflict(resolveID, "resolved"); err != nil {
		t.Fatalf("ResolveConflict failed: %v", err)
	}

	pending, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("pending length = %d, want 1", len(pending))
	}
	if pending[0].ID != keepID {
		t.Errorf("pending[0].ID = %d, want %d", pending[0].ID, keepID)
	}
	if pending[0].Status != "pending" {
		t.Errorf("pending[0].Status = %q, want %q", pending[0].Status, "pending")
	}
	if pending[0].ResolvedAt != "" {
		t.Errorf("keep row ResolvedAt.Valid = true, want false")
	}

	resolved, err := s.ListConflicts("resolved")
	if err != nil {
		t.Fatalf("ListConflicts(resolved) failed: %v", err)
	}
	if len(resolved) != 1 {
		t.Fatalf("resolved length = %d, want 1", len(resolved))
	}
	if resolved[0].ID != resolveID {
		t.Errorf("resolved[0].ID = %d, want %d", resolved[0].ID, resolveID)
	}
}

func TestRecordConflictSeparateStoresIsolated(t *testing.T) {
	s1 := newConflictTestStore(t)
	s2 := newConflictTestStore(t)

	mustRecordConflict(t, s1, Conflict{
		TableName: "t1", PK: "1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v1"}`, Status: "pending",
	})
	mustRecordConflict(t, s2, Conflict{
		TableName: "t2", PK: "2", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v2"}`, Status: "pending",
	})

	l1, err := s1.ListConflicts("")
	if err != nil {
		t.Fatalf("s1.ListConflicts failed: %v", err)
	}
	if len(l1) != 1 {
		t.Fatalf("s1 length = %d, want 1", len(l1))
	}
	if l1[0].TableName != "t1" {
		t.Errorf("s1[0].TableName = %q, want %q", l1[0].TableName, "t1")
	}

	l2, err := s2.ListConflicts("")
	if err != nil {
		t.Fatalf("s2.ListConflicts failed: %v", err)
	}
	if len(l2) != 1 {
		t.Fatalf("s2 length = %d, want 1", len(l2))
	}
	if l2[0].TableName != "t2" {
		t.Errorf("s2[0].TableName = %q, want %q", l2[0].TableName, "t2")
	}
}

func TestRecordConflictNullByteAndControlChars(t *testing.T) {
	s := newConflictTestStore(t)

	payload := "line1\nline2\ttab\rreturn\x00nullbyte"
	id := mustRecordConflict(t, s, Conflict{
		TableName: "ctrl", PK: "c1", SourceA: "a", SourceB: "b",
		RowJSON: payload, Status: "pending",
	})

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("length = %d, want 1", len(list))
	}
	if list[0].ID != id {
		t.Errorf("ID = %d, want %d", list[0].ID, id)
	}
	if list[0].RowJSON != payload {
		t.Errorf("RowJSON = %q, want %q", list[0].RowJSON, payload)
	}
	if len(list[0].RowJSON) != len(payload) {
		t.Errorf("RowJSON byte length = %d, want %d", len(list[0].RowJSON), len(payload))
	}
}

func TestRecordConflictCreatedAtMonotonic(t *testing.T) {
	s := newConflictTestStore(t)

	first := mustRecordConflict(t, s, Conflict{
		TableName: "t", PK: "1", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v1"}`, Status: "pending",
	})
	time.Sleep(2 * time.Millisecond)
	second := mustRecordConflict(t, s, Conflict{
		TableName: "t", PK: "2", SourceA: "a", SourceB: "b",
		RowJSON: `{"k":"v2"}`, Status: "pending",
	})

	list, err := s.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts(pending) failed: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("length = %d, want 2", len(list))
	}
	if list[0].ID != second || list[1].ID != first {
		t.Fatalf("order = [%d, %d], want [%d, %d]", list[0].ID, list[1].ID, second, first)
	}
	if list[0].CreatedAt < list[1].CreatedAt {
		t.Errorf("CreatedAt not monotonic: first=%v second=%v", list[1].CreatedAt, list[0].CreatedAt)
	}
}

var _ = sql.ErrNoRows