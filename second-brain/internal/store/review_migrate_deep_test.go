package store

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

func openMigrateTestDB(t *testing.T) *sql.DB {
	t.Helper()
	dir := t.TempDir()
	dsn := "file:" + filepath.Join(dir, "migrate.db") + "?_pragma=foreign_keys(1)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		t.Fatalf("打开测试数据库失败: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func createLegacyReviewsSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	stmts := []string{
		`CREATE TABLE notes (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			title TEXT NOT NULL,
			content TEXT NOT NULL DEFAULT ''
		)`,
		`CREATE TABLE reviews (
			note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
			ef REAL NOT NULL DEFAULT 2.5,
			interval_days INTEGER NOT NULL DEFAULT 0,
			repetitions INTEGER NOT NULL DEFAULT 0,
			due_date TEXT NOT NULL,
			last_reviewed_at TEXT,
			reviewed_count INTEGER NOT NULL DEFAULT 0
		)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("建旧表失败: %v", err)
		}
	}
}

func insertLegacyNote(t *testing.T, db *sql.DB, id int, title string) {
	t.Helper()
	if _, err := db.Exec(`INSERT INTO notes (id, title, content) VALUES (?, ?, '')`, id, title); err != nil {
		t.Fatalf("插入 notes 失败: %v", err)
	}
}

func insertLegacyReview(t *testing.T, db *sql.DB, noteID int, ef float64, intervalDays, repetitions int, dueDate string, lastReviewedAt sql.NullString, reviewedCount int) {
	t.Helper()
	if _, err := db.Exec(
		`INSERT INTO reviews (note_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count)
		 VALUES (?, ?, ?, ?, ?, ?, ?)`,
		noteID, ef, intervalDays, repetitions, dueDate, lastReviewedAt, reviewedCount,
	); err != nil {
		t.Fatalf("插入 reviews 失败: %v", err)
	}
}

type reviewRow struct {
	NoteID         int
	UserID         string
	EF             float64
	IntervalDays   int
	Repetitions    int
	DueDate        string
	LastReviewedAt sql.NullString
	ReviewedCount  int
}

func readReviewRows(t *testing.T, db *sql.DB) []reviewRow {
	t.Helper()
	rows, err := db.Query(`SELECT note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count FROM reviews ORDER BY note_id, user_id`)
	if err != nil {
		t.Fatalf("查询 reviews 失败: %v", err)
	}
	defer rows.Close()
	var out []reviewRow
	for rows.Next() {
		var r reviewRow
		if err := rows.Scan(&r.NoteID, &r.UserID, &r.EF, &r.IntervalDays, &r.Repetitions, &r.DueDate, &r.LastReviewedAt, &r.ReviewedCount); err != nil {
			t.Fatalf("扫描 reviews 失败: %v", err)
		}
		out = append(out, r)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历 reviews 失败: %v", err)
	}
	return out
}

func readPKColumns(t *testing.T, db *sql.DB) map[string]int {
	t.Helper()
	rows, err := db.Query(`PRAGMA table_info(reviews)`)
	if err != nil {
		t.Fatalf("读取 table_info 失败: %v", err)
	}
	defer rows.Close()
	pk := map[string]int{}
	for rows.Next() {
		var (
			cid     int
			name    string
			ctype   string
			notnull int
			dflt    sql.NullString
			pkSeq   int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pkSeq); err != nil {
			t.Fatalf("扫描 table_info 失败: %v", err)
		}
		if pkSeq != 0 {
			pk[name] = pkSeq
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历 table_info 失败: %v", err)
	}
	return pk
}

func hasColumnReview(t *testing.T, db *sql.DB, table, column string) bool {
	t.Helper()
	rows, err := db.Query(`PRAGMA table_info(` + table + `)`)
	if err != nil {
		t.Fatalf("读取 table_info(%s) 失败: %v", table, err)
	}
	defer rows.Close()
	for rows.Next() {
		var (
			cid     int
			name    string
			ctype   string
			notnull int
			dflt    sql.NullString
			pkSeq   int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pkSeq); err != nil {
			t.Fatalf("扫描 table_info(%s) 失败: %v", table, err)
		}
		if name == column {
			return true
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历 table_info(%s) 失败: %v", table, err)
	}
	return false
}

func TestMigrateReviewsUser_跨天与闰日到期值保留(t *testing.T) {
	cases := []struct {
		name          string
		noteID        int
		dueDate       string
		intervalDays  int
		repetitions   int
		ef            float64
		reviewedCount int
	}{
		{name: "普通跨天", noteID: 1, dueDate: "2024-03-01", intervalDays: 1, repetitions: 1, ef: 2.5, reviewedCount: 1},
		{name: "闰日 2月29", noteID: 2, dueDate: "2024-02-29", intervalDays: 4, repetitions: 2, ef: 2.6, reviewedCount: 3},
		{name: "闰年前一天", noteID: 3, dueDate: "2024-02-28", intervalDays: 1, repetitions: 1, ef: 2.4, reviewedCount: 2},
		{name: "跨年边界", noteID: 4, dueDate: "2025-01-01", intervalDays: 30, repetitions: 3, ef: 2.7, reviewedCount: 5},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db := openMigrateTestDB(t)
			createLegacyReviewsSchema(t, db)
			insertLegacyNote(t, db, tc.noteID, "笔记")
			insertLegacyReview(t, db, tc.noteID, tc.ef, tc.intervalDays, tc.repetitions, tc.dueDate, sql.NullString{String: "2024-01-15T08:00:00Z", Valid: true}, tc.reviewedCount)

			if err := migrateReviewsUser(db); err != nil {
				t.Fatalf("迁移失败: %v", err)
			}

			rows := readReviewRows(t, db)
			if len(rows) != 1 {
				t.Fatalf("期望 1 行, 实际 %d", len(rows))
			}
			if rows[0].DueDate != tc.dueDate {
				t.Errorf("due_date 期望 %q, 实际 %q", tc.dueDate, rows[0].DueDate)
			}
			if rows[0].IntervalDays != tc.intervalDays {
				t.Errorf("interval_days 期望 %d, 实际 %d", tc.intervalDays, rows[0].IntervalDays)
			}
			if rows[0].UserID != "local" {
				t.Errorf("user_id 期望 local, 实际 %q", rows[0].UserID)
			}
			if rows[0].ReviewedCount != tc.reviewedCount {
				t.Errorf("reviewed_count 期望 %d, 实际 %d", tc.reviewedCount, rows[0].ReviewedCount)
			}
		})
	}
}

func TestMigrateReviewsUser_时区偏移字符串保留(t *testing.T) {
	cases := []struct {
		name   string
		due    string
		lastAt string
	}{
		{name: "东八区", due: "2024-03-01T00:00:00+08:00", lastAt: "2024-02-28T23:59:59+08:00"},
		{name: "UTC", due: "2024-03-01T00:00:00Z", lastAt: "2024-02-28T16:00:00Z"},
		{name: "西五区", due: "2024-03-01T00:00:00-05:00", lastAt: "2024-02-28T19:00:00-05:00"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db := openMigrateTestDB(t)
			createLegacyReviewsSchema(t, db)
			insertLegacyNote(t, db, 1, "笔记")
			insertLegacyReview(t, db, 1, 2.5, 1, 1, tc.due, sql.NullString{String: tc.lastAt, Valid: true}, 1)

			if err := migrateReviewsUser(db); err != nil {
				t.Fatalf("迁移失败: %v", err)
			}

			rows := readReviewRows(t, db)
			if len(rows) != 1 {
				t.Fatalf("期望 1 行, 实际 %d", len(rows))
			}
			if rows[0].DueDate != tc.due {
				t.Errorf("due_date 期望 %q, 实际 %q", tc.due, rows[0].DueDate)
			}
			if !rows[0].LastReviewedAt.Valid || rows[0].LastReviewedAt.String != tc.lastAt {
				t.Errorf("last_reviewed_at 期望 %q, 实际 %v", tc.lastAt, rows[0].LastReviewedAt)
			}
		})
	}
}

func TestMigrateReviewsUser_SM2极端EF值保留(t *testing.T) {
	cases := []struct {
		name string
		ef   float64
	}{
		{name: "最小值 1.3", ef: 1.3},
		{name: "略高于最小值", ef: 1.31},
		{name: "默认 2.5", ef: 2.5},
		{name: "大值 5.0", ef: 5.0},
		{name: "负值", ef: -1.5},
		{name: "零", ef: 0.0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db := openMigrateTestDB(t)
			createLegacyReviewsSchema(t, db)
			insertLegacyNote(t, db, 1, "笔记")
			insertLegacyReview(t, db, 1, tc.ef, 0, 0, "2024-03-01", sql.NullString{Valid: false}, 0)

			if err := migrateReviewsUser(db); err != nil {
				t.Fatalf("迁移失败: %v", err)
			}

			rows := readReviewRows(t, db)
			if len(rows) != 1 {
				t.Fatalf("期望 1 行, 实际 %d", len(rows))
			}
			if rows[0].EF != tc.ef {
				t.Errorf("ef 期望 %v, 实际 %v", tc.ef, rows[0].EF)
			}
			if rows[0].LastReviewedAt.Valid {
				t.Errorf("last_reviewed_at 期望 NULL, 实际 %v", rows[0].LastReviewedAt)
			}
		})
	}
}

func TestMigrateReviewsUser_添加user_id列并重建主键(t *testing.T) {
	db := openMigrateTestDB(t)
	createLegacyReviewsSchema(t, db)
	insertLegacyNote(t, db, 1, "笔记一")
	insertLegacyNote(t, db, 2, "笔记二")
	insertLegacyReview(t, db, 1, 2.5, 1, 1, "2024-03-01", sql.NullString{String: "2024-02-28", Valid: true}, 1)
	insertLegacyReview(t, db, 2, 2.6, 2, 2, "2024-03-02", sql.NullString{Valid: false}, 2)

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	if !hasColumnReview(t, db, "reviews", "user_id") {
		t.Fatalf("user_id 列应存在")
	}
	pk := readPKColumns(t, db)
	if pk["note_id"] != 1 || pk["user_id"] != 2 {
		t.Errorf("期望主键 (note_id, user_id), 实际 %v", pk)
	}
	rows := readReviewRows(t, db)
	if len(rows) != 2 {
		t.Fatalf("期望 2 行, 实际 %d", len(rows))
	}
	for _, r := range rows {
		if r.UserID != "local" {
			t.Errorf("user_id 期望 local, 实际 %q", r.UserID)
		}
	}
}

func TestMigrateReviewsUser_幂等重复执行无副作用(t *testing.T) {
	db := openMigrateTestDB(t)
	createLegacyReviewsSchema(t, db)
	insertLegacyNote(t, db, 1, "笔记")
	insertLegacyReview(t, db, 1, 2.5, 1, 1, "2024-03-01", sql.NullString{String: "2024-02-28", Valid: true}, 1)

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("首次迁移失败: %v", err)
	}
	first := readReviewRows(t, db)
	if len(first) != 1 {
		t.Fatalf("首次迁移后期望 1 行, 实际 %d", len(first))
	}

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("二次迁移失败: %v", err)
	}
	second := readReviewRows(t, db)
	if len(second) != 1 {
		t.Fatalf("二次迁移后期望 1 行, 实际 %d", len(second))
	}
	if first[0].UserID != second[0].UserID || first[0].EF != second[0].EF || first[0].DueDate != second[0].DueDate {
		t.Errorf("二次迁移改变了数据: first=%+v second=%+v", first[0], second[0])
	}
	pk := readPKColumns(t, db)
	if pk["note_id"] != 1 || pk["user_id"] != 2 {
		t.Errorf("期望主键 (note_id, user_id), 实际 %v", pk)
	}
}

func TestMigrateReviewsUser_新库已是复合主键时不做改动(t *testing.T) {
	db := openMigrateTestDB(t)
	if _, err := db.Exec(`CREATE TABLE notes (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		title TEXT NOT NULL,
		content TEXT NOT NULL DEFAULT ''
	)`); err != nil {
		t.Fatalf("建 notes 失败: %v", err)
	}
	if _, err := db.Exec(`CREATE TABLE reviews (
		note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
		user_id TEXT NOT NULL DEFAULT 'local',
		ef REAL NOT NULL DEFAULT 2.5,
		interval_days INTEGER NOT NULL DEFAULT 0,
		repetitions INTEGER NOT NULL DEFAULT 0,
		due_date TEXT NOT NULL,
		last_reviewed_at TEXT,
		reviewed_count INTEGER NOT NULL DEFAULT 0,
		PRIMARY KEY (note_id, user_id)
	)`); err != nil {
		t.Fatalf("建 reviews 失败: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO notes (id, title, content) VALUES (1, '笔记', '')`); err != nil {
		t.Fatalf("插入 notes 失败: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO reviews (note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count)
		VALUES (1, 'alice', 2.5, 1, 1, '2024-03-01', NULL, 1)`); err != nil {
		t.Fatalf("插入 reviews 失败: %v", err)
	}

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	rows := readReviewRows(t, db)
	if len(rows) != 1 {
		t.Fatalf("期望 1 行, 实际 %d", len(rows))
	}
	if rows[0].UserID != "alice" {
		t.Errorf("user_id 期望 alice, 实际 %q", rows[0].UserID)
	}
	if rows[0].DueDate != "2024-03-01" {
		t.Errorf("due_date 期望 2024-03-01, 实际 %q", rows[0].DueDate)
	}
}

func TestMigrateReviewsUser_多用户隔离(t *testing.T) {
	db := openMigrateTestDB(t)
	if _, err := db.Exec(`CREATE TABLE notes (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		title TEXT NOT NULL,
		content TEXT NOT NULL DEFAULT ''
	)`); err != nil {
		t.Fatalf("建 notes 失败: %v", err)
	}
	if _, err := db.Exec(`CREATE TABLE reviews (
		note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
		user_id TEXT NOT NULL DEFAULT 'local',
		ef REAL NOT NULL DEFAULT 2.5,
		interval_days INTEGER NOT NULL DEFAULT 0,
		repetitions INTEGER NOT NULL DEFAULT 0,
		due_date TEXT NOT NULL,
		last_reviewed_at TEXT,
		reviewed_count INTEGER NOT NULL DEFAULT 0,
		PRIMARY KEY (note_id, user_id)
	)`); err != nil {
		t.Fatalf("建 reviews 失败: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO notes (id, title, content) VALUES (1, '笔记', '')`); err != nil {
		t.Fatalf("插入 notes 失败: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO reviews (note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count)
		VALUES (1, 'alice', 2.5, 1, 1, '2024-03-01', NULL, 1),
		       (1, 'bob', 2.6, 2, 2, '2024-03-02', NULL, 2)`); err != nil {
		t.Fatalf("插入 reviews 失败: %v", err)
	}

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	rows := readReviewRows(t, db)
	if len(rows) != 2 {
		t.Fatalf("期望 2 行, 实际 %d", len(rows))
	}
	if rows[0].UserID != "alice" || rows[0].EF != 2.5 {
		t.Errorf("alice 行不符: %+v", rows[0])
	}
	if rows[1].UserID != "bob" || rows[1].EF != 2.6 {
		t.Errorf("bob 行不符: %+v", rows[1])
	}

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM reviews WHERE note_id = 1 AND user_id = 'alice'`).Scan(&count); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if count != 1 {
		t.Errorf("alice 查询期望 1, 实际 %d", count)
	}
}

func TestMigrateReviewsUser_复合主键允许同笔记不同用户(t *testing.T) {
	db := openMigrateTestDB(t)
	createLegacyReviewsSchema(t, db)
	insertLegacyNote(t, db, 1, "笔记")
	insertLegacyReview(t, db, 1, 2.5, 1, 1, "2024-03-01", sql.NullString{Valid: false}, 1)

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	if _, err := db.Exec(`INSERT INTO reviews (note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count)
		VALUES (1, 'alice', 2.5, 1, 1, '2024-03-01', NULL, 1)`); err != nil {
		t.Fatalf("插入 alice 行失败: %v", err)
	}

	rows := readReviewRows(t, db)
	if len(rows) != 2 {
		t.Fatalf("期望 2 行, 实际 %d", len(rows))
	}
	seen := map[string]bool{}
	for _, r := range rows {
		seen[r.UserID] = true
	}
	if !seen["local"] || !seen["alice"] {
		t.Errorf("期望同时存在 local 和 alice, 实际 %v", seen)
	}
}

func TestMigrateReviewsUser_空表迁移(t *testing.T) {
	db := openMigrateTestDB(t)
	createLegacyReviewsSchema(t, db)

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	if !hasColumnReview(t, db, "reviews", "user_id") {
		t.Fatalf("user_id 列应存在")
	}
	pk := readPKColumns(t, db)
	if pk["note_id"] != 1 || pk["user_id"] != 2 {
		t.Errorf("期望主键 (note_id, user_id), 实际 %v", pk)
	}
	rows := readReviewRows(t, db)
	if len(rows) != 0 {
		t.Errorf("空表迁移后期望 0 行, 实际 %d", len(rows))
	}
}

func TestMigrateReviewsUser_外键级联仍生效(t *testing.T) {
	db := openMigrateTestDB(t)
	createLegacyReviewsSchema(t, db)
	insertLegacyNote(t, db, 1, "笔记")
	insertLegacyReview(t, db, 1, 2.5, 1, 1, "2024-03-01", sql.NullString{Valid: false}, 1)

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	if _, err := db.Exec(`DELETE FROM notes WHERE id = 1`); err != nil {
		t.Fatalf("删除 note 失败: %v", err)
	}

	rows := readReviewRows(t, db)
	if len(rows) != 0 {
		t.Errorf("级联删除后期望 0 行, 实际 %d", len(rows))
	}
}

func TestMigrateReviewsUser_列默认值约束(t *testing.T) {
	db := openMigrateTestDB(t)
	createLegacyReviewsSchema(t, db)
	insertLegacyNote(t, db, 1, "笔记")

	if err := migrateReviewsUser(db); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	if _, err := db.Exec(`INSERT INTO reviews (note_id, due_date) VALUES (1, '2024-03-01')`); err != nil {
		t.Fatalf("插入失败: %v", err)
	}

	rows := readReviewRows(t, db)
	if len(rows) != 1 {
		t.Fatalf("期望 1 行, 实际 %d", len(rows))
	}
	if rows[0].UserID != "local" {
		t.Errorf("user_id 默认期望 local, 实际 %q", rows[0].UserID)
	}
	if rows[0].EF != 2.5 {
		t.Errorf("ef 默认期望 2.5, 实际 %v", rows[0].EF)
	}
	if rows[0].IntervalDays != 0 || rows[0].Repetitions != 0 || rows[0].ReviewedCount != 0 {
		t.Errorf("数值默认期望 0, 实际 %+v", rows[0])
	}
}
