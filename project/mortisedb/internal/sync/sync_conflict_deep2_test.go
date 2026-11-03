package sync

import (
	"fmt"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func openSourceDeep2(t *testing.T, dir, name string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	src, err := store.Open(p)
	if err != nil {
		t.Fatalf("open source %s: %v", name, err)
	}
	if _, err := src.DB.Exec(`CREATE TABLE "users" ("id" TEXT PRIMARY KEY, "name" TEXT)`); err != nil {
		t.Fatalf("create table: %v", err)
	}
	src.Close()
	return p
}

func seedUsersDeep2(t *testing.T, path, id, name string) {
	t.Helper()
	src, err := store.Open(path)
	if err != nil {
		t.Fatalf("open seed %s: %v", path, err)
	}
	if _, err := src.DB.Exec(`INSERT OR REPLACE INTO "users" ("id","name") VALUES (?,?)`, id, name); err != nil {
		t.Fatalf("insert: %v", err)
	}
	src.Close()
}

func openTargetDeep2(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(filepath.Join(t.TempDir(), "t.db"))
	if err != nil {
		t.Fatalf("open target: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return st
}

func makeCfgDeep2(dir string, aPath, bPath string, conflict string, priority []string) *config.Config {
	return &config.Config{
		Sources: []config.SourceConfig{
			{
				Name:        "A",
				Type:        "sqlite",
				Path:        aPath,
				Incremental: "",
				Tables:      []config.TableMap{{Source: "users", Target: "users", PrimaryKey: "id"}},
			},
			{
				Name:        "B",
				Type:        "sqlite",
				Path:        bPath,
				Incremental: "",
				Tables:      []config.TableMap{{Source: "users", Target: "users", PrimaryKey: "id"}},
			},
		},
		Sync: config.SyncPolicy{
			Conflict:  conflict,
			Priority:  priority,
			BatchSize: 100,
		},
	}
}

func userNameDeep2(t *testing.T, st *store.Store, id string) string {
	t.Helper()
	cols, rows, err := st.Query(`SELECT "name" FROM "users" WHERE "id"='` + id + `'`)
	if err != nil {
		t.Fatalf("query name: %v", err)
	}
	if len(rows) == 0 {
		return ""
	}
	idx := -1
	for i, c := range cols {
		if c == "name" {
			idx = i
			break
		}
	}
	if idx < 0 {
		t.Fatal("column name not found")
	}
	return fmt.Sprint(rows[0][idx])
}

func TestDeep2PriorityIndex_Boundaries(t *testing.T) {
	if got := PriorityIndex(nil, "a"); got != 1<<30 {
		t.Fatalf("nil list: got %d want %d", got, 1<<30)
	}
	if got := PriorityIndex([]string{"b", "a"}, "a"); got != 1 {
		t.Fatalf("pos 1: got %d want 1", got)
	}
	if got := PriorityIndex([]string{"a"}, "b"); got != 1<<30 {
		t.Fatalf("missing: got %d want %d", got, 1<<30)
	}
	if got := PriorityIndex([]string{"a", "a"}, "a"); got != 0 {
		t.Fatalf("first occurrence: got %d want 0", got)
	}
}

func TestDeep2Adjudication_HigherPriorityWins(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "bob")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "priority", []string{"B", "A"})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}

	stats, err := Sync(cfg, st, []string{"B"}, "job2")
	if err != nil {
		t.Fatalf("sync B: %v", err)
	}

	var conflicts int
	for _, s := range stats {
		for _, tb := range s.Tables {
			conflicts += tb.Conflicts
		}
	}
	if conflicts < 1 {
		t.Fatalf("expected conflicts >= 1, got %d", conflicts)
	}

	resolved, err := st.ListConflicts("resolved_auto")
	if err != nil {
		t.Fatalf("list resolved_auto: %v", err)
	}
	if len(resolved) != 1 {
		t.Fatalf("expected 1 resolved_auto, got %d", len(resolved))
	}
	if resolved[0].SourceA != "A" || resolved[0].SourceB != "B" {
		t.Fatalf("unexpected conflict sources: %+v", resolved[0])
	}

	if got := userNameDeep2(t, st, "1"); got != "bob" {
		t.Fatalf("expected name bob, got %q", got)
	}
}

func TestDeep2Adjudication_LowerPriorityPends(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "bob")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "priority", []string{"A", "B"})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}

	stats, err := Sync(cfg, st, []string{"B"}, "job2")
	if err != nil {
		t.Fatalf("sync B: %v", err)
	}

	var conflicts int
	for _, s := range stats {
		for _, tb := range s.Tables {
			conflicts += tb.Conflicts
		}
	}
	if conflicts != 1 {
		t.Fatalf("expected conflicts == 1, got %d", conflicts)
	}

	pending, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("expected 1 pending, got %d", len(pending))
	}

	if got := userNameDeep2(t, st, "1"); got != "alice" {
		t.Fatalf("expected name alice, got %q", got)
	}
}

func TestDeep2Adjudication_EqualPriorityPends(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "bob")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "priority", []string{})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}

	if _, err := Sync(cfg, st, []string{"B"}, "job2"); err != nil {
		t.Fatalf("sync B: %v", err)
	}

	pending, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("expected 1 pending, got %d", len(pending))
	}

	resolved, err := st.ListConflicts("resolved_auto")
	if err != nil {
		t.Fatalf("list resolved_auto: %v", err)
	}
	if len(resolved) != 0 {
		t.Fatalf("expected 0 resolved_auto, got %d", len(resolved))
	}

	if got := userNameDeep2(t, st, "1"); got != "alice" {
		t.Fatalf("expected name alice, got %q", got)
	}
}

func TestDeep2Adjudication_DefaultBehavesLikePriority(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "bob")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "", []string{"B", "A"})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}

	if _, err := Sync(cfg, st, []string{"B"}, "job2"); err != nil {
		t.Fatalf("sync B: %v", err)
	}

	resolved, err := st.ListConflicts("resolved_auto")
	if err != nil {
		t.Fatalf("list resolved_auto: %v", err)
	}
	if len(resolved) != 1 {
		t.Fatalf("expected 1 resolved_auto, got %d", len(resolved))
	}

	if got := userNameDeep2(t, st, "1"); got != "bob" {
		t.Fatalf("expected name bob, got %q", got)
	}
}

func TestDeep2Adjudication_ManualAlwaysPends(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "bob")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "manual", []string{"B", "A"})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}

	stats, err := Sync(cfg, st, []string{"B"}, "job2")
	if err != nil {
		t.Fatalf("sync B: %v", err)
	}

	pending, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("expected 1 pending, got %d", len(pending))
	}

	resolved, err := st.ListConflicts("resolved_auto")
	if err != nil {
		t.Fatalf("list resolved_auto: %v", err)
	}
	if len(resolved) != 0 {
		t.Fatalf("expected 0 resolved_auto, got %d", len(resolved))
	}

	for _, s := range stats {
		for _, tb := range s.Tables {
			if tb.Updated != 0 {
				t.Fatalf("expected Updated == 0, got %d", tb.Updated)
			}
		}
	}

	if got := userNameDeep2(t, st, "1"); got != "alice" {
		t.Fatalf("expected name alice, got %q", got)
	}
}

func TestDeep2Adjudication_SameSourceChangeAutoResolves(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "bob")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "priority", []string{"A", "B"})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}
	if _, err := Sync(cfg, st, []string{"B"}, "job2"); err != nil {
		t.Fatalf("sync B: %v", err)
	}

	pending, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("expected 1 pending before change, got %d", len(pending))
	}

	seedUsersDeep2(t, aPath, "1", "alice2")

	if _, err := Sync(cfg, st, []string{"A"}, "job3"); err != nil {
		t.Fatalf("sync A again: %v", err)
	}

	pending2, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list pending after: %v", err)
	}
	if len(pending2) != 0 {
		t.Fatalf("expected 0 pending after same-source update, got %d", len(pending2))
	}

	resolved, err := st.ListConflicts("resolved_auto")
	if err != nil {
		t.Fatalf("list resolved_auto: %v", err)
	}
	found := false
	for _, c := range resolved {
		if c.PK == "1" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected resolved_auto for pk 1, got %+v", resolved)
	}

	if got := userNameDeep2(t, st, "1"); got != "alice2" {
		t.Fatalf("expected name alice2, got %q", got)
	}
}

func TestDeep2Adjudication_NoConflictWhenSameContent(t *testing.T) {
	dir := t.TempDir()
	aPath := openSourceDeep2(t, dir, "a.db")
	bPath := openSourceDeep2(t, dir, "b.db")
	seedUsersDeep2(t, aPath, "1", "alice")
	seedUsersDeep2(t, bPath, "1", "alice")

	st := openTargetDeep2(t)
	defer st.Close()

	cfg := makeCfgDeep2(dir, aPath, bPath, "priority", []string{"A", "B"})

	if _, err := Sync(cfg, st, []string{"A"}, "job1"); err != nil {
		t.Fatalf("sync A: %v", err)
	}

	stats, err := Sync(cfg, st, []string{"B"}, "job2")
	if err != nil {
		t.Fatalf("sync B: %v", err)
	}

	all, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("list conflicts: %v", err)
	}
	if len(all) != 0 {
		t.Fatalf("expected no conflicts, got %d", len(all))
	}

	var skipped, conflicts int
	for _, s := range stats {
		for _, tb := range s.Tables {
			skipped += tb.Skipped
			conflicts += tb.Conflicts
		}
	}
	if skipped < 1 {
		t.Fatalf("expected skipped >= 1, got %d", skipped)
	}
	if conflicts != 0 {
		t.Fatalf("expected conflicts == 0, got %d", conflicts)
	}
}
