package store

import (
	"errors"
	"testing"
	"time"
)

func TestStoreExpiryR2_UpdateExpiryRoundTrip(t *testing.T) {
	st := newTestStore(t)

	id, err := st.CreateLinkEx("b2rt1", "https://example.com/b2rt1", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	exp := time.Now().Add(2 * time.Hour).Truncate(time.Second)
	if err := st.UpdateLinkEx(id, "", true, &exp, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx 失败: %v", err)
	}

	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if l.ExpiresAt == nil {
		t.Fatalf("ExpiresAt 为 nil, 期望非 nil")
	}
	if got, want := l.ExpiresAt.UTC().Format(time.RFC3339), exp.UTC().Format(time.RFC3339); got != want {
		t.Fatalf("ExpiresAt = %q, 期望 %q", got, want)
	}
}

func TestStoreExpiryR2_UpdateExpiryToNil(t *testing.T) {
	st := newTestStore(t)

	exp := time.Now().Add(3 * time.Hour).Truncate(time.Second)
	id, err := st.CreateLinkEx("b2rt2", "https://example.com/b2rt2", "", &exp, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	if err := st.UpdateLinkEx(id, "", true, nil, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx 失败: %v", err)
	}

	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if l.ExpiresAt != nil {
		t.Fatalf("ExpiresAt = %v, 期望 nil", l.ExpiresAt)
	}
}

func TestStoreExpiryR2_CreateExpirySecondPrecision(t *testing.T) {
	st := newTestStore(t)

	exp := time.Now().Add(time.Hour).Truncate(time.Second)
	id, err := st.CreateLinkEx("b2rt3", "https://example.com/b2rt3", "", &exp, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if l.ExpiresAt == nil {
		t.Fatalf("ExpiresAt 为 nil, 期望非 nil")
	}
	if got, want := l.ExpiresAt.UTC().Format(time.RFC3339), exp.UTC().Format(time.RFC3339); got != want {
		t.Fatalf("ExpiresAt = %q, 期望 %q", got, want)
	}
}

func TestStoreExpiryR2_UpdateMissingIDNotFound(t *testing.T) {
	st := newTestStore(t)

	err := st.UpdateLinkEx(999999, "", true, nil, nil, false, false)
	if err == nil {
		t.Fatalf("UpdateLinkEx 期望 ErrNotFound, 实际 nil")
	}
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("UpdateLinkEx err = %v, 期望 ErrNotFound", err)
	}
}