package store

import (
"errors"
"testing"
"time"
)

func TestStoreExpiryR2_BurnedSweepFirst(t *testing.T) {
st := newTestStore(t)

	burnedID, err := st.CreateLinkEx("b2so1", "https://example.com/b2so1", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx(burned) 失败: %v", err)
	}
	ok, err := st.TryBurn(burnedID)
	if err != nil {
		t.Fatalf("TryBurn 失败: %v", err)
	}
	if !ok {
		t.Fatalf("TryBurn 期望 true, 得到 false")
	}

	past := time.Now().Add(-time.Hour)
	expiredID, err := st.CreateLinkEx("b2so2", "https://example.com/b2so2", "", &past, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx(expired) 失败: %v", err)
	}

	// burned_at 以秒精度存储，before 取 now+2s 确保严格小于成立
	n1, err := st.PurgeExpiredBurned(time.Now().Add(2 * time.Second))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n1 != 1 {
		t.Fatalf("PurgeExpiredBurned 期望 1, 得到 %d", n1)
	}

	n2, err := st.PurgeExpiredLinks(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredLinks 失败: %v", err)
	}
	if n2 != 1 {
		t.Fatalf("PurgeExpiredLinks 期望 1, 得到 %d", n2)
	}

	if _, err := st.GetLink(burnedID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("已销毁链 GetLink 期望 ErrNotFound, 得到 %v", err)
	}
	if _, err := st.GetLink(expiredID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("过期链 GetLink 期望 ErrNotFound, 得到 %v", err)
	}
}

func TestStoreExpiryR2_BurnedAndExpiredNotDoubleCounted(t *testing.T) {
st := newTestStore(t)

	past := time.Now().Add(-time.Hour)
	id, err := st.CreateLinkEx("b2so3", "https://example.com/b2so3", "", &past, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}
	ok, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn 失败: %v", err)
	}
	if !ok {
		t.Fatalf("TryBurn 期望 true, 得到 false")
	}

	// burned_at 以秒精度存储，before 取 now+2s 确保严格小于成立
	n1, err := st.PurgeExpiredBurned(time.Now().Add(2 * time.Second))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n1 != 1 {
		t.Fatalf("PurgeExpiredBurned 期望 1, 得到 %d", n1)
	}

	n2, err := st.PurgeExpiredLinks(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredLinks 失败: %v", err)
	}
	if n2 != 0 {
		t.Fatalf("PurgeExpiredLinks 期望 0, 得到 %d", n2)
	}

	if _, err := st.GetLink(id); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLink 期望 ErrNotFound, 得到 %v", err)
	}
}

func TestStoreExpiryR2_UnburnedBurnLinkByExpiry(t *testing.T) {
st := newTestStore(t)

	past := time.Now().Add(-time.Hour)
	id, err := st.CreateLinkEx("b2so4", "https://example.com/b2so4", "", &past, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	n1, err := st.PurgeExpiredBurned(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n1 != 0 {
		t.Fatalf("PurgeExpiredBurned 期望 0, 得到 %d", n1)
	}

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("PurgeExpiredBurned 后 GetLink 期望存在, 得到 %v", err)
	}

	n2, err := st.PurgeExpiredLinks(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredLinks 失败: %v", err)
	}
	if n2 != 1 {
		t.Fatalf("PurgeExpiredLinks 期望 1, 得到 %d", n2)
	}

	if _, err := st.GetLink(id); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLink 期望 ErrNotFound, 得到 %v", err)
	}
}

func TestStoreExpiryR2_PurgeEmptyStore(t *testing.T) {
st := newTestStore(t)

	n1, err := st.PurgeExpiredLinks(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredLinks 失败: %v", err)
	}
	if n1 != 0 {
		t.Fatalf("PurgeExpiredLinks 期望 0, 得到 %d", n1)
	}

	n2, err := st.PurgeExpiredBurned(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredBurned 失败: %v", err)
	}
	if n2 != 0 {
		t.Fatalf("PurgeExpiredBurned 期望 0, 得到 %d", n2)
	}
}
