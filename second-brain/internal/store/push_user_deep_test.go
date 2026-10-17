package store

import (
	"database/sql"
	"path/filepath"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

func newPushUserTestStore(t *testing.T) *Store {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	stmts := []string{
		`CREATE TABLE reviews (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id TEXT NOT NULL,
			due_date TEXT NOT NULL
		)`,
		`CREATE TABLE push_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			date TEXT NOT NULL,
			channel TEXT NOT NULL,
			user_id TEXT NOT NULL,
			status TEXT NOT NULL,
			detail TEXT,
			created_at TEXT NOT NULL,
			UNIQUE(date, channel, user_id)
		)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("create table: %v", err)
		}
	}
	return &Store{db: db}
}

func insertReview(t *testing.T, s *Store, user, dueDate string) {
	t.Helper()
	if _, err := s.db.Exec(
		`INSERT INTO reviews (user_id, due_date) VALUES (?, ?)`, user, dueDate,
	); err != nil {
		t.Fatalf("insert review: %v", err)
	}
}

func TestListUsersWithDueReviews_ScheduleBoundaries(t *testing.T) {
	s := newPushUserTestStore(t)

	cases := []struct {
		name     string
		today    time.Time
		reviews  [][2]string
		wantUser []string
	}{
		{
			name:     "no data returns empty non-nil slice",
			today:    time.Date(2024, 3, 1, 0, 0, 0, 0, time.UTC),
			reviews:  nil,
			wantUser: []string{},
		},
		{
			name:  "due exactly today is included",
			today: time.Date(2024, 3, 10, 12, 0, 0, 0, time.UTC),
			reviews: [][2]string{
				{"alice", "2024-03-10"},
				{"bob", "2024-03-11"},
			},
			wantUser: []string{"alice"},
		},
		{
			name:  "leap day boundary included when today is feb29",
			today: time.Date(2024, 2, 29, 23, 59, 59, 0, time.UTC),
			reviews: [][2]string{
				{"carol", "2024-02-28"},
				{"dave", "2024-02-29"},
				{"erin", "2024-03-01"},
			},
			wantUser: []string{"carol", "dave"},
		},
		{
			name:  "day rollover across midnight excludes tomorrow",
			today: time.Date(2024, 3, 1, 0, 0, 0, 0, time.UTC),
			reviews: [][2]string{
				{"frank", "2024-02-29"},
				{"grace", "2024-03-01"},
				{"heidi", "2024-03-02"},
			},
			wantUser: []string{"frank", "grace"},
		},
		{
			name:  "timezone shift changes effective date",
			today: time.Date(2024, 3, 10, 23, 30, 0, 0, time.FixedZone("CST", 8*3600)),
			reviews: [][2]string{
				{"ivan", "2024-03-10"},
				{"judy", "2024-03-11"},
			},
			wantUser: []string{"ivan"},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			sub := newPushUserTestStore(t)
			for _, r := range tc.reviews {
				insertReview(t, sub, r[0], r[1])
			}
			got, err := sub.ListUsersWithDueReviews(tc.today)
			if err != nil {
				t.Fatalf("ListUsersWithDueReviews: %v", err)
			}
			if got == nil {
				t.Fatalf("got nil slice, want non-nil")
			}
			if len(got) != len(tc.wantUser) {
				t.Fatalf("len(got)=%d want=%d got=%v", len(got), len(tc.wantUser), got)
			}
			for i := range tc.wantUser {
				if got[i] != tc.wantUser[i] {
					t.Fatalf("index %d: got %q want %q (full=%v)", i, got[i], tc.wantUser[i], got)
				}
			}
		})
	}

	_ = s
}

func TestListUsersWithDueReviews_DedupAndOrder(t *testing.T) {
	s := newPushUserTestStore(t)
	insertReview(t, s, "zoe", "2024-01-01")
	insertReview(t, s, "amy", "2024-01-01")
	insertReview(t, s, "zoe", "2024-01-02")
	insertReview(t, s, "amy", "2024-01-03")
	insertReview(t, s, "mia", "2024-01-01")

	got, err := s.ListUsersWithDueReviews(time.Date(2024, 1, 5, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	want := []string{"amy", "mia", "zoe"}
	if len(got) != len(want) {
		t.Fatalf("len=%d want=%d got=%v", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("index %d: got %q want %q", i, got[i], want[i])
		}
	}
}

func TestRecordPushFor_ExtremeEFValuesRoundTrip(t *testing.T) {
	s := newPushUserTestStore(t)

	cases := []struct {
		name   string
		user   string
		status string
		detail string
	}{
		{"min EF as detail string", "u1", "sent", "ef=1.3"},
		{"max EF as detail string", "u2", "sent", "ef=2.5"},
		{"negative EF boundary", "u3", "failed", "ef=-1.0"},
		{"empty detail", "u4", "skipped", ""},
		{"long detail", "u5", "sent", "ef=1.3 interval=999999999 repetition=42"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			date := "2024-05-01"
			if err := s.RecordPushFor(date, "email", tc.user, tc.status, tc.detail); err != nil {
				t.Fatalf("RecordPushFor: %v", err)
			}
			wantPushed := tc.status == "sent"
			if got := s.HasPushedFor(date, "email", tc.user); got != wantPushed {
				t.Fatalf("HasPushedFor(%q) = %v, want %v", tc.status, got, wantPushed)
			}
			recs, err := s.ListPushLogFor(10, tc.user)
			if err != nil {
				t.Fatalf("ListPushLogFor: %v", err)
			}
			if len(recs) != 1 {
				t.Fatalf("len=%d want=1", len(recs))
			}
			if recs[0].Detail != tc.detail {
				t.Fatalf("detail got %q want %q", recs[0].Detail, tc.detail)
			}
			if recs[0].Status != tc.status {
				t.Fatalf("status got %q want %q", recs[0].Status, tc.status)
			}
		})
	}
}

func TestRecordPushFor_UpsertOverwritesStatus(t *testing.T) {
	s := newPushUserTestStore(t)
	date := "2024-05-02"
	if err := s.RecordPushFor(date, "email", "alice", "failed", "first try"); err != nil {
		t.Fatalf("first record: %v", err)
	}
	if s.HasPushedFor(date, "email", "alice") {
		t.Fatalf("HasPushedFor should be false when status=failed")
	}
	if err := s.RecordPushFor(date, "email", "alice", "sent", "retry ok"); err != nil {
		t.Fatalf("second record: %v", err)
	}
	if !s.HasPushedFor(date, "email", "alice") {
		t.Fatalf("HasPushedFor should be true after status=sent")
	}
	recs, err := s.ListPushLogFor(10, "alice")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(recs) != 1 {
		t.Fatalf("upsert should keep single row, got %d", len(recs))
	}
	if recs[0].Detail != "retry ok" {
		t.Fatalf("detail got %q want %q", recs[0].Detail, "retry ok")
	}
}

func TestHasPushedFor_NormalizesUserAndIsolatesChannel(t *testing.T) {
	s := newPushUserTestStore(t)
	date := "2024-06-01"
	if err := s.RecordPushFor(date, "email", "  Alice  ", "sent", "ok"); err != nil {
		t.Fatalf("record: %v", err)
	}
	if !s.HasPushedFor(date, "email", "alice") {
		t.Fatalf("HasPushedFor should normalize and match alice")
	}
	if !s.HasPushedFor(date, "email", "ALICE") {
		t.Fatalf("HasPushedFor should be case-insensitive via NormalizeUser")
	}
	if s.HasPushedFor(date, "sms", "alice") {
		t.Fatalf("different channel must not match")
	}
	if s.HasPushedFor("2024-06-02", "email", "alice") {
		t.Fatalf("different date must not match")
	}
}

func TestListPushLogFor_LimitClamping(t *testing.T) {
	s := newPushUserTestStore(t)
	for i := 0; i < 5; i++ {
		u := string(rune('a' + i))
		if err := s.RecordPushFor("2024-07-01", "email", u, "sent", "ok"); err != nil {
			t.Fatalf("record %d: %v", i, err)
		}
	}

	cases := []struct {
		name      string
		limit     int
		wantCount int
	}{
		{"limit zero defaults to 50", 0, 5},
		{"limit negative defaults to 50", -3, 5},
		{"limit within range", 2, 2},
		{"limit over cap clamps to 200", 5000, 5},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			recs, err := s.ListPushLogFor(tc.limit, "")
			if err != nil {
				t.Fatalf("err: %v", err)
			}
			if len(recs) != tc.wantCount {
				t.Fatalf("len=%d want=%d", len(recs), tc.wantCount)
			}
			if tc.wantCount >= 2 {
				if recs[0].ID <= recs[1].ID {
					t.Fatalf("expected id DESC order, got %d then %d", recs[0].ID, recs[1].ID)
				}
			}
		})
	}
}

func TestListPushLogFor_FilterByUser(t *testing.T) {
	s := newPushUserTestStore(t)
	if err := s.RecordPushFor("2024-08-01", "email", "alice", "sent", "a1"); err != nil {
		t.Fatalf("record alice: %v", err)
	}
	if err := s.RecordPushFor("2024-08-01", "email", "bob", "sent", "b1"); err != nil {
		t.Fatalf("record bob: %v", err)
	}
	if err := s.RecordPushFor("2024-08-02", "email", "alice", "sent", "a2"); err != nil {
		t.Fatalf("record alice2: %v", err)
	}

	aliceRecs, err := s.ListPushLogFor(10, "alice")
	if err != nil {
		t.Fatalf("list alice: %v", err)
	}
	if len(aliceRecs) != 2 {
		t.Fatalf("alice len=%d want=2", len(aliceRecs))
	}
	for _, r := range aliceRecs {
		if NormalizeUser(r.User) != "alice" {
			t.Fatalf("unexpected user %q in alice filter", r.User)
		}
	}
	if aliceRecs[0].Detail != "a2" {
		t.Fatalf("expected newest first, got %q", aliceRecs[0].Detail)
	}

	all, err := s.ListPushLogFor(10, "")
	if err != nil {
		t.Fatalf("list all: %v", err)
	}
	if len(all) != 3 {
		t.Fatalf("all len=%d want=3", len(all))
	}
}

func TestMultiUserIsolationPushUser(t *testing.T) {
	s := newPushUserTestStore(t)
	if err := s.RecordPushFor("2024-09-01", "email", "user-a", "sent", "ok-a"); err != nil {
		t.Fatalf("a: %v", err)
	}
	if err := s.RecordPushFor("2024-09-01", "email", "user-b", "failed", "err-b"); err != nil {
		t.Fatalf("b: %v", err)
	}

	if !s.HasPushedFor("2024-09-01", "email", "user-a") {
		t.Fatalf("user-a should have sent")
	}
	if s.HasPushedFor("2024-09-01", "email", "user-b") {
		t.Fatalf("user-b should not have sent")
	}

	recA, err := s.ListPushLogFor(10, "user-a")
	if err != nil {
		t.Fatalf("list a: %v", err)
	}
	recB, err := s.ListPushLogFor(10, "user-b")
	if err != nil {
		t.Fatalf("list b: %v", err)
	}
	if len(recA) != 1 || len(recB) != 1 {
		t.Fatalf("isolation broken: a=%d b=%d", len(recA), len(recB))
	}
	if recA[0].Detail != "ok-a" {
		t.Fatalf("a detail got %q", recA[0].Detail)
	}
	if recB[0].Detail != "err-b" {
		t.Fatalf("b detail got %q", recB[0].Detail)
	}
}

func TestListPushLogFor_NullDetailBecomesEmpty(t *testing.T) {
	s := newPushUserTestStore(t)
	if _, err := s.db.Exec(
		`INSERT INTO push_log (date, channel, user_id, status, detail, created_at) VALUES (?, ?, ?, ?, NULL, ?)`,
		"2024-10-01", "email", "nulluser", "sent", "2024-10-01T00:00:00Z",
	); err != nil {
		t.Fatalf("insert null detail: %v", err)
	}
	recs, err := s.ListPushLogFor(10, "nulluser")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(recs) != 1 {
		t.Fatalf("len=%d want=1", len(recs))
	}
	if recs[0].Detail != "" {
		t.Fatalf("null detail should map to empty string, got %q", recs[0].Detail)
	}
	if recs[0].Status != "sent" {
		t.Fatalf("status got %q want sent", recs[0].Status)
	}
}
