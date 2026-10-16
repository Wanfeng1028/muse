package store

import (
	"database/sql"
	"errors"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

func openTestStorePassword(t *testing.T) *Store {
	t.Helper()
	path := filepath.Join(t.TempDir(), "linkshort_test.db")
	database, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return New(database)
}

func TestSetAndClearLinkPassword(t *testing.T) {
	s := openTestStorePassword(t)

	id, err := s.CreateLink("pw1", "https://example.com", "", nil)
	if err != nil {
		t.Fatalf("CreateLink failed: %v", err)
	}

	link, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink failed: %v", err)
	}
	if link.PasswordHash != nil {
		t.Fatalf("expected PasswordHash nil, got %v", *link.PasswordHash)
	}

	fakeHash := "$2a$04$fakehashforunittestonly0000000000000000000000"
	if err := s.SetLinkPassword(id, fakeHash); err != nil {
		t.Fatalf("SetLinkPassword failed: %v", err)
	}

	link, err = s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink failed: %v", err)
	}
	if link.PasswordHash == nil {
		t.Fatalf("expected PasswordHash non-nil after SetLinkPassword")
	}
	if *link.PasswordHash != fakeHash {
		t.Fatalf("PasswordHash mismatch: got %q want %q", *link.PasswordHash, fakeHash)
	}

	if err := s.ClearLinkPassword(id); err != nil {
		t.Fatalf("ClearLinkPassword failed: %v", err)
	}

	link, err = s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink failed: %v", err)
	}
	if link.PasswordHash != nil {
		t.Fatalf("expected PasswordHash nil after ClearLinkPassword, got %v", *link.PasswordHash)
	}
}

func TestSetLinkPasswordNotFound(t *testing.T) {
	s := openTestStorePassword(t)

	if err := s.SetLinkPassword(999999, "$2a$04$fakehashforunittestonly0000000000000000000000"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound from SetLinkPassword, got %v", err)
	}
	if err := s.ClearLinkPassword(999999); !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound from ClearLinkPassword, got %v", err)
	}
}

func TestSetLinkPasswordEmptyHash(t *testing.T) {
	s := openTestStorePassword(t)

	id, err := s.CreateLink("pw-empty", "https://example.com", "", nil)
	if err != nil {
		t.Fatalf("CreateLink failed: %v", err)
	}
	if err := s.SetLinkPassword(id, ""); err == nil {
		t.Fatalf("expected error for empty hash")
	}
}

func TestMigrateV2ToV3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "linkshort_v2.db")

	raw, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		t.Fatalf("sql.Open failed: %v", err)
	}
	v2Schema := `
CREATE TABLE IF NOT EXISTS links (
	id INTEGER PRIMARY KEY,
	slug TEXT UNIQUE NOT NULL,
	url TEXT NOT NULL,
	title TEXT NOT NULL DEFAULT "",
	clicks INTEGER NOT NULL DEFAULT 0,
	enabled INTEGER NOT NULL DEFAULT 1,
	expires_at TEXT,
	max_visits INTEGER,
	burn INTEGER NOT NULL DEFAULT 0,
	created_at TEXT NOT NULL,
	updated_at TEXT NOT NULL
);
PRAGMA user_version=2;
`
	if _, err := raw.Exec(v2Schema); err != nil {
		_ = raw.Close()
		t.Fatalf("failed to create v2 schema: %v", err)
	}
	if _, err := raw.Exec(`INSERT INTO links (slug, url, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)`, "old-slug", "https://old.example.com", "old", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"); err != nil {
		_ = raw.Close()
		t.Fatalf("failed to insert v2 row: %v", err)
	}
	if err := raw.Close(); err != nil {
		t.Fatalf("failed to close v2 db: %v", err)
	}

	database, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open on v2 db failed: %v", err)
	}
	defer func() { _ = database.Close() }()

	var version int
	if err := database.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		t.Fatalf("read user_version failed: %v", err)
	}
	if version != 4 {
		t.Fatalf("expected user_version=4 after migration, got %d", version)
	}

	s := New(database)

	var id int64
	if err := database.QueryRow("SELECT id FROM links WHERE slug = ?", "old-slug").Scan(&id); err != nil {
		t.Fatalf("old row not found after migration: %v", err)
	}

	old, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink on old row failed: %v", err)
	}
	if old.Slug != "old-slug" {
		t.Fatalf("slug mismatch: got %q want %q", old.Slug, "old-slug")
	}
	if old.URL != "https://old.example.com" {
		t.Fatalf("url mismatch: got %q want %q", old.URL, "https://old.example.com")
	}

	newID, err := s.CreateLink("new-slug", "https://new.example.com", "", nil)
	if err != nil {
		t.Fatalf("CreateLink after migration failed: %v", err)
	}
	if err := s.SetLinkPassword(newID, "$2a$04$fakehashforunittestonly0000000000000000000000"); err != nil {
		t.Fatalf("SetLinkPassword after migration failed: %v", err)
	}
}
