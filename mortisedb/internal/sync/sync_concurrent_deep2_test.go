package sync

import (
	"fmt"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func deep2ConcurrentMakeSource(t *testing.T, path string, rows [][2]string) {
	t.Helper()
	src, err := store.Open(path)
	if err != nil {
		t.Fatalf("open source %s: %v", path, err)
	}
	if _, err := src.DB.Exec(`CREATE TABLE "users" ("id" TEXT PRIMARY KEY, "name" TEXT)`); err != nil {
		src.Close()
		t.Fatalf("create table: %v", err)
	}
	for _, r := range rows {
		if _, err := src.DB.Exec(`INSERT INTO "users" ("id","name") VALUES (?,?)`, r[0], r[1]); err != nil {
			src.Close()
			t.Fatalf("insert: %v", err)
		}
	}
	if err := src.Close(); err != nil {
		t.Fatalf("close source: %v", err)
	}
}

func deep2ConcurrentCfg(t *testing.T, sources []config.SourceConfig) *config.Config {
	t.Helper()
	return &config.Config{
		Sources: sources,
		Sync: config.SyncPolicy{
			Conflict:   "priority",
			Priority:   []string{},
			SoftDelete: false,
			BatchSize:  50,
		},
	}
}

func deep2ConcurrentNewTarget(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(filepath.Join(t.TempDir(), "t.db"))
	if err != nil {
		t.Fatalf("open target: %v", err)
	}
	if err := st.Migrate(); err != nil {
		st.Close()
		t.Fatalf("migrate: %v", err)
	}
	return st
}

func TestDeep2Concurrent_SameSourceTwice(t *testing.T) {
	dir := t.TempDir()
	srcPath := filepath.Join(dir, "a.db")

	rows := make([][2]string, 0, 20)
	for i := 0; i < 20; i++ {
		rows = append(rows, [2]string{fmt.Sprintf("k%02d", i), fmt.Sprintf("name%02d", i)})
	}
	deep2ConcurrentMakeSource(t, srcPath, rows)

	cfg := deep2ConcurrentCfg(t, []config.SourceConfig{{
		Name: "A",
		Type: "sqlite",
		Path: srcPath,
		Tables: []config.TableMap{{
			Source:     "users",
			Target:     "users",
			PrimaryKey: "id",
		}},
	}})

	st := deep2ConcurrentNewTarget(t)
	defer st.Close()

	const workers = 4
	var wg sync.WaitGroup
	errCh := make(chan error, workers)
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := Sync(cfg, st, []string{"A"}, "j"); err != nil {
				errCh <- err
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("concurrent Sync error: %v", err)
	}

	_, rowsOut, err := st.Query(`SELECT "id","name" FROM "users" ORDER BY "id"`)
	if err != nil {
		t.Fatalf("query users: %v", err)
	}
	if len(rowsOut) != 20 {
		t.Fatalf("expected exactly 20 rows, got %d", len(rowsOut))
	}
	seen := map[string]int{}
	for _, r := range rowsOut {
		seen[fmt.Sprint(r[0])]++
	}
	for id, n := range seen {
		if n != 1 {
			t.Fatalf("duplicate primary key %q count=%d", id, n)
		}
	}
	if len(seen) != 20 {
		t.Fatalf("expected 20 distinct ids, got %d", len(seen))
	}

	conflicts, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list conflicts: %v", err)
	}
	if len(conflicts) != 0 {
		t.Fatalf("expected 0 conflicts for same source, got %d", len(conflicts))
	}
}

func TestDeep2Concurrent_ConflictingSources(t *testing.T) {
	dir := t.TempDir()
	srcA := filepath.Join(dir, "a.db")
	srcB := filepath.Join(dir, "b.db")

	deep2ConcurrentMakeSource(t, srcA, [][2]string{{"1", "alice"}})
	deep2ConcurrentMakeSource(t, srcB, [][2]string{{"1", "bob"}})

	cfg := deep2ConcurrentCfg(t, []config.SourceConfig{
		{
			Name: "A",
			Type: "sqlite",
			Path: srcA,
			Tables: []config.TableMap{{
				Source:     "users",
				Target:     "users",
				PrimaryKey: "id",
			}},
		},
		{
			Name: "B",
			Type: "sqlite",
			Path: srcB,
			Tables: []config.TableMap{{
				Source:     "users",
				Target:     "users",
				PrimaryKey: "id",
			}},
		},
	})
	cfg.Sync.Conflict = "priority"
	cfg.Sync.Priority = []string{"A", "B"}

	st := deep2ConcurrentNewTarget(t)
	defer st.Close()

	var wg sync.WaitGroup
	errCh := make(chan error, 2)
	wg.Add(2)
	go func() {
		defer wg.Done()
		if _, err := Sync(cfg, st, []string{"A"}, "j"); err != nil {
			errCh <- err
		}
	}()
	go func() {
		defer wg.Done()
		if _, err := Sync(cfg, st, []string{"B"}, "j"); err != nil {
			errCh <- err
		}
	}()
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("concurrent Sync error: %v", err)
	}

	_, rowsOut, err := st.Query(`SELECT "id","name" FROM "users" ORDER BY "id"`)
	if err != nil {
		t.Fatalf("query users: %v", err)
	}
	if len(rowsOut) != 1 {
		t.Fatalf("expected exactly 1 row, got %d", len(rowsOut))
	}
	idVal := fmt.Sprint(rowsOut[0][0])
	if idVal != "1" {
		t.Fatalf("expected id=1, got %v", rowsOut[0][0])
	}
	nameVal, _ := rowsOut[0][1].(string)
	if nameVal != "alice" && nameVal != "bob" {
		t.Fatalf("expected name alice or bob, got %q", nameVal)
	}

	conflicts, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list conflicts: %v", err)
	}
	count := 0
	for _, c := range conflicts {
		if c.Status == "pending" || c.Status == "resolved_auto" {
			count++
		}
	}
	if count < 1 {
		t.Fatalf("expected at least 1 conflict record (pending or resolved_auto), got %d", count)
	}
}

func TestDeep2Concurrent_RecordConflictStorm(t *testing.T) {
	st := deep2ConcurrentNewTarget(t)
	defer st.Close()

	const workers = 50
	var wg sync.WaitGroup
	errCh := make(chan error, workers)
	idCh := make(chan int64, workers)

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			id, err := st.RecordConflict(st.DB, store.Conflict{
				TableName: "users",
				PK:        fmt.Sprintf("pk-%d", n),
				SourceA:   "A",
				SourceB:   "B",
				RowJSON:   fmt.Sprintf(`{"n":%d}`, n),
				Status:    "pending",
				CreatedAt: time.Now().UTC().Format(time.RFC3339),
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
		t.Fatalf("RecordConflict error: %v", err)
	}

	ids := map[int64]bool{}
	for id := range idCh {
		if ids[id] {
			t.Fatalf("duplicate conflict id %d", id)
		}
		ids[id] = true
	}
	if len(ids) != workers {
		t.Fatalf("expected %d unique conflict ids, got %d", workers, len(ids))
	}

	conflicts, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list conflicts: %v", err)
	}
	if len(conflicts) != workers {
		t.Fatalf("expected %d conflict records, got %d", workers, len(conflicts))
	}
}

func TestDeep2Concurrent_SyncWhileResolve(t *testing.T) {
	dir := t.TempDir()
	srcA := filepath.Join(dir, "a.db")
	srcB := filepath.Join(dir, "b.db")

	deep2ConcurrentMakeSource(t, srcA, [][2]string{{"1", "alice-v0"}})
	deep2ConcurrentMakeSource(t, srcB, [][2]string{{"1", "bob"}})

	cfg := deep2ConcurrentCfg(t, []config.SourceConfig{
		{
			Name: "A",
			Type: "sqlite",
			Path: srcA,
			Tables: []config.TableMap{{
				Source:     "users",
				Target:     "users",
				PrimaryKey: "id",
			}},
		},
		{
			Name: "B",
			Type: "sqlite",
			Path: srcB,
			Tables: []config.TableMap{{
				Source:     "users",
				Target:     "users",
				PrimaryKey: "id",
			}},
		},
	})
	cfg.Sync.Conflict = "priority"
	cfg.Sync.Priority = []string{"A", "B"}

	st := deep2ConcurrentNewTarget(t)
	defer st.Close()

	if _, err := Sync(cfg, st, []string{"B"}, "j"); err != nil {
		t.Fatalf("initial sync B: %v", err)
	}

	syncErrCh := make(chan error, 8)
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 1; i <= 5; i++ {
			src, err := store.Open(srcA)
			if err != nil {
				syncErrCh <- err
				return
			}
			if _, err := src.DB.Exec(`UPDATE "users" SET "name"=? WHERE "id"='1'`, fmt.Sprintf("alice-v%d", i)); err != nil {
				src.Close()
				syncErrCh <- err
				return
			}
			if err := src.Close(); err != nil {
				syncErrCh <- err
				return
			}
			if _, err := Sync(cfg, st, []string{"A"}, "j"); err != nil {
				syncErrCh <- err
				return
			}
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 20; i++ {
			conflicts, err := st.ListConflicts("")
			if err != nil {
				syncErrCh <- err
				return
			}
			for _, c := range conflicts {
				if c.Status == "pending" {
					_ = st.ResolveConflict(c.ID, "resolved")
				}
			}
		}
	}()

	wg.Wait()
	close(syncErrCh)
	for err := range syncErrCh {
		t.Fatalf("concurrent sync/resolve error: %v", err)
	}

	conflicts, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("final list conflicts: %v", err)
	}
	for _, c := range conflicts {
		if c.Status != "pending" && c.Status != "resolved" && c.Status != "resolved_auto" {
			t.Fatalf("unexpected conflict status %q for id %d", c.Status, c.ID)
		}
	}
}
