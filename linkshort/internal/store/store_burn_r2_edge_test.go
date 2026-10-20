package store

import (
	"errors"
	"testing"
)

func TestStoreBurnR2_TryBurnOnDisabledReturnsFalse(t *testing.T) {
	s := newTestStore(t)

	id, err := s.CreateLinkEx("r2-disable", "https://example.com/r2-disable", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	if err := s.UpdateLinkEx(id, "", false, nil, nil, true, false); err != nil {
		t.Fatalf("UpdateLinkEx: %v", err)
	}

	burned, err := s.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if burned {
		t.Fatalf("TryBurn on disabled link = true, want false")
	}
}

func TestStoreBurnR2_TryBurnOnMissingID(t *testing.T) {
	s := newTestStore(t)

	burned, err := s.TryBurn(999999)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if burned {
		t.Fatalf("TryBurn on missing id = true, want false")
	}
}

func TestStoreBurnR2_MarkBurnedTwiceBothNil(t *testing.T) {
	s := newTestStore(t)

	id, err := s.CreateLinkEx("r2-mark-twice", "https://example.com/r2-mark-twice", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned first: %v", err)
	}
	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned second: %v", err)
	}
}

func TestStoreBurnR2_MarkBurnedNonBurnLink(t *testing.T) {
	s := newTestStore(t)

	id, err := s.CreateLinkEx("r2-nonburn", "https://example.com/r2-nonburn", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	err = s.MarkBurned(id)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("MarkBurned non-burn link err = %v, want ErrNotFound", err)
	}
}

func TestStoreBurnR2_TryBurnAfterMarkBurnedFalse(t *testing.T) {
	s := newTestStore(t)

	id, err := s.CreateLinkEx("r2-after-mark", "https://example.com/r2-after-mark", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}

	burned, err := s.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if burned {
		t.Fatalf("TryBurn after MarkBurned = true, want false")
	}
}