package backup

import (
	"database/sql"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

func TestBackupDeep2KeepZeroDefaultsToSeven(t *testing.T) {
	dir := t.TempDir()
	backupDir := filepath.Join(dir, "backups")
	dbPath := filepath.Join(dir, "sentinel.db")

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	if _, err := db.Exec("CREATE TABLE t (id INTEGER)"); err != nil {
		t.Fatalf("create table: %v", err)
	}
	db.Close()

	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		t.Fatalf("mkdir backup: %v", err)
	}
	base := time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 9; i++ {
		name := filepath.Join(backupDir, "sentinel-2020"+"0101"+"-"+"000000"+".db")
		name = filepath.Join(backupDir, "sentinel-20200101-0000"+"0"+string(rune('0'+i))+".db")
		if err := os.WriteFile(name, []byte("old"), 0o644); err != nil {
			t.Fatalf("write old backup: %v", err)
		}
		ts := base.Add(time.Duration(i) * time.Second)
		if err := os.Chtimes(name, ts, ts); err != nil {
			t.Fatalf("chtimes: %v", err)
		}
	}

	if _, err := Backup(dbPath, backupDir, 0); err != nil {
		t.Fatalf("Backup: %v", err)
	}

	infos, err := List(backupDir)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(infos) != 7 {
		t.Fatalf("expected 7 backups after keep=0, got %d", len(infos))
	}
}

func TestBackupDeep2KeepTwo(t *testing.T) {
	dir := t.TempDir()
	backupDir := filepath.Join(dir, "backups")
	dbPath := filepath.Join(dir, "sentinel.db")

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	if _, err := db.Exec("CREATE TABLE t (id INTEGER)"); err != nil {
		t.Fatalf("create table: %v", err)
	}
	db.Close()

	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		t.Fatalf("mkdir backup: %v", err)
	}
	base := time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 5; i++ {
		name := filepath.Join(backupDir, "sentinel-20200101-0000"+string(rune('0'+i))+".db")
		if err := os.WriteFile(name, []byte("old"), 0o644); err != nil {
			t.Fatalf("write old backup: %v", err)
		}
		ts := base.Add(time.Duration(i) * time.Second)
		if err := os.Chtimes(name, ts, ts); err != nil {
			t.Fatalf("chtimes: %v", err)
		}
	}

	if _, err := Backup(dbPath, backupDir, 2); err != nil {
		t.Fatalf("Backup: %v", err)
	}

	infos, err := List(backupDir)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(infos) != 2 {
		t.Fatalf("expected 2 backups after keep=2, got %d", len(infos))
	}
}

func TestBackupDeep2SameSecondSuffix(t *testing.T) {
	dir := t.TempDir()
	backupDir := filepath.Join(dir, "backups")
	dbPath := filepath.Join(dir, "sentinel.db")

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	if _, err := db.Exec("CREATE TABLE t (id INTEGER)"); err != nil {
		t.Fatalf("create table: %v", err)
	}
	db.Close()

	first, err := Backup(dbPath, backupDir, 7)
	if err != nil {
		t.Fatalf("first Backup: %v", err)
	}
	second, err := Backup(dbPath, backupDir, 7)
	if err != nil {
		t.Fatalf("second Backup: %v", err)
	}

	if first == second {
		t.Fatalf("expected distinct paths, got %q twice", first)
	}
	if _, err := os.Stat(first); err != nil {
		t.Fatalf("first backup missing: %v", err)
	}
	if _, err := os.Stat(second); err != nil {
		t.Fatalf("second backup missing: %v", err)
	}

	baseFirst := filepath.Base(first)
	baseSecond := filepath.Base(second)
	if baseFirst == baseSecond {
		t.Fatalf("expected distinct base names, got %q twice", baseFirst)
	}

	sameSecond := strings.TrimSuffix(baseFirst, ".db") == strings.TrimSuffix(baseSecond, ".db")
	if sameSecond {
		if !strings.Contains(baseSecond, "-2") && !strings.Contains(baseFirst, "-2") {
			t.Fatalf("same-second backups expected a -2 suffix, got %q and %q", baseFirst, baseSecond)
		}
	}

	infos, err := List(backupDir)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(infos) != 2 {
		t.Fatalf("expected 2 backups, got %d", len(infos))
	}
}

func TestListDeep2FiltersNamesAndDirs(t *testing.T) {
	dir := t.TempDir()

	valid := filepath.Join(dir, "sentinel-20200101-000000.db")
	if err := os.WriteFile(valid, []byte("x"), 0o644); err != nil {
		t.Fatalf("write valid: %v", err)
	}
	notSentinel := filepath.Join(dir, "other-20200101-000000.db")
	if err := os.WriteFile(notSentinel, []byte("x"), 0o644); err != nil {
		t.Fatalf("write notSentinel: %v", err)
	}
	notDB := filepath.Join(dir, "sentinel-20200101-000000.txt")
	if err := os.WriteFile(notDB, []byte("x"), 0o644); err != nil {
		t.Fatalf("write notDB: %v", err)
	}
	sub := filepath.Join(dir, "sentinel-subdir.db")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatalf("mkdir sub: %v", err)
	}

	infos, err := List(dir)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(infos) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(infos))
	}
	if infos[0].Name != "sentinel-20200101-000000.db" {
		t.Fatalf("expected sentinel file, got %q", infos[0].Name)
	}
}

func TestListDeep2OrderByModTimeDesc(t *testing.T) {
	dir := t.TempDir()

	oldest := filepath.Join(dir, "sentinel-20200101-000000.db")
	middle := filepath.Join(dir, "sentinel-20200102-000000.db")
	newest := filepath.Join(dir, "sentinel-20200103-000000.db")
	for _, p := range []string{oldest, middle, newest} {
		if err := os.WriteFile(p, []byte("x"), 0o644); err != nil {
			t.Fatalf("write %s: %v", p, err)
		}
	}

	base := time.Date(2021, 6, 1, 12, 0, 0, 0, time.UTC)
	if err := os.Chtimes(oldest, base, base); err != nil {
		t.Fatalf("chtimes oldest: %v", err)
	}
	if err := os.Chtimes(middle, base.Add(time.Hour), base.Add(time.Hour)); err != nil {
		t.Fatalf("chtimes middle: %v", err)
	}
	if err := os.Chtimes(newest, base.Add(2*time.Hour), base.Add(2*time.Hour)); err != nil {
		t.Fatalf("chtimes newest: %v", err)
	}

	infos, err := List(dir)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(infos) != 3 {
		t.Fatalf("expected 3 entries, got %d", len(infos))
	}
	if infos[0].Name != "sentinel-20200103-000000.db" {
		t.Fatalf("expected newest first, got %q", infos[0].Name)
	}
	if infos[1].Name != "sentinel-20200102-000000.db" {
		t.Fatalf("expected middle second, got %q", infos[1].Name)
	}
	if infos[2].Name != "sentinel-20200101-000000.db" {
		t.Fatalf("expected oldest last, got %q", infos[2].Name)
	}
}

func TestListDeep2MissingDir(t *testing.T) {
	dir := t.TempDir()
	missing := filepath.Join(dir, "does-not-exist")

	infos, err := List(missing)
	if err != nil {
		t.Fatalf("expected nil error for missing dir, got %v", err)
	}
	if len(infos) != 0 {
		t.Fatalf("expected empty slice, got %d entries", len(infos))
	}
}

func TestRestoreDeep2EmptyPath(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "sentinel.db")

	err := Restore(dbPath, "")
	if err == nil {
		t.Fatal("expected error for empty backup path")
	}
	if !strings.Contains(err.Error(), "备份路径不能为空") {
		t.Fatalf("expected empty-path error message, got %q", err.Error())
	}
}

func TestBackupDeep2MissingDBPath(t *testing.T) {
	dir := t.TempDir()
	backupDir := filepath.Join(dir, "backups")
	dbPath := filepath.Join(dir, "missing.db")

	if _, err := Backup(dbPath, backupDir, 7); err == nil {
		t.Fatal("expected error for missing db path")
	}
}

func TestBackupDeep2ProducesValidSQLite(t *testing.T) {
	dir := t.TempDir()
	backupDir := filepath.Join(dir, "backups")
	dbPath := filepath.Join(dir, "sentinel.db")

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	if _, err := db.Exec("CREATE TABLE widgets (id INTEGER PRIMARY KEY, label TEXT)"); err != nil {
		t.Fatalf("create table: %v", err)
	}
	if _, err := db.Exec("INSERT INTO widgets (label) VALUES ('alpha'), ('beta')"); err != nil {
		t.Fatalf("insert: %v", err)
	}
	db.Close()

	dst, err := Backup(dbPath, backupDir, 7)
	if err != nil {
		t.Fatalf("Backup: %v", err)
	}

	restored, err := sql.Open("sqlite", dst)
	if err != nil {
		t.Fatalf("open backup: %v", err)
	}
	defer restored.Close()

	var count int
	if err := restored.QueryRow("SELECT COUNT(*) FROM widgets").Scan(&count); err != nil {
		t.Fatalf("query widgets: %v", err)
	}
	if count != 2 {
		t.Fatalf("expected 2 rows in restored widgets table, got %d", count)
	}
}
