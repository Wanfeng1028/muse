package store

import (
	"context"
	"database/sql"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/review"
)

func TestNormalizeUser(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"", "local"},
		{"  Alice ", "alice"},
		{"BOB", "bob"},
		{strings.Repeat("x", 70), strings.Repeat("x", 64)},
	}
	for _, c := range cases {
		if got := NormalizeUser(c.in); got != c.want {
			t.Errorf("NormalizeUser(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestCreateNoteForUser(t *testing.T) {
	s := newTestStore(t)

	n, err := s.CreateNoteFor(context.Background(), Note{Title: "alice note", Body: "hello"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}

	st, err := s.GetReviewState(n.ID, "alice")
	if err != nil {
		t.Fatalf("GetReviewState(alice): %v", err)
	}
	if st.EF != 2.5 {
		t.Errorf("alice EF = %v, want 2.5", st.EF)
	}

	if _, err := s.GetReviewState(n.ID, "bob"); err != ErrNotFound {
		t.Errorf("GetReviewState(bob) err = %v, want ErrNotFound", err)
	}
	if _, err := s.GetReviewState(n.ID, "local"); err != ErrNotFound {
		t.Errorf("GetReviewState(local) err = %v, want ErrNotFound", err)
	}
}

func TestReviewIsolationQueue(t *testing.T) {
	s := newTestStore(t)
	today := time.Now()

	n, err := s.CreateNoteFor(context.Background(), Note{Title: "alice due", Body: "x"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	if _, err := s.RecordReview(context.Background(), n.ID, 4, today, "alice"); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}
	if _, err := s.db.Exec("UPDATE reviews SET due_date='2000-01-01' WHERE note_id=? AND user_id='alice'", n.ID); err != nil {
		t.Fatalf("force due_date: %v", err)
	}

	alice, err := s.ListDueReviews(today, 10, "alice")
	if err != nil {
		t.Fatalf("ListDueReviews(alice): %v", err)
	}
	if len(alice) != 1 {
		t.Errorf("alice due len = %d, want 1", len(alice))
	}

	bob, err := s.ListDueReviews(today, 10, "bob")
	if err != nil {
		t.Fatalf("ListDueReviews(bob): %v", err)
	}
	if len(bob) != 0 {
		t.Errorf("bob due len = %d, want 0", len(bob))
	}
}

func TestReviewIsolationGrade(t *testing.T) {
	s := newTestStore(t)
	today := time.Now()

	n, err := s.CreateNoteFor(context.Background(), Note{Title: "shared note", Body: "x"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}

	aliceState, err := s.RecordReview(context.Background(), n.ID, 5, today, "alice")
	if err != nil {
		t.Fatalf("RecordReview(alice): %v", err)
	}
	bobState, err := s.RecordReview(context.Background(), n.ID, 0, today, "bob")
	if err != nil {
		t.Fatalf("RecordReview(bob): %v", err)
	}

	if aliceState.EF <= 2.5 {
		t.Errorf("alice EF = %v, want > 2.5", aliceState.EF)
	}
	// SM-2 真实语义：grade<3 视为失败，Repetitions=0、IntervalDays=1、EF 不变。
	if bobState.EF != 2.5 {
		t.Errorf("bob EF = %v, want 2.5 (grade<3 时 EF 不变)", bobState.EF)
	}
	if bobState.Repetitions != 0 {
		t.Errorf("bob Repetitions = %v, want 0", bobState.Repetitions)
	}

	gotAlice, err := s.GetReviewState(n.ID, "alice")
	if err != nil {
		t.Fatalf("GetReviewState(alice): %v", err)
	}
	gotBob, err := s.GetReviewState(n.ID, "bob")
	if err != nil {
		t.Fatalf("GetReviewState(bob): %v", err)
	}
	if gotAlice == gotBob {
		t.Errorf("alice and bob states should differ, both = %+v", gotAlice)
	}
	if gotAlice != aliceState {
		t.Errorf("alice persisted state = %+v, want %+v", gotAlice, aliceState)
	}
	if gotBob != bobState {
		t.Errorf("bob persisted state = %+v, want %+v", gotBob, bobState)
	}

	// 与单用户基线一致：review.Next(InitialState, Grade) 的结果应等于各自持久化状态。
	base := review.InitialState(today)
	wantAlice := review.Next(base, review.Grade(5), today)
	wantBob := review.Next(base, review.Grade(0), today)
	if aliceState != wantAlice {
		t.Errorf("alice state = %+v, want %+v", aliceState, wantAlice)
	}
	if bobState != wantBob {
		t.Errorf("bob state = %+v, want %+v", bobState, wantBob)
	}
}

func TestReviewIsolationDigest(t *testing.T) {
	s := newTestStore(t)
	today := time.Now()
	yesterday := today.AddDate(0, 0, -1)

	a1, err := s.CreateNoteFor(context.Background(), Note{Title: "a1", Body: "x"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor a1: %v", err)
	}
	a2, err := s.CreateNoteFor(context.Background(), Note{Title: "a2", Body: "x"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor a2: %v", err)
	}
	b1, err := s.CreateNoteFor(context.Background(), Note{Title: "b1", Body: "x"}, "bob")
	if err != nil {
		t.Fatalf("CreateNoteFor b1: %v", err)
	}
	// 各自造一条到期数据：grade 0 按 SM-2 得 due=yesterday+1=今天。
	if _, err := s.RecordReview(context.Background(), a1.ID, 0, yesterday, "alice"); err != nil {
		t.Fatalf("RecordReview a1: %v", err)
	}
	if _, err := s.RecordReview(context.Background(), b1.ID, 0, yesterday, "bob"); err != nil {
		t.Fatalf("RecordReview b1: %v", err)
	}

	// 到期部分按用户隔离：n=1 时只取到该用户自己的到期笔记。
	aliceDigest, err := s.DigestNotes(today, 1, "alice")
	if err != nil {
		t.Fatalf("DigestNotes(alice): %v", err)
	}
	if len(aliceDigest) != 1 || aliceDigest[0].ID != a1.ID {
		t.Errorf("alice digest n=1 = %v, want [a1]", idsOf(aliceDigest))
	}
	bobDigest, err := s.DigestNotes(today, 1, "bob")
	if err != nil {
		t.Fatalf("DigestNotes(bob): %v", err)
	}
	if len(bobDigest) != 1 || bobDigest[0].ID != b1.ID {
		t.Errorf("bob digest n=1 = %v, want [b1]", idsOf(bobDigest))
	}

	// 补足语义：digest = 该用户到期优先 + 该用户从未复习过的笔记补足
	// （含他人创建但该用户没复习过的笔记——复习一次后即归属该用户）。
	aliceFull, err := s.DigestNotes(today, 10, "alice")
	if err != nil {
		t.Fatalf("DigestNotes(alice,10): %v", err)
	}
	aliceIDs := map[int64]bool{}
	for _, n := range aliceFull {
		aliceIDs[n.ID] = true
	}
	if !aliceIDs[a1.ID] || !aliceIDs[a2.ID] {
		t.Errorf("alice digest missing own notes: got %v", aliceIDs)
	}
	if len(aliceFull) == 0 || aliceFull[0].ID != a1.ID {
		t.Errorf("alice digest should list due note a1 first: got %v", idsOf(aliceFull))
	}
}

// idsOf 提取笔记 id 列表（测试辅助）。
func idsOf(notes []Note) []int64 {
	ids := make([]int64, len(notes))
	for i := range notes {
		ids[i] = notes[i].ID
	}
	return ids
}

func TestReviewIsolationStats(t *testing.T) {
	s := newTestStore(t)
	today := time.Now()

	n, err := s.CreateNoteFor(context.Background(), Note{Title: "alice stats", Body: "x"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	if _, err := s.RecordReview(context.Background(), n.ID, 4, today, "alice"); err != nil {
		t.Fatalf("RecordReview(alice): %v", err)
	}

	aliceStats, err := s.ReviewStats(today, "alice")
	if err != nil {
		t.Fatalf("ReviewStats(alice): %v", err)
	}
	if aliceStats.Reviewed7d != 1 {
		t.Errorf("alice Reviewed7d = %d, want 1", aliceStats.Reviewed7d)
	}

	bobStats, err := s.ReviewStats(today, "bob")
	if err != nil {
		t.Fatalf("ReviewStats(bob): %v", err)
	}
	if bobStats.Reviewed7d != 0 {
		t.Errorf("bob Reviewed7d = %d, want 0", bobStats.Reviewed7d)
	}

	// DueToday 按用户隔离：alice 复习后 due 在未来（>today），bob 无行。
	if aliceStats.DueToday != 0 {
		t.Errorf("alice DueToday = %d, want 0", aliceStats.DueToday)
	}
	if bobStats.DueToday != 0 {
		t.Errorf("bob DueToday = %d, want 0", bobStats.DueToday)
	}
}

func TestReviewIsolationMigrationFromOldSchema(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "old.db")

	raw, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open raw db: %v", err)
	}
	stmts := []string{
		`CREATE TABLE notes(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', pinned INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`,
		`CREATE TABLE reviews(note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE, ef REAL NOT NULL DEFAULT 2.5, interval_days INTEGER NOT NULL DEFAULT 0, repetitions INTEGER NOT NULL DEFAULT 0, due_date TEXT NOT NULL, last_reviewed_at TEXT, reviewed_count INTEGER NOT NULL DEFAULT 0)`,
		`INSERT INTO notes(id, title, body, pinned, created_at, updated_at) VALUES (1, 'legacy', '', 0, '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z')`,
		`INSERT INTO reviews(note_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count) VALUES (1, 2.6, 0, 0, '2000-01-01', NULL, 0)`,
	}
	for _, s := range stmts {
		if _, err := raw.Exec(s); err != nil {
			t.Fatalf("exec %q: %v", s, err)
		}
	}
	if err := raw.Close(); err != nil {
		t.Fatalf("close raw db: %v", err)
	}

	s, err := Open(path)
	if err != nil {
		t.Fatalf("Open after old schema: %v", err)
	}

	rows, err := s.db.Query(`PRAGMA table_info(reviews)`)
	if err != nil {
		t.Fatalf("pragma table_info: %v", err)
	}
	hasUserID := false
	for rows.Next() {
		var cid int
		var name, ctype string
		var notnull, pk int
		var dflt sql.NullString
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			t.Fatalf("scan pragma row: %v", err)
		}
		if name == "user_id" {
			hasUserID = true
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("pragma rows err: %v", err)
	}
	if err := rows.Close(); err != nil {
		t.Fatalf("pragma rows close: %v", err)
	}
	if !hasUserID {
		t.Fatalf("reviews table missing user_id column after migration")
	}

	var uid string
	if err := s.db.QueryRow(`SELECT user_id FROM reviews WHERE note_id = 1`).Scan(&uid); err != nil {
		t.Fatalf("select user_id: %v", err)
	}
	if uid != "local" {
		t.Errorf("user_id = %q, want %q", uid, "local")
	}

	st, err := s.GetReviewState(1, "local")
	if err != nil {
		t.Fatalf("GetReviewState after migration: %v", err)
	}
	if st.EF != 2.6 {
		t.Errorf("EF = %v, want 2.6", st.EF)
	}

	if err := s.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}

	s2, err := Open(path)
	if err != nil {
		t.Fatalf("reopen after migration: %v", err)
	}
	defer s2.Close()

	st2, err := s2.GetReviewState(1, "local")
	if err != nil {
		t.Fatalf("GetReviewState after reopen: %v", err)
	}
	if st2.EF != 2.6 {
		t.Errorf("EF after reopen = %v, want 2.6", st2.EF)
	}
}

func TestRecordReviewCreatesRowForNewUser(t *testing.T) {
	s := newTestStore(t)

	note, err := s.CreateNoteFor(context.Background(), Note{Title: "shared", Body: "body"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	id := note.ID

	today := time.Date(2024, 1, 10, 0, 0, 0, 0, time.UTC)
	if _, err := s.RecordReview(context.Background(), id, 4, today, "bob"); err != nil {
		t.Fatalf("RecordReview bob: %v", err)
	}

	var aliceCount int
	if err := s.db.QueryRow(
		`SELECT reviewed_count FROM reviews WHERE note_id = ? AND user_id = 'alice'`, id,
	).Scan(&aliceCount); err != nil {
		t.Fatalf("select alice row: %v", err)
	}
	if aliceCount != 0 {
		t.Errorf("alice reviewed_count = %d, want 0", aliceCount)
	}

	var bobCount int
	if err := s.db.QueryRow(
		`SELECT reviewed_count FROM reviews WHERE note_id = ? AND user_id = 'bob'`, id,
	).Scan(&bobCount); err != nil {
		t.Fatalf("select bob row: %v", err)
	}
	if bobCount != 1 {
		t.Errorf("bob reviewed_count = %d, want 1", bobCount)
	}

	aliceState, err := s.GetReviewState(id, "alice")
	if err != nil {
		t.Fatalf("GetReviewState alice: %v", err)
	}
	bobState, err := s.GetReviewState(id, "bob")
	if err != nil {
		t.Fatalf("GetReviewState bob: %v", err)
	}
	if aliceState.Repetitions != 0 {
		t.Errorf("alice Repetitions = %d, want 0", aliceState.Repetitions)
	}
	if bobState.Repetitions != 1 {
		t.Errorf("bob Repetitions = %d, want 1", bobState.Repetitions)
	}
}
