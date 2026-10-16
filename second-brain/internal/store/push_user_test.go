// internal/store/push_user_test.go
package store

import (
	"testing"
	"time"
)

func TestListUsersWithDueReviewsEmpty(t *testing.T) {
	st := newTestStore(t)

	users, err := st.ListUsersWithDueReviews(time.Now())
	if err != nil {
		t.Fatalf("ListUsersWithDueReviews: %v", err)
	}
	if len(users) != 0 {
		t.Fatalf("expected empty, got %v", users)
	}
}

func TestListUsersWithDueReviewsSingleUser(t *testing.T) {
	st := newTestStore(t)

	n, err := st.CreateNoteFor(Note{Title: "x", Body: "y"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	yesterday := time.Now().AddDate(0, 0, -1)
	if _, err := st.RecordReview(n.ID, 0, yesterday, "alice"); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}

	users, err := st.ListUsersWithDueReviews(time.Now())
	if err != nil {
		t.Fatalf("ListUsersWithDueReviews: %v", err)
	}
	if len(users) != 1 || users[0] != "alice" {
		t.Fatalf("expected [alice], got %v", users)
	}
}

func TestListUsersWithDueReviewsMultiUserSorted(t *testing.T) {
	st := newTestStore(t)

	yesterday := time.Now().AddDate(0, 0, -1)
	for _, u := range []string{"alice", "bob"} {
		n, err := st.CreateNoteFor(Note{Title: "x", Body: "y"}, u)
		if err != nil {
			t.Fatalf("CreateNoteFor %s: %v", u, err)
		}
		if _, err := st.RecordReview(n.ID, 0, yesterday, u); err != nil {
			t.Fatalf("RecordReview %s: %v", u, err)
		}
	}

	users, err := st.ListUsersWithDueReviews(time.Now())
	if err != nil {
		t.Fatalf("ListUsersWithDueReviews: %v", err)
	}
	if len(users) != 2 || users[0] != "alice" || users[1] != "bob" {
		t.Fatalf("expected [alice bob], got %v", users)
	}
}

func TestListUsersWithDueReviewsNormalized(t *testing.T) {
	st := newTestStore(t)

	n, err := st.CreateNoteFor(Note{Title: "x", Body: "y"}, "Alice")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	yesterday := time.Now().AddDate(0, 0, -1)
	if _, err := st.RecordReview(n.ID, 0, yesterday, "Alice"); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}

	users, err := st.ListUsersWithDueReviews(time.Now())
	if err != nil {
		t.Fatalf("ListUsersWithDueReviews: %v", err)
	}
	if len(users) != 1 || users[0] != "alice" {
		t.Fatalf("expected [alice], got %v", users)
	}
}

func TestListUsersWithDueReviewsExcludesFuture(t *testing.T) {
	st := newTestStore(t)

	n, err := st.CreateNoteFor(Note{Title: "x", Body: "y"}, "carol")
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	today := time.Now()
	if _, err := st.RecordReview(n.ID, 5, today, "carol"); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}

	users, err := st.ListUsersWithDueReviews(today)
	if err != nil {
		t.Fatalf("ListUsersWithDueReviews: %v", err)
	}
	for _, u := range users {
		if u == "carol" {
			t.Fatalf("carol should be excluded, got %v", users)
		}
	}
}

func TestPushLogPerUserIsolation(t *testing.T) {
	st := newTestStore(t)
	date := time.Now().Format("2006-01-02")

	if err := st.RecordPushFor(date, "webhook", "alice", "sent", ""); err != nil {
		t.Fatalf("RecordPushFor: %v", err)
	}
	if !st.HasPushedFor(date, "webhook", "alice") {
		t.Fatalf("expected alice pushed")
	}
	if st.HasPushedFor(date, "webhook", "bob") {
		t.Fatalf("expected bob not pushed")
	}
	if st.HasPushed(date, "webhook") {
		t.Fatalf("expected local not pushed")
	}
}

func TestPushLogLegacyDefaultUser(t *testing.T) {
	st := newTestStore(t)
	date := time.Now().Format("2006-01-02")

	if err := st.RecordPush(date, "webhook", "sent", ""); err != nil {
		t.Fatalf("RecordPush: %v", err)
	}
	if !st.HasPushed(date, "webhook") {
		t.Fatalf("expected local pushed via legacy")
	}
	if !st.HasPushedFor(date, "webhook", "local") {
		t.Fatalf("expected local pushed via HasPushedFor")
	}
}

func TestListPushLogForUserFilter(t *testing.T) {
	st := newTestStore(t)
	date := time.Now().Format("2006-01-02")

	if err := st.RecordPushFor(date, "webhook", "alice", "sent", ""); err != nil {
		t.Fatalf("RecordPushFor alice: %v", err)
	}
	if err := st.RecordPushFor(date, "webhook", "bob", "sent", ""); err != nil {
		t.Fatalf("RecordPushFor bob: %v", err)
	}

	aliceLogs, err := st.ListPushLogFor(50, "alice")
	if err != nil {
		t.Fatalf("ListPushLogFor alice: %v", err)
	}
	if len(aliceLogs) != 1 || aliceLogs[0].User != "alice" {
		t.Fatalf("expected 1 alice log, got %v", aliceLogs)
	}

	all, err := st.ListPushLogFor(50, "")
	if err != nil {
		t.Fatalf("ListPushLogFor all: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("expected 2 logs, got %v", all)
	}
}
