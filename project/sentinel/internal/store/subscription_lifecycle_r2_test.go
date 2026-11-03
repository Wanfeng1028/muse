package store

import (
	"database/sql"
	"errors"
	"testing"
)

func TestR2_SubscriptionDuplicate(t *testing.T) {
	st := newTestStore(t)

	pageID, err := st.CreateStatusPage(1, "sub-r2", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	tok1, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken: %v", err)
	}

	id1, err := st.CreateSubscription(pageID, "a@x.com", tok1)
	if err != nil {
		t.Fatalf("CreateSubscription: %v", err)
	}
	if id1 <= 0 {
		t.Fatalf("CreateSubscription id = %d, want > 0", id1)
	}

	tok2, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken: %v", err)
	}

	_, err = st.CreateSubscription(pageID, "a@x.com", tok2)
	if !errors.Is(err, ErrDuplicateSubscription) {
		t.Fatalf("duplicate CreateSubscription err = %v, want %v", err, ErrDuplicateSubscription)
	}

	page2ID, err := st.CreateStatusPage(1, "sub-r2-other", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage second page: %v", err)
	}

	tok3, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken: %v", err)
	}

	id3, err := st.CreateSubscription(page2ID, "a@x.com", tok3)
	if err != nil {
		t.Fatalf("CreateSubscription on second page: %v", err)
	}
	if id3 <= 0 {
		t.Fatalf("CreateSubscription on second page id = %d, want > 0", id3)
	}
}

func TestR2_SubscriptionConfirmIdempotent(t *testing.T) {
	st := newTestStore(t)

	pageID, err := st.CreateStatusPage(1, "sub-r2-confirm", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	tok1, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken: %v", err)
	}

	_, err = st.CreateSubscription(pageID, "a@x.com", tok1)
	if err != nil {
		t.Fatalf("CreateSubscription: %v", err)
	}

	if err := st.ConfirmSubscription(tok1); err != nil {
		t.Fatalf("ConfirmSubscription first call: %v", err)
	}

	sub, err := st.GetSubscriptionByToken(tok1)
	if err != nil {
		t.Fatalf("GetSubscriptionByToken: %v", err)
	}
	if sub.Confirmed != 1 {
		t.Fatalf("sub.Confirmed = %d, want 1", sub.Confirmed)
	}
	if !sub.ConfirmedAt.Valid {
		t.Fatalf("sub.ConfirmedAt.Valid = false, want true")
	}

	err = st.ConfirmSubscription(tok1)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("ConfirmSubscription second call err = %v, want %v", err, sql.ErrNoRows)
	}

	err = st.ConfirmSubscription("no-such-token")
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("ConfirmSubscription missing token err = %v, want %v", err, sql.ErrNoRows)
	}
}

func TestR2_SubscriptionListAndDelete(t *testing.T) {
	st := newTestStore(t)

	pageID, err := st.CreateStatusPage(1, "sub-r2-list-delete", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	tok1, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken: %v", err)
	}

	_, err = st.CreateSubscription(pageID, "a@x.com", tok1)
	if err != nil {
		t.Fatalf("CreateSubscription a: %v", err)
	}
	if err := st.ConfirmSubscription(tok1); err != nil {
		t.Fatalf("ConfirmSubscription a: %v", err)
	}

	tok2, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken: %v", err)
	}

	_, err = st.CreateSubscription(pageID, "b@x.com", tok2)
	if err != nil {
		t.Fatalf("CreateSubscription b: %v", err)
	}
	if err := st.ConfirmSubscription(tok2); err != nil {
		t.Fatalf("ConfirmSubscription b: %v", err)
	}

	subs, err := st.ListConfirmedSubscribers(pageID)
	if err != nil {
		t.Fatalf("ListConfirmedSubscribers: %v", err)
	}
	if len(subs) != 2 {
		t.Fatalf("len(subs) = %d, want 2", len(subs))
	}
	if subs[0].Email != "a@x.com" {
		t.Fatalf("subs[0].Email = %q, want %q", subs[0].Email, "a@x.com")
	}
	if subs[0].Token == "" {
		t.Fatalf("subs[0].Token is empty, want non-empty")
	}

	if err := st.DeleteSubscriptionByToken(tok1); err != nil {
		t.Fatalf("DeleteSubscriptionByToken: %v", err)
	}

	_, err = st.GetSubscriptionByToken(tok1)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("GetSubscriptionByToken after delete err = %v, want %v", err, sql.ErrNoRows)
	}

	err = st.DeleteSubscriptionByToken("no-such")
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("DeleteSubscriptionByToken missing token err = %v, want %v", err, sql.ErrNoRows)
	}
}
