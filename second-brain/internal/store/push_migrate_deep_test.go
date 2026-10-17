package store

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// openPushMigrateTestDB 打开一个临时目录下的 sqlite 库，调用方负责 Close。
func openPushMigrateTestDB(t *testing.T) *sql.DB {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "push_migrate_deep.db")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	t.Cleanup(func() {
		_ = db.Close()
	})
	return db
}

// legacyPushLogSchema 建出迁移前的旧 schema：push_log 无 user_id 列，
// 且存在旧的 (date, channel) 唯一索引 idx_push_log_date_channel。
func legacyPushLogSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	stmts := []string{
		`CREATE TABLE push_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			date TEXT NOT NULL,
			channel TEXT NOT NULL,
			payload TEXT NOT NULL DEFAULT ''
		)`,
		`CREATE UNIQUE INDEX idx_push_log_date_channel ON push_log(date, channel)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("exec %q: %v", s, err)
		}
	}
}

// newPushLogSchema 建出新 schema：push_log 已含 user_id 列，
// 并已存在 (date, channel, user_id) 唯一索引。
func newPushLogSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	stmts := []string{
		`CREATE TABLE push_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			date TEXT NOT NULL,
			channel TEXT NOT NULL,
			payload TEXT NOT NULL DEFAULT '',
			user_id TEXT NOT NULL DEFAULT 'local'
		)`,
		`CREATE UNIQUE INDEX idx_push_log_date_channel_user ON push_log(date, channel, user_id)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("exec %q: %v", s, err)
		}
	}
}

// hasColumn 用 PRAGMA table_info 判断某列是否存在。
func hasColumn(t *testing.T, db *sql.DB, table, column string) bool {
	t.Helper()
	rows, err := db.Query(`PRAGMA table_info(` + table + `)`)
	if err != nil {
		t.Fatalf("pragma table_info %s: %v", table, err)
	}
	defer rows.Close()
	found := false
	for rows.Next() {
		var (
			cid     int
			name    string
			ctype   string
			notnull int
			dflt    sql.NullString
			pk      int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			t.Fatalf("scan pragma row: %v", err)
		}
		if name == column {
			found = true
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("pragma rows err: %v", err)
	}
	return found
}

// indexColumns 读取某个索引的列名列表（按 seqno 排序）。
func indexColumns(t *testing.T, db *sql.DB, index string) []string {
	t.Helper()
	rows, err := db.Query(`PRAGMA index_info(` + index + `)`)
	if err != nil {
		t.Fatalf("pragma index_info %s: %v", index, err)
	}
	defer rows.Close()
	var cols []string
	for rows.Next() {
		var (
			seqno int
			cid   int
			name  string
		)
		if err := rows.Scan(&seqno, &cid, &name); err != nil {
			t.Fatalf("scan index_info: %v", err)
		}
		cols = append(cols, name)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("index_info rows err: %v", err)
	}
	return cols
}

// indexExists 判断索引是否存在于 sqlite_master。
func indexExists(t *testing.T, db *sql.DB, index string) bool {
	t.Helper()
	var name string
	err := db.QueryRow(
		`SELECT name FROM sqlite_master WHERE type='index' AND name=?`, index,
	).Scan(&name)
	if err == sql.ErrNoRows {
		return false
	}
	if err != nil {
		t.Fatalf("query sqlite_master for index %s: %v", index, err)
	}
	return name == index
}

// insertPushLog 插入一条 push_log 记录。
func insertPushLog(t *testing.T, db *sql.DB, date, channel, payload, userID string) {
	t.Helper()
	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		date, channel, payload, userID,
	)
	if err != nil {
		t.Fatalf("insert push_log(%s,%s,%s,%s): %v", date, channel, payload, userID, err)
	}
}

// countPushLog 统计 push_log 行数。
func countPushLog(t *testing.T, db *sql.DB) int {
	t.Helper()
	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM push_log`).Scan(&n); err != nil {
		t.Fatalf("count push_log: %v", err)
	}
	return n
}

// TestPushMigrateAddsUserIDColumnAndReplacesIndex 迁移核心行为：
// 旧表补 user_id 列，默认 'local'；旧索引换成三列唯一索引。
func TestPushMigrateAddsUserIDColumnAndReplacesIndex(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)

	insertPushLogNoUser(t, db, "2024-02-29", "wechat", "闰日旧数据")

	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	if !hasColumn(t, db, "push_log", "user_id") {
		t.Fatal("迁移后 push_log 仍缺少 user_id 列")
	}
	if indexExists(t, db, "idx_push_log_date_channel") {
		t.Fatal("旧的 idx_push_log_date_channel 索引应当已被删除")
	}
	if !indexExists(t, db, "idx_push_log_date_channel_user") {
		t.Fatal("新的 idx_push_log_date_channel_user 索引应当存在")
	}
	cols := indexColumns(t, db, "idx_push_log_date_channel_user")
	if len(cols) != 3 || cols[0] != "date" || cols[1] != "channel" || cols[2] != "user_id" {
		t.Fatalf("新索引列应为 [date channel user_id]，实际为 %v", cols)
	}

	var payload, userID string
	err := db.QueryRow(
		`SELECT payload, user_id FROM push_log WHERE date=? AND channel=?`,
		"2024-02-29", "wechat",
	).Scan(&payload, &userID)
	if err != nil {
		t.Fatalf("select migrated row: %v", err)
	}
	if payload != "闰日旧数据" {
		t.Fatalf("旧数据 payload 应保留，实际 %q", payload)
	}
	if userID != "local" {
		t.Fatalf("旧数据 user_id 默认值应为 local，实际 %q", userID)
	}
}

// insertPushLogNoUser 向旧 schema（无 user_id 列）插入一条记录。
func insertPushLogNoUser(t *testing.T, db *sql.DB, date, channel, payload string) {
	t.Helper()
	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload) VALUES (?, ?, ?)`,
		date, channel, payload,
	)
	if err != nil {
		t.Fatalf("insert legacy push_log(%s,%s): %v", date, channel, err)
	}
}

// TestPushMigrateIsIdempotent 迁移幂等：连续调用两次，结果与一次相同。
func TestPushMigrateIsIdempotent(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	insertPushLogNoUser(t, db, "2023-12-31", "sms", "跨年旧数据")

	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("first migratePushLogUser: %v", err)
	}
	colsAfterFirst := indexColumns(t, db, "idx_push_log_date_channel_user")

	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("second migratePushLogUser: %v", err)
	}
	colsAfterSecond := indexColumns(t, db, "idx_push_log_date_channel_user")

	if len(colsAfterFirst) != len(colsAfterSecond) {
		t.Fatalf("二次迁移改变了索引列数：%v -> %v", colsAfterFirst, colsAfterSecond)
	}
	for i := range colsAfterFirst {
		if colsAfterFirst[i] != colsAfterSecond[i] {
			t.Fatalf("二次迁移改变了索引列：%v -> %v", colsAfterFirst, colsAfterSecond)
		}
	}
	if got := countPushLog(t, db); got != 1 {
		t.Fatalf("幂等迁移后行数应为 1，实际 %d", got)
	}
	var userID string
	if err := db.QueryRow(`SELECT user_id FROM push_log`).Scan(&userID); err != nil {
		t.Fatalf("select user_id: %v", err)
	}
	if userID != "local" {
		t.Fatalf("二次迁移后 user_id 仍应为 local，实际 %q", userID)
	}
}

// TestPushMigrateNewSchemaNoop 新库（已建新 schema）调用迁移不应做任何改动。
func TestPushMigrateNewSchemaNoop(t *testing.T) {
	db := openPushMigrateTestDB(t)
	newPushLogSchema(t, db)
	insertPushLog(t, db, "2024-01-01", "wechat", "新库数据", "alice")

	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser on new schema: %v", err)
	}

	if !hasColumn(t, db, "push_log", "user_id") {
		t.Fatal("新库迁移后应仍有 user_id 列")
	}
	if indexExists(t, db, "idx_push_log_date_channel") {
		t.Fatal("新库不应出现旧索引 idx_push_log_date_channel")
	}
	cols := indexColumns(t, db, "idx_push_log_date_channel_user")
	if len(cols) != 3 || cols[2] != "user_id" {
		t.Fatalf("新库索引列应为 [date channel user_id]，实际 %v", cols)
	}
	var userID string
	if err := db.QueryRow(`SELECT user_id FROM push_log`).Scan(&userID); err != nil {
		t.Fatalf("select user_id: %v", err)
	}
	if userID != "alice" {
		t.Fatalf("新库已有数据不应被改动，user_id 应为 alice，实际 %q", userID)
	}
}

// TestPushMigrateMultiUserUniqueness 迁移后 (date, channel, user_id) 唯一：
// 同一天同一渠道不同用户可共存，同用户重复插入被拒。
func TestPushMigrateMultiUserUniqueness(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	insertPushLog(t, db, "2024-03-01", "wechat", "alice 的推送", "alice")
	insertPushLog(t, db, "2024-03-01", "wechat", "bob 的推送", "bob")

	if got := countPushLog(t, db); got != 2 {
		t.Fatalf("不同用户同日同渠道应可共存，行数应为 2，实际 %d", got)
	}

	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		"2024-03-01", "wechat", "alice 重复", "alice",
	)
	if err == nil {
		t.Fatal("同一用户同日同渠道重复插入应被唯一索引拒绝")
	}

	insertPushLog(t, db, "2024-03-02", "wechat", "alice 次日推送", "alice")
	if got := countPushLog(t, db); got != 3 {
		t.Fatalf("换一天后应可插入，行数应为 3，实际 %d", got)
	}
}

// TestPushMigrateCrossDayBoundary 跨天边界：23:59:59 与次日 00:00:00
// 视为不同 date，可共存。
func TestPushMigrateCrossDayBoundary(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	insertPushLog(t, db, "2024-06-30 23:59:59", "wechat", "跨天前", "alice")
	insertPushLog(t, db, "2024-07-01 00:00:00", "wechat", "跨天后", "alice")

	if got := countPushLog(t, db); got != 2 {
		t.Fatalf("跨天两条记录应共存，行数应为 2，实际 %d", got)
	}

	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		"2024-06-30 23:59:59", "wechat", "重复的跨天前", "alice",
	)
	if err == nil {
		t.Fatal("同一天同一时刻重复插入应被唯一索引拒绝")
	}
}

// TestPushMigrateLeapDayBoundary 闰日边界：2024-02-29 与 2024-03-01
// 是不同日期，同用户可各存一条。
func TestPushMigrateLeapDayBoundary(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	insertPushLog(t, db, "2024-02-29", "wechat", "闰日推送", "alice")
	insertPushLog(t, db, "2024-03-01", "wechat", "闰日后一天推送", "alice")

	if got := countPushLog(t, db); got != 2 {
		t.Fatalf("闰日与次日应共存，行数应为 2，实际 %d", got)
	}

	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		"2024-02-29", "wechat", "闰日重复", "alice",
	)
	if err == nil {
		t.Fatal("闰日同用户同渠道重复插入应被拒绝")
	}

	var payload string
	if err := db.QueryRow(
		`SELECT payload FROM push_log WHERE date=? AND channel=? AND user_id=?`,
		"2024-02-29", "wechat", "alice",
	).Scan(&payload); err != nil {
		t.Fatalf("select leap day row: %v", err)
	}
	if payload != "闰日推送" {
		t.Fatalf("闰日原始记录应保留，实际 %q", payload)
	}
}

// TestPushMigrateTimeZoneOffsetStrings 时区边界：带不同时区偏移的字符串
// 在 sqlite 中按文本比较，属于不同 date。
func TestPushMigrateTimeZoneOffsetStrings(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	insertPushLog(t, db, "2024-05-01T08:00:00+08:00", "wechat", "东八区", "alice")
	insertPushLog(t, db, "2024-05-01T00:00:00Z", "wechat", "UTC", "alice")

	if got := countPushLog(t, db); got != 2 {
		t.Fatalf("不同时区偏移的字符串应视为不同 date，行数应为 2，实际 %d", got)
	}

	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		"2024-05-01T08:00:00+08:00", "wechat", "东八区重复", "alice",
	)
	if err == nil {
		t.Fatal("同一时区字符串重复插入应被拒绝")
	}

	var payload string
	if err := db.QueryRow(
		`SELECT payload FROM push_log WHERE date=? AND channel=? AND user_id=?`,
		"2024-05-01T00:00:00Z", "wechat", "alice",
	).Scan(&payload); err != nil {
		t.Fatalf("select UTC row: %v", err)
	}
	if payload != "UTC" {
		t.Fatalf("UTC 记录应保留，实际 %q", payload)
	}
}

// TestPushMigrateMultiUserIsolation 多用户隔离：alice 的记录 bob 查不到，
// 计数也按用户隔离。
func TestPushMigrateMultiUserIsolation(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	insertPushLog(t, db, "2024-08-01", "wechat", "alice 私密", "alice")
	insertPushLog(t, db, "2024-08-01", "wechat", "bob 私密", "bob")
	insertPushLog(t, db, "2024-08-02", "wechat", "alice 次日", "alice")

	var aliceCount, bobCount int
	if err := db.QueryRow(`SELECT COUNT(*) FROM push_log WHERE user_id=?`, "alice").Scan(&aliceCount); err != nil {
		t.Fatalf("count alice: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM push_log WHERE user_id=?`, "bob").Scan(&bobCount); err != nil {
		t.Fatalf("count bob: %v", err)
	}
	if aliceCount != 2 {
		t.Fatalf("alice 记录数应为 2，实际 %d", aliceCount)
	}
	if bobCount != 1 {
		t.Fatalf("bob 记录数应为 1，实际 %d", bobCount)
	}

	var payload string
	err := db.QueryRow(
		`SELECT payload FROM push_log WHERE date=? AND channel=? AND user_id=?`,
		"2024-08-01", "wechat", "alice",
	).Scan(&payload)
	if err != nil {
		t.Fatalf("select alice row: %v", err)
	}
	if payload != "alice 私密" {
		t.Fatalf("alice 应查到自己的记录，实际 %q", payload)
	}

	var leaked string
	err = db.QueryRow(
		`SELECT payload FROM push_log WHERE date=? AND channel=? AND user_id=?`,
		"2024-08-01", "wechat", "bob",
	).Scan(&leaked)
	if err != nil {
		t.Fatalf("select bob row: %v", err)
	}
	if leaked != "bob 私密" {
		t.Fatalf("bob 应查到自己的记录，实际 %q", leaked)
	}
}

// TestPushMigrateUserIDDefaultOnLegacyInsert 迁移后向旧列插入数据，
// user_id 自动落 'local'，且与显式 local 冲突。
func TestPushMigrateUserIDDefaultOnLegacyInsert(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload) VALUES (?, ?, ?)`,
		"2024-09-01", "sms", "未指定用户",
	)
	if err != nil {
		t.Fatalf("未指定 user_id 的插入应成功并落默认值: %v", err)
	}

	var userID string
	if err := db.QueryRow(
		`SELECT user_id FROM push_log WHERE date=? AND channel=?`,
		"2024-09-01", "sms",
	).Scan(&userID); err != nil {
		t.Fatalf("select user_id: %v", err)
	}
	if userID != "local" {
		t.Fatalf("未指定 user_id 时应落 local，实际 %q", userID)
	}

	_, err = db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		"2024-09-01", "sms", "显式 local 重复", "local",
	)
	if err == nil {
		t.Fatal("默认 local 与显式 local 应视为同一用户，重复插入应被拒绝")
	}
}

// TestPushMigrateChannelIsolation 渠道隔离：同一天同一用户不同渠道可共存。
func TestPushMigrateChannelIsolation(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)
	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	insertPushLog(t, db, "2024-10-01", "wechat", "微信推送", "alice")
	insertPushLog(t, db, "2024-10-01", "sms", "短信推送", "alice")
	insertPushLog(t, db, "2024-10-01", "email", "邮件推送", "alice")

	if got := countPushLog(t, db); got != 3 {
		t.Fatalf("同用户同日不同渠道应共存，行数应为 3，实际 %d", got)
	}

	_, err := db.Exec(
		`INSERT INTO push_log(date, channel, payload, user_id) VALUES (?, ?, ?, ?)`,
		"2024-10-01", "sms", "短信重复", "alice",
	)
	if err == nil {
		t.Fatal("同用户同日同渠道重复插入应被拒绝")
	}

	var payload string
	if err := db.QueryRow(
		`SELECT payload FROM push_log WHERE date=? AND channel=? AND user_id=?`,
		"2024-10-01", "email", "alice",
	).Scan(&payload); err != nil {
		t.Fatalf("select email row: %v", err)
	}
	if payload != "邮件推送" {
		t.Fatalf("邮件渠道记录应保留，实际 %q", payload)
	}
}

// TestPushMigrateEmptyLegacyTable 空旧表迁移：补列、换索引后仍为空，
// 且能正常写入。
func TestPushMigrateEmptyLegacyTable(t *testing.T) {
	db := openPushMigrateTestDB(t)
	legacyPushLogSchema(t, db)

	if err := migratePushLogUser(db); err != nil {
		t.Fatalf("migratePushLogUser: %v", err)
	}

	if got := countPushLog(t, db); got != 0 {
		t.Fatalf("空旧表迁移后行数应为 0，实际 %d", got)
	}
	if !hasColumn(t, db, "push_log", "user_id") {
		t.Fatal("空旧表迁移后应补出 user_id 列")
	}
	if !indexExists(t, db, "idx_push_log_date_channel_user") {
		t.Fatal("空旧表迁移后应存在新唯一索引")
	}

	insertPushLog(t, db, "2024-11-11", "wechat", "双十一推送", "alice")
	insertPushLog(t, db, "2024-11-11", "wechat", "双十一推送", "bob")
	if got := countPushLog(t, db); got != 2 {
		t.Fatalf("空表迁移后可正常写入两条，行数应为 2，实际 %d", got)
	}
}
