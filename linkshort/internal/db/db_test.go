package db

import (
	"database/sql"
	"testing"
)

func TestMigrateV5ToV6AddsGeoColumns(t *testing.T) {
	path := t.TempDir() + "/test.db"

	raw, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	if _, err := raw.Exec(`CREATE TABLE IF NOT EXISTS visits (
id INTEGER PRIMARY KEY,
link_id INTEGER NOT NULL,
ts TEXT NOT NULL,
ip_hash TEXT NOT NULL DEFAULT "",
ua TEXT NOT NULL DEFAULT "",
referer TEXT NOT NULL DEFAULT ""
);`); err != nil {
		raw.Close()
		t.Fatalf("create old visits: %v", err)
	}
	if _, err := raw.Exec("PRAGMA user_version = 5;"); err != nil {
		raw.Close()
		t.Fatalf("set user_version: %v", err)
	}
	if err := raw.Close(); err != nil {
		t.Fatalf("close raw: %v", err)
	}

	d, err := Open(path)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer d.Close()

	rows, err := d.Query("PRAGMA table_info(visits);")
	if err != nil {
		t.Fatalf("table_info: %v", err)
	}
	defer rows.Close()
	cols := map[string]bool{}
	for rows.Next() {
		var cid int
		var name, ctype string
		var notnull, pk int
		var dflt any
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			t.Fatalf("scan: %v", err)
		}
		cols[name] = true
	}
	if !cols["country_code"] || !cols["country_name"] || !cols["province"] {
		t.Fatalf("missing geo columns: %+v", cols)
	}

	var version int
	if err := d.QueryRow("PRAGMA user_version;").Scan(&version); err != nil {
		t.Fatalf("user_version: %v", err)
	}
	if version != 6 {
		t.Fatalf("want user_version 6, got %d", version)
	}
}
