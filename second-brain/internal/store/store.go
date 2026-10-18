package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
	"github.com/Wanfeng1028/muse/second-brain/internal/review"
	_ "modernc.org/sqlite"
)

// ErrNotFound 表示笔记不存在。
var ErrNotFound = errors.New("note not found")

// Note 数据模型。
type Note struct {
	ID        int64    `json:"id"`
	Title     string   `json:"title"`
	Body      string   `json:"body"`
	Tags      []string `json:"tags"`
	Pinned    bool     `json:"pinned"`
	CreatedAt string   `json:"createdAt"`
	UpdatedAt string   `json:"updatedAt"`
}

// TagCount 标签及其笔记数量。
type TagCount struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

// Stats 统计信息。
type Stats struct {
	Notes int `json:"notes"`
	Tags  int `json:"tags"`
	Links int `json:"links"`
	Words int `json:"words"`
}

// GraphNode 图节点。
type GraphNode struct {
	ID    int64    `json:"id"`
	Title string   `json:"title"`
	Tags  []string `json:"tags"`
}

// GraphEdge 图边。
type GraphEdge struct {
	Source int64 `json:"source"`
	Target int64 `json:"target"`
}

// GraphData 图数据。
type GraphData struct {
	Nodes []GraphNode `json:"nodes"`
	Edges []GraphEdge `json:"edges"`
}

// Store 数据库封装。
type Store struct {
	db *sql.DB
	// attachDir 附件落盘根目录。
	attachDir string
}

// 双链正则，例如 [[标题]]
var wikiRe = regexp.MustCompile(`\[\[([^\]]+)\]\]`)

// Open 打开数据库并初始化表结构。
func Open(path string) (*Store, error) {
	memory := path == ":memory:"
	if !memory {
		dir := filepath.Dir(path)
		if dir != "" && dir != "." {
			if err := os.MkdirAll(dir, 0o755); err != nil {
				return nil, err
			}
		}
	}
	// 通过 DSN 的 _pragma 参数设置 busy_timeout：该 PRAGMA 会随连接池中每个新连接自动执行，
	// 而单次 db.Exec 只影响当时拿到的那一个连接，无法覆盖池中其它连接。
	dsn := path + "?_pragma=busy_timeout(5000)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	if !memory {
		if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
			db.Close()
			return nil, err
		}
	}
	if _, err := db.Exec("PRAGMA foreign_keys=ON"); err != nil {
		db.Close()
		return nil, err
	}
	if err := createSchema(db); err != nil {
		db.Close()
		return nil, err
	}

	if err := migrateReviewsUser(db); err != nil {
		db.Close()
		return nil, err
	}

	if err := migratePushLogUser(db); err != nil {
		db.Close()
		return nil, err
	}

	attachDir := filepath.Join(filepath.Dir(path), "attachments")
	return &Store{db: db, attachDir: attachDir}, nil
}

// createSchema 建表。
func createSchema(db *sql.DB) error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS notes (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			title TEXT NOT NULL,
			body TEXT NOT NULL DEFAULT '',
			pinned INTEGER NOT NULL DEFAULT 0,
			created_at TEXT NOT NULL,
			updated_at TEXT NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS tags (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL UNIQUE
		)`,
		`CREATE TABLE IF NOT EXISTS note_tags (
			note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
			tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
			PRIMARY KEY(note_id, tag_id)
		)`,
		`CREATE TABLE IF NOT EXISTS links (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			source_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
			target_title TEXT NOT NULL,
			target_id INTEGER REFERENCES notes(id) ON DELETE SET NULL
		)`,
		`CREATE TABLE IF NOT EXISTS reviews (
			note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
			user_id TEXT NOT NULL DEFAULT 'local',
			ef REAL NOT NULL DEFAULT 2.5,
			interval_days INTEGER NOT NULL DEFAULT 0,
			repetitions INTEGER NOT NULL DEFAULT 0,
			due_date TEXT NOT NULL,
			last_reviewed_at TEXT,
			reviewed_count INTEGER NOT NULL DEFAULT 0,
			PRIMARY KEY (note_id, user_id)
		)`,
		`CREATE TABLE IF NOT EXISTS attachments (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
			filename TEXT NOT NULL,
			stored_name TEXT NOT NULL,
			mime TEXT NOT NULL,
			size INTEGER NOT NULL,
			sha256 TEXT NOT NULL,
			created_at TEXT NOT NULL
		)`,
		`CREATE INDEX IF NOT EXISTS idx_attachments_note_id ON attachments(note_id)`,
		`CREATE TABLE IF NOT EXISTS push_settings (
			key TEXT PRIMARY KEY,
			value TEXT NOT NULL,
			updated_at TEXT NOT NULL
		)`,

		`CREATE TABLE IF NOT EXISTS push_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			date TEXT NOT NULL,
			channel TEXT NOT NULL,
			user_id TEXT NOT NULL DEFAULT 'local',
			status TEXT NOT NULL,
			detail TEXT NOT NULL DEFAULT '',
			created_at TEXT NOT NULL
		)`,
		// 注意：push_log 的唯一索引由 migratePushLogUser 统一创建（幂等）。
		// 不能在这里直接建 (date, channel, user_id) 索引：老库在 migration 之前
		// 还没有 user_id 列，会报 no such column。
		`CREATE TABLE IF NOT EXISTS push_subscriptions (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id TEXT NOT NULL DEFAULT 'local',
			endpoint TEXT NOT NULL,
			p256dh TEXT NOT NULL,
			auth TEXT NOT NULL,
			created_at TEXT NOT NULL,
			UNIQUE(endpoint)
		)`,
		// endpoint 全局唯一：同一浏览器订阅被其他用户重新认领时归属新用户。
		// 按 user_id 查询的普通索引，支撑 List/Count。
		`CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			return err
		}
	}
	return nil
}

// Close 关闭数据库。
func (s *Store) Close() error {
	if s.db == nil {
		return nil
	}
	return s.db.Close()
}

// nowRFC3339 当前 UTC RFC3339 时间。
func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// normalizeTags 归一化标签：trim、去空、转小写、去重保序。
func normalizeTags(tags []string) []string {
	seen := make(map[string]bool, len(tags))
	out := make([]string, 0, len(tags))
	for _, t := range tags {
		t = strings.ToLower(strings.TrimSpace(t))
		if t == "" {
			continue
		}
		if seen[t] {
			continue
		}
		seen[t] = true
		out = append(out, t)
	}
	return out
}

// CreateNote 创建笔记（复习行归属默认用户）。
func (s *Store) CreateNote(n Note) (Note, error) {
	return s.CreateNoteFor(context.Background(), n, DefaultUser)
}

// CreateNoteFor 创建笔记，复习行归属指定用户。ctx 用于携带 request_id 做全链路日志。
func (s *Store) CreateNoteFor(ctx context.Context, n Note, user string) (Note, error) {
	user = NormalizeUser(user)
	now := nowRFC3339()
	n.CreatedAt = now
	n.UpdatedAt = now
	n.Tags = normalizeTags(n.Tags)

	pinned := 0
	if n.Pinned {
		pinned = 1
	}

	tx, err := s.db.Begin()
	if err != nil {
		return Note{}, err
	}
	defer tx.Rollback()

	res, err := tx.Exec(
		`INSERT INTO notes(title, body, pinned, created_at, updated_at) VALUES(?,?,?,?,?)`,
		n.Title, n.Body, pinned, n.CreatedAt, n.UpdatedAt,
	)
	if err != nil {
		return Note{}, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return Note{}, err
	}
	n.ID = id

	if err := syncTags(tx, id, n.Tags); err != nil {
		return Note{}, err
	}
	if err := syncLinks(tx, id, n.Body); err != nil {
		return Note{}, err
	}
	// 回填：其他笔记的 links 可能指向本笔记标题。
	if err := resolveBacklinks(tx, n.Title, id); err != nil {
		return Note{}, err
	}
	st := review.InitialState(time.Now())
	if _, err := tx.Exec(`INSERT INTO reviews(note_id, user_id, ef, interval_days, repetitions, due_date) VALUES(?,?,?,?,?,?)`,
		id, user, st.EF, st.IntervalDays, st.Repetitions, st.DueDate); err != nil {
		return Note{}, err
	}
	if err := tx.Commit(); err != nil {
		return Note{}, err
	}
	logpkg.RequestLogger(ctx).Info("store.note_created", "note_id", id, "user", user)
	return n, nil
}

// GetNote 获取笔记。
func (s *Store) GetNote(id int64) (Note, error) {
	row := s.db.QueryRow(
		`SELECT id, title, body, pinned, created_at, updated_at FROM notes WHERE id=?`, id,
	)
	n, err := scanNote(row)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Note{}, ErrNotFound
		}
		return Note{}, err
	}
	tags, err := s.tagsForNote(id)
	if err != nil {
		return Note{}, err
	}
	n.Tags = tags
	return n, nil
}

// ListNotes 列出笔记，可按标签过滤。
func (s *Store) ListNotes(tag string, limit, offset int) ([]Note, error) {
	if limit <= 0 {
		limit = 100
	}
	if offset < 0 {
		offset = 0
	}
	tag = strings.ToLower(strings.TrimSpace(tag))

	var (
		rows *sql.Rows
		err  error
	)
	if tag == "" {
		rows, err = s.db.Query(
			`SELECT id, title, body, pinned, created_at, updated_at FROM notes
			 ORDER BY pinned DESC, updated_at DESC LIMIT ? OFFSET ?`,
			limit, offset,
		)
	} else {
		rows, err = s.db.Query(
			`SELECT n.id, n.title, n.body, n.pinned, n.created_at, n.updated_at
			 FROM notes n
			 JOIN note_tags nt ON nt.note_id = n.id
			 JOIN tags t ON t.id = nt.tag_id
			 WHERE t.name = ?
			 ORDER BY n.pinned DESC, n.updated_at DESC LIMIT ? OFFSET ?`,
			tag, limit, offset,
		)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	notes := []Note{}
	ids := []int64{}
	for rows.Next() {
		n, err := scanNote(rows)
		if err != nil {
			return nil, err
		}
		notes = append(notes, n)
		ids = append(ids, n.ID)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	tagMap, err := s.tagsForNotes(ids)
	if err != nil {
		return nil, err
	}
	for i := range notes {
		if t, ok := tagMap[notes[i].ID]; ok {
			notes[i].Tags = t
		} else {
			notes[i].Tags = []string{}
		}
	}
	return notes, nil
}

// UpdateNote 更新笔记。
func (s *Store) UpdateNote(n Note) (Note, error) {
	existing, err := s.GetNote(n.ID)
	if err != nil {
		return Note{}, err
	}
	n.Tags = normalizeTags(n.Tags)
	n.UpdatedAt = nowRFC3339()
	if n.CreatedAt == "" {
		n.CreatedAt = existing.CreatedAt
	}

	pinned := 0
	if n.Pinned {
		pinned = 1
	}

	tx, err := s.db.Begin()
	if err != nil {
		return Note{}, err
	}
	defer tx.Rollback()

	res, err := tx.Exec(
		`UPDATE notes SET title=?, body=?, pinned=?, updated_at=? WHERE id=?`,
		n.Title, n.Body, pinned, n.UpdatedAt, n.ID,
	)
	if err != nil {
		return Note{}, err
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return Note{}, err
	}
	if affected == 0 {
		return Note{}, ErrNotFound
	}

	if err := syncTags(tx, n.ID, n.Tags); err != nil {
		return Note{}, err
	}
	if err := syncLinks(tx, n.ID, n.Body); err != nil {
		return Note{}, err
	}
	// 若标题发生变化，回填指向新标题的 links。
	if err := resolveBacklinks(tx, n.Title, n.ID); err != nil {
		return Note{}, err
	}
	if err := tx.Commit(); err != nil {
		return Note{}, err
	}
	return s.GetNote(n.ID)
}

// DeleteNote 删除笔记，并清理其附件目录。
func (s *Store) DeleteNote(id int64) error {
	if _, err := s.ListAttachments(id); err != nil {
		return err
	}
	res, err := s.db.Exec(`DELETE FROM notes WHERE id=?`, id)
	if err != nil {
		return err
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if affected == 0 {
		return ErrNotFound
	}
	dir := filepath.Join(s.attachDir, strconv.FormatInt(id, 10))
	if err := os.RemoveAll(dir); err != nil {
		return err
	}
	return nil
}

// SearchNotes 按 title/body/tags 多关键词 AND 搜索。
func (s *Store) SearchNotes(q string) ([]Note, error) {
	fields := strings.Fields(q)
	clauses := []string{}
	args := []interface{}{}
	for _, f := range fields {
		f = strings.TrimSpace(f)
		if f == "" {
			continue
		}
		like := "%" + f + "%"
		clauses = append(clauses, "(title LIKE ? OR body LIKE ? OR EXISTS (SELECT 1 FROM note_tags nt JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = notes.id AND t.name LIKE ?))")
		args = append(args, like, like, like)
	}

	query := `SELECT id, title, body, pinned, created_at, updated_at FROM notes`
	if len(clauses) > 0 {
		query += " WHERE " + strings.Join(clauses, " AND ")
	}
	query += " ORDER BY pinned DESC, updated_at DESC"

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	notes := []Note{}
	ids := []int64{}
	for rows.Next() {
		n, err := scanNote(rows)
		if err != nil {
			return nil, err
		}
		notes = append(notes, n)
		ids = append(ids, n.ID)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	tagMap, err := s.tagsForNotes(ids)
	if err != nil {
		return nil, err
	}
	for i := range notes {
		if t, ok := tagMap[notes[i].ID]; ok {
			notes[i].Tags = t
		} else {
			notes[i].Tags = []string{}
		}
	}
	return notes, nil
}

// ListTags 列出所有标签及数量。
func (s *Store) ListTags() ([]TagCount, error) {
	rows, err := s.db.Query(
		`SELECT t.name, COUNT(nt.note_id) FROM tags t
		 LEFT JOIN note_tags nt ON nt.tag_id = t.id
		 GROUP BY t.id, t.name
		 ORDER BY COUNT(nt.note_id) DESC, t.name ASC`,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []TagCount{}
	for rows.Next() {
		var tc TagCount
		if err := rows.Scan(&tc.Name, &tc.Count); err != nil {
			return nil, err
		}
		out = append(out, tc)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// Stats 统计信息。
func (s *Store) Stats() (Stats, error) {
	var st Stats
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM notes`).Scan(&st.Notes); err != nil {
		return st, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM tags`).Scan(&st.Tags); err != nil {
		return st, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM links`).Scan(&st.Links); err != nil {
		return st, err
	}
	rows, err := s.db.Query(`SELECT body FROM notes`)
	if err != nil {
		return st, err
	}
	defer rows.Close()
	words := 0
	for rows.Next() {
		var body string
		if err := rows.Scan(&body); err != nil {
			return st, err
		}
		words += len(strings.Fields(body))
	}
	if err := rows.Err(); err != nil {
		return st, err
	}
	st.Words = words
	return st, nil
}

// Graph 返回图数据（节点和已解析的边）。
func (s *Store) Graph() (GraphData, error) {
	gd := GraphData{Nodes: []GraphNode{}, Edges: []GraphEdge{}}

	rows, err := s.db.Query(`SELECT id, title FROM notes ORDER BY id ASC`)
	if err != nil {
		return gd, err
	}
	defer rows.Close()
	ids := []int64{}
	titleToID := map[string]int64{}
	for rows.Next() {
		var n GraphNode
		if err := rows.Scan(&n.ID, &n.Title); err != nil {
			return gd, err
		}
		n.Tags = []string{}
		gd.Nodes = append(gd.Nodes, n)
		ids = append(ids, n.ID)
		titleToID[strings.ToLower(n.Title)] = n.ID
	}
	if err := rows.Err(); err != nil {
		return gd, err
	}
	tagMap, err := s.tagsForNotes(ids)
	if err != nil {
		return gd, err
	}
	for i := range gd.Nodes {
		if t, ok := tagMap[gd.Nodes[i].ID]; ok {
			gd.Nodes[i].Tags = t
		}
	}

	edgeRows, err := s.db.Query(
		`SELECT source_id, target_id, target_title FROM links`,
	)
	if err != nil {
		return gd, err
	}
	defer edgeRows.Close()
	seen := map[[2]int64]bool{}
	for edgeRows.Next() {
		var (
			source      int64
			targetNull  sql.NullInt64
			targetTitle string
		)
		if err := edgeRows.Scan(&source, &targetNull, &targetTitle); err != nil {
			return gd, err
		}
		var target int64
		if targetNull.Valid {
			target = targetNull.Int64
		} else {
			id, ok := titleToID[strings.ToLower(targetTitle)]
			if !ok {
				continue
			}
			target = id
		}
		if target == 0 || target == source {
			continue
		}
		key := [2]int64{source, target}
		if seen[key] {
			continue
		}
		seen[key] = true
		gd.Edges = append(gd.Edges, GraphEdge{Source: source, Target: target})
	}
	if err := edgeRows.Err(); err != nil {
		return gd, err
	}
	return gd, nil
}

// ---------- 内部 helper ----------

// scanner 兼容 *sql.Row 和 *sql.Rows。
type scanner interface {
	Scan(dest ...interface{}) error
}

// scanNote 扫描一行笔记基础字段（不含 tags）。
func scanNote(sc scanner) (Note, error) {
	var (
		n      Note
		pinned int
	)
	if err := sc.Scan(&n.ID, &n.Title, &n.Body, &pinned, &n.CreatedAt, &n.UpdatedAt); err != nil {
		return Note{}, err
	}
	n.Pinned = pinned != 0
	n.Tags = []string{}
	return n, nil
}

// tagsForNote 查询单个笔记的标签。
func (s *Store) tagsForNote(id int64) ([]string, error) {
	rows, err := s.db.Query(
		`SELECT t.name FROM tags t
		 JOIN note_tags nt ON nt.tag_id = t.id
		 WHERE nt.note_id = ?
		 ORDER BY t.name ASC`,
		id,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []string{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		out = append(out, name)
	}
	return out, rows.Err()
}

// tagsForNotes 批量查询多个笔记的标签。
func (s *Store) tagsForNotes(ids []int64) (map[int64][]string, error) {
	result := make(map[int64][]string, len(ids))
	if len(ids) == 0 {
		return result, nil
	}
	placeholders := make([]string, len(ids))
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		placeholders[i] = "?"
		args[i] = id
	}
	query := fmt.Sprintf(
		`SELECT nt.note_id, t.name FROM note_tags nt
		 JOIN tags t ON t.id = nt.tag_id
		 WHERE nt.note_id IN (%s)
		 ORDER BY t.name ASC`,
		strings.Join(placeholders, ","),
	)
	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var (
			nid  int64
			name string
		)
		if err := rows.Scan(&nid, &name); err != nil {
			return nil, err
		}
		result[nid] = append(result[nid], name)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return result, nil
}

// syncTags 同步笔记的标签关联。
func syncTags(tx *sql.Tx, noteID int64, tags []string) error {
	if _, err := tx.Exec(`DELETE FROM note_tags WHERE note_id=?`, noteID); err != nil {
		return err
	}
	for _, name := range tags {
		if _, err := tx.Exec(`INSERT OR IGNORE INTO tags(name) VALUES(?)`, name); err != nil {
			return err
		}
		var tagID int64
		if err := tx.QueryRow(`SELECT id FROM tags WHERE name=?`, name).Scan(&tagID); err != nil {
			return err
		}
		if _, err := tx.Exec(
			`INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES(?,?)`,
			noteID, tagID,
		); err != nil {
			return err
		}
	}
	return nil
}

// syncLinks 提取 body 中的双链并同步 links 表。
func syncLinks(tx *sql.Tx, noteID int64, body string) error {
	if _, err := tx.Exec(`DELETE FROM links WHERE source_id=?`, noteID); err != nil {
		return err
	}
	matches := wikiRe.FindAllStringSubmatch(body, -1)
	seen := map[string]bool{}
	for _, m := range matches {
		if len(m) < 2 {
			continue
		}
		title := strings.TrimSpace(m[1])
		if title == "" || seen[title] {
			continue
		}
		seen[title] = true
		targetID, err := findNoteIDByTitle(tx, title)
		if err != nil {
			return err
		}
		if targetID.Valid {
			if _, err := tx.Exec(
				`INSERT INTO links(source_id, target_title, target_id) VALUES(?,?,?)`,
				noteID, title, targetID.Int64,
			); err != nil {
				return err
			}
		} else {
			if _, err := tx.Exec(
				`INSERT INTO links(source_id, target_title, target_id) VALUES(?,?,NULL)`,
				noteID, title,
			); err != nil {
				return err
			}
		}
	}
	return nil
}

// findNoteIDByTitle 按标题查笔记 id（忽略大小写）。
func findNoteIDByTitle(tx *sql.Tx, title string) (sql.NullInt64, error) {
	var id sql.NullInt64
	err := tx.QueryRow(
		`SELECT id FROM notes WHERE LOWER(title)=LOWER(?) ORDER BY id ASC LIMIT 1`,
		title,
	).Scan(&id)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return sql.NullInt64{}, nil
		}
		return sql.NullInt64{}, err
	}
	return id, nil
}

// resolveBacklinks 将指向 title 的所有未解析 links 的 target_id 回填为 noteID。
func resolveBacklinks(tx *sql.Tx, title string, noteID int64) error {
	title = strings.TrimSpace(title)
	if title == "" {
		return nil
	}
	_, err := tx.Exec(
		`UPDATE links SET target_id=? WHERE target_id IS NULL AND LOWER(target_title)=LOWER(?)`,
		noteID, title,
	)
	return err
}

// 复习相关函数见 review.go。
