package store

import (
	"database/sql"
	"testing"

	_ "modernc.org/sqlite"
)

func TestMigrateNewDBHasCurrentVersion(t *testing.T) {
	s, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()

	v, err := GetSchemaVersion(s.db)
	if err != nil {
		t.Fatalf("GetSchemaVersion: %v", err)
	}
	if v != CurrentSchemaVersion {
		t.Fatalf("schema version = %d, want %d", v, CurrentSchemaVersion)
	}
}

func TestMigrateIsIdempotent(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	// 生产路径 OpenStore 也是先 createSchema 再 Migrate；迁移函数要求表已存在。
	if err := createSchema(db); err != nil {
		t.Fatalf("createSchema: %v", err)
	}

	if err := Migrate(db); err != nil {
		t.Fatalf("first Migrate: %v", err)
	}
	if err := Migrate(db); err != nil {
		t.Fatalf("second Migrate: %v", err)
	}

	v, err := GetSchemaVersion(db)
	if err != nil {
		t.Fatalf("GetSchemaVersion: %v", err)
	}
	if v != CurrentSchemaVersion {
		t.Fatalf("schema version = %d, want %d", v, CurrentSchemaVersion)
	}
}

func TestMigrateUpgradesOldReviewsSchema(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	if _, err := db.Exec(`CREATE TABLE reviews (
		note_id INTEGER NOT NULL PRIMARY KEY,
		ef REAL NOT NULL DEFAULT 2.5,
		interval_days INTEGER NOT NULL DEFAULT 0,
		repetitions INTEGER NOT NULL DEFAULT 0,
		due_date TEXT NOT NULL,
		last_reviewed_at TEXT,
		reviewed_count INTEGER NOT NULL DEFAULT 0
	)`); err != nil {
		t.Fatalf("create old reviews table: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO reviews (note_id, due_date) VALUES (1, '2024-01-01')`); err != nil {
		t.Fatalf("insert old review: %v", err)
	}
	// migration 2 需要 push_log 表存在，这里按老 schema 建（无 user_id）。
	if _, err := db.Exec(`CREATE TABLE push_log (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		date TEXT NOT NULL,
		channel TEXT NOT NULL,
		status TEXT NOT NULL,
		detail TEXT NOT NULL DEFAULT '',
		created_at TEXT NOT NULL
	)`); err != nil {
		t.Fatalf("create old push_log table: %v", err)
	}
	if _, err := db.Exec(`CREATE UNIQUE INDEX idx_push_log_date_channel ON push_log(date, channel)`); err != nil {
		t.Fatalf("create old unique index: %v", err)
	}

	if err := Migrate(db); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	v, err := GetSchemaVersion(db)
	if err != nil {
		t.Fatalf("GetSchemaVersion: %v", err)
	}
	if v != CurrentSchemaVersion {
		t.Fatalf("schema version = %d, want %d", v, CurrentSchemaVersion)
	}

	if !tableHasColumn(t, db, "reviews", "user_id") {
		t.Fatalf("reviews table missing user_id column")
	}

	var userID string
	if err := db.QueryRow(`SELECT user_id FROM reviews WHERE note_id = 1`).Scan(&userID); err != nil {
		t.Fatalf("select user_id: %v", err)
	}
	if userID != "local" {
		t.Fatalf("user_id = %q, want %q", userID, "local")
	}
}

func TestMigrateUpgradesOldPushLogSchema(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	if _, err := db.Exec(`CREATE TABLE push_log (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		date TEXT NOT NULL,
		channel TEXT NOT NULL,
		status TEXT NOT NULL,
		detail TEXT NOT NULL DEFAULT '',
		created_at TEXT NOT NULL
	)`); err != nil {
		t.Fatalf("create old push_log table: %v", err)
	}
	if _, err := db.Exec(`CREATE UNIQUE INDEX idx_push_log_date_channel ON push_log(date, channel)`); err != nil {
		t.Fatalf("create old unique index: %v", err)
	}
	// migration 1 需要 reviews 表存在，这里按老 schema 建（无 user_id、主键 note_id 单列）。
	if _, err := db.Exec(`CREATE TABLE reviews (
		note_id INTEGER NOT NULL PRIMARY KEY,
		ef REAL NOT NULL DEFAULT 2.5,
		interval_days INTEGER NOT NULL DEFAULT 0,
		repetitions INTEGER NOT NULL DEFAULT 0,
		due_date TEXT NOT NULL,
		last_reviewed_at TEXT,
		reviewed_count INTEGER NOT NULL DEFAULT 0
	)`); err != nil {
		t.Fatalf("create old reviews table: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO push_log (date, channel, status, created_at) VALUES ('2024-01-01', 'cli', 'ok', '2024-01-01T00:00:00Z')`); err != nil {
		t.Fatalf("insert old push_log: %v", err)
	}

	if err := Migrate(db); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	v, err := GetSchemaVersion(db)
	if err != nil {
		t.Fatalf("GetSchemaVersion: %v", err)
	}
	if v != CurrentSchemaVersion {
		t.Fatalf("schema version = %d, want %d", v, CurrentSchemaVersion)
	}

	if !tableHasColumn(t, db, "push_log", "user_id") {
		t.Fatalf("push_log table missing user_id column")
	}

	var userID string
	if err := db.QueryRow(`SELECT user_id FROM push_log WHERE id = 1`).Scan(&userID); err != nil {
		t.Fatalf("select user_id: %v", err)
	}
	if userID != "local" {
		t.Fatalf("user_id = %q, want %q", userID, "local")
	}

	if !indexExists(t, db, "idx_push_log_date_channel_user") {
		t.Fatalf("index idx_push_log_date_channel_user not found")
	}
}

func tableHasColumn(t *testing.T, db *sql.DB, table, column string) bool {
	t.Helper()
	rows, err := db.Query(`PRAGMA table_info(` + table + `)`)
	if err != nil {
		t.Fatalf("PRAGMA table_info(%s): %v", table, err)
	}
	defer rows.Close()

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
		t.Fatalf("rows.Err: %v", err)
	}
	return false
}
