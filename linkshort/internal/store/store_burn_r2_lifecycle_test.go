package store

import (
	"errors"
	"testing"
	"time"
)

func TestStoreBurnR2_FullLifecycle(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("b2lc1", "https://example.com/lc1", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if !link.Enabled {
		t.Fatalf("初始 Enabled 应为 true, 实际 false")
	}
	if link.BurnedAt != nil {
		t.Fatalf("初始 BurnedAt 应为 nil, 实际 %v", link.BurnedAt)
	}

	ok, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn 失败: %v", err)
	}
	if !ok {
		t.Fatalf("首次 TryBurn 应返回 true, 实际 false")
	}

	link, err = st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if link.Enabled {
		t.Fatalf("burn 后 Enabled 应为 false, 实际 true")
	}
	if link.BurnedAt == nil {
		t.Fatalf("burn 后 BurnedAt 不应为 nil")
	}

	ok, err = st.TryBurn(id)
	if err != nil {
		t.Fatalf("第二次 TryBurn 失败: %v", err)
	}
	if ok {
		t.Fatalf("第二次 TryBurn 应返回 false, 实际 true")
	}

	n, err := st.PurgeExpiredBurned(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("PurgeExpiredBurned 应删除 1 行, 实际 %d", n)
	}

	_, err = st.GetLink(id)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("purge 后 GetLink 应返回 ErrNotFound, 实际 %v", err)
	}
}

func TestStoreBurnR2_PurgeRespectsCutoff(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("b2lc2", "https://example.com/lc2", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	ok, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn 失败: %v", err)
	}
	if !ok {
		t.Fatalf("TryBurn 应返回 true, 实际 false")
	}

	n, err := st.PurgeExpiredBurned(time.Now().Add(-time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n != 0 {
		t.Fatalf("cutoff 早于 burned_at, 应删除 0 行, 实际 %d", n)
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if link.Enabled {
		t.Fatalf("GetLink 后 Enabled 应为 false, 实际 true")
	}
	if link.BurnedAt == nil {
		t.Fatalf("GetLink 后 BurnedAt 不应为 nil")
	}
}

func TestStoreBurnR2_NonBurnNeverPurgedAsBurned(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("b2lc3", "https://example.com/lc3", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	n, err := st.PurgeExpiredBurned(time.Now().Add(24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n != 0 {
		t.Fatalf("非 burn 链不应被删除, 应删除 0 行, 实际 %d", n)
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if !link.Enabled {
		t.Fatalf("非 burn 链 Enabled 应为 true, 实际 false")
	}
}

func TestStoreBurnR2_BurnedAtUTCFormat(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("b2lc4", "https://example.com/lc4", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	ok, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn 失败: %v", err)
	}
	if !ok {
		t.Fatalf("TryBurn 应返回 true, 实际 false")
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if link.BurnedAt == nil {
		t.Fatalf("BurnedAt 不应为 nil")
	}
	formatted := link.BurnedAt.Format(time.RFC3339)
	if formatted[len(formatted)-1] != 'Z' {
		t.Fatalf("BurnedAt 应以 Z 结尾 (UTC), 实际 %q", formatted)
	}
}
