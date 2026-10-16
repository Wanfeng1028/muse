package store

import (
	"database/sql"
	"errors"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

// v4 建表语句：与 db.schema 一致，但 links 表不含 purge_after_burn。
const v4Schema = `
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
	password_hash TEXT,
	burned_at TEXT,
	created_at TEXT NOT NULL,

	updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visits (
	id INTEGER PRIMARY KEY,
	link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
	ts TEXT NOT NULL,
	ip_hash TEXT NOT NULL DEFAULT "",
	ua TEXT NOT NULL DEFAULT "",
	referer TEXT NOT NULL DEFAULT ""
);

CREATE INDEX IF NOT EXISTS idx_visits_link_ts ON visits(link_id, ts);
CREATE INDEX IF NOT EXISTS idx_links_slug ON links(slug);
`

// columnExists 通过 PRAGMA table_info 判断列是否存在。
func columnExists(t *testing.T, database *sql.DB, table, column string) bool {
	t.Helper()
	rows, err := database.Query("PRAGMA table_info(" + table + ");")
	if err != nil {
		t.Fatalf("table_info: %v", err)
	}
	defer func() {
		_ = rows.Close()
	}()
	for rows.Next() {
		var (
			cid       int
			name      string
			ctype     string
			notnull   int
			dfltValue sql.NullString
			pk        int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dfltValue, &pk); err != nil {
			t.Fatalf("scan table_info: %v", err)
		}
		if name == column {
			return true
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate table_info: %v", err)
	}
	return false
}

func TestMigrateV4ToV5(t *testing.T) {
	path := filepath.Join(t.TempDir(), "v4.db")

	// 手建一个 v4 库。
	raw, err := sql.Open("sqlite", "file:"+path+"?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(ON)")
	if err != nil {
		t.Fatalf("open raw: %v", err)
	}
	raw.SetMaxOpenConns(1)
	if _, err := raw.Exec(v4Schema); err != nil {
		t.Fatalf("apply v4 schema: %v", err)
	}
	if _, err := raw.Exec("PRAGMA user_version = 4;"); err != nil {
		t.Fatalf("set user_version=4: %v", err)
	}
	if _, err := raw.Exec(
		`INSERT INTO links (slug, url, title, clicks, enabled, burn, created_at, updated_at)
		 VALUES (?, ?, ?, 0, 1, 0, ?, ?)`,
		"old-1", "https://example.com/old", "旧数据", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z",
	); err != nil {
		t.Fatalf("insert old row: %v", err)
	}
	if err := raw.Close(); err != nil {
		t.Fatalf("close raw: %v", err)
	}

	// 用 db.Open 打开同一文件，触发迁移。
	database, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer func() {
		_ = database.Close()
	}()

	var v int
	if err := database.QueryRow("PRAGMA user_version;").Scan(&v); err != nil {
		t.Fatalf("read user_version: %v", err)
	}
	if v != 7 {
		t.Fatalf("user_version = %d, want 7", v)
	}
	if !columnExists(t, database, "links", "purge_after_burn") {
		t.Fatalf("purge_after_burn column missing after migration")
	}

	st := New(database)
	got, err := st.GetLinkBySlug("old-1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.PurgeAfterBurn {
		t.Fatalf("old row PurgeAfterBurn = true, want false")
	}
	if got.Slug != "old-1" || got.URL != "https://example.com/old" || got.Title != "旧数据" {
		t.Fatalf("old row fields damaged: %+v", got)
	}
	if !got.Enabled {
		t.Fatalf("old row Enabled = false, want true")
	}
	if got.Burn {
		t.Fatalf("old row Burn = true, want false")
	}
	if got.BurnedAt != nil {
		t.Fatalf("old row BurnedAt = %v, want nil", got.BurnedAt)
	}
}

func TestCreateLinkEx_PurgeFlag(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer func() {
		_ = database.Close()
	}()
	st := New(database)

	id1, err := st.CreateLinkEx("p-1", "https://example.com/a", "t1", nil, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx burn+purge: %v", err)
	}
	l1, err := st.GetLink(id1)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if !l1.Burn {
		t.Fatalf("Burn = false, want true")
	}
	if !l1.PurgeAfterBurn {
		t.Fatalf("PurgeAfterBurn = false, want true")
	}

	id2, err := st.CreateLinkEx("p-2", "https://example.com/b", "t2", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx no burn no purge: %v", err)
	}
	l2, err := st.GetLink(id2)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if l2.Burn {
		t.Fatalf("Burn = true, want false")
	}
	if l2.PurgeAfterBurn {
		t.Fatalf("PurgeAfterBurn = true, want false")
	}
}

func TestUpdateLinkEx_PurgeFlag(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer func() {
		_ = database.Close()
	}()
	st := New(database)

	id, err := st.CreateLinkEx("u-1", "https://example.com/u", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if l.PurgeAfterBurn {
		t.Fatalf("initial PurgeAfterBurn = true, want false")
	}

	if err := st.UpdateLinkEx(id, l.Title, l.Enabled, l.ExpiresAt, l.MaxVisits, true, true); err != nil {
		t.Fatalf("UpdateLinkEx: %v", err)
	}
	got, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink after update: %v", err)
	}
	if !got.PurgeAfterBurn {
		t.Fatalf("PurgeAfterBurn = false after update, want true")
	}
	if !got.Burn {
		t.Fatalf("Burn = false after update, want true")
	}
}

func TestPurgeLink_DeletesRowAndVisits(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer func() {
		_ = database.Close()
	}()
	st := New(database)

	id, err := st.CreateLinkEx("purge-1", "https://example.com/p", "t", nil, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := st.RecordVisit(id, "iphash", "ua", ""); err != nil {
		t.Fatalf("RecordVisit 1: %v", err)
	}
	if err := st.RecordVisit(id, "iphash", "ua", ""); err != nil {
		t.Fatalf("RecordVisit 2: %v", err)
	}

	var before int64
	if err := database.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, id).Scan(&before); err != nil {
		t.Fatalf("count visits before: %v", err)
	}
	if before != 2 {
		t.Fatalf("visits before purge = %d, want 2", before)
	}

	if err := st.PurgeLink(id); err != nil {
		t.Fatalf("PurgeLink: %v", err)
	}

	if _, err := st.GetLinkBySlug("purge-1"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLinkBySlug after purge err = %v, want ErrNotFound", err)
	}
	var after int64
	if err := database.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, id).Scan(&after); err != nil {
		t.Fatalf("count visits after: %v", err)
	}
	if after != 0 {
		t.Fatalf("visits after purge = %d, want 0", after)
	}
}
