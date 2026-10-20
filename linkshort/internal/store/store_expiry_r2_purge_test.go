package store

import (
"errors"
"testing"
"time"
)

func TestStoreExpiryR2_PurgeDeletesExpiredWithVisits(t *testing.T) {
st := newTestStore(t)
expired := time.Now().Add(-time.Hour)
id, err := st.CreateLinkEx("b2px1", "https://example.com/b2px1", "t", &expired, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}
if err := st.RecordVisit(id, "h1", "ua", ""); err != nil {
t.Fatalf("RecordVisit 第一次失败: %v", err)
}
if err := st.RecordVisit(id, "h1", "ua", ""); err != nil {
t.Fatalf("RecordVisit 第二次失败: %v", err)
}
n, err := st.PurgeExpiredLinks(time.Now())
if err != nil {
t.Fatalf("PurgeExpiredLinks 失败: %v", err)
}
if n != 1 {
t.Fatalf("PurgeExpiredLinks 删除行数 = %d, 期望 1", n)
}
if _, err := st.GetLink(id); !errors.Is(err, ErrNotFound) {
t.Fatalf("GetLink 错误 = %v, 期望 ErrNotFound", err)
}
stats, err := st.LinkDailyClicks(id, 7)
if err != nil {
t.Fatalf("LinkDailyClicks 失败: %v", err)
}
var total int64
for _, s := range stats {
total += s.Clicks
}
if total != 0 {
t.Fatalf("LinkDailyClicks 求和 = %d, 期望 0", total)
}
}

func TestStoreExpiryR2_PurgeKeepsFreshAndNull(t *testing.T) {
st := newTestStore(t)
fresh := time.Now().Add(time.Hour)
idFresh, err := st.CreateLinkEx("b2px2", "https://example.com/b2px2", "t", &fresh, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}
idNull, err := st.CreateLinkEx("b2px3", "https://example.com/b2px3", "t", nil, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}
n, err := st.PurgeExpiredLinks(time.Now())
if err != nil {
t.Fatalf("PurgeExpiredLinks 失败: %v", err)
}
if n != 0 {
t.Fatalf("PurgeExpiredLinks 删除行数 = %d, 期望 0", n)
}
if _, err := st.GetLink(idFresh); err != nil {
t.Fatalf("GetLink 未过期链失败: %v", err)
}
if _, err := st.GetLink(idNull); err != nil {
t.Fatalf("GetLink 永不过期链失败: %v", err)
}
}

func TestStoreExpiryR2_PurgeBoundaryExactCutoff(t *testing.T) {
st := newTestStore(t)
cut := time.Now().Truncate(time.Second)
id, err := st.CreateLinkEx("b2px4", "https://example.com/b2px4", "t", &cut, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}
n, err := st.PurgeExpiredLinks(cut)
if err != nil {
t.Fatalf("PurgeExpiredLinks(cut) 失败: %v", err)
}
if n != 0 {
t.Fatalf("PurgeExpiredLinks(cut) 删除行数 = %d, 期望 0", n)
}
n, err = st.PurgeExpiredLinks(cut.Add(time.Second))
if err != nil {
t.Fatalf("PurgeExpiredLinks(cut+1s) 失败: %v", err)
}
if n != 1 {
t.Fatalf("PurgeExpiredLinks(cut+1s) 删除行数 = %d, 期望 1", n)
}
if _, err := st.GetLink(id); !errors.Is(err, ErrNotFound) {
t.Fatalf("GetLink 错误 = %v, 期望 ErrNotFound", err)
}
}

func TestStoreExpiryR2_PurgeIdempotent(t *testing.T) {
st := newTestStore(t)
expired := time.Now().Add(-time.Hour)
if _, err := st.CreateLinkEx("b2px5", "https://example.com/b2px5", "t", &expired, nil, false, false); err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}
n, err := st.PurgeExpiredLinks(time.Now())
if err != nil {
t.Fatalf("PurgeExpiredLinks 第一次失败: %v", err)
}
if n != 1 {
t.Fatalf("PurgeExpiredLinks 第一次删除行数 = %d, 期望 1", n)
}
n, err = st.PurgeExpiredLinks(time.Now())
if err != nil {
t.Fatalf("PurgeExpiredLinks 第二次失败: %v", err)
}
if n != 0 {
t.Fatalf("PurgeExpiredLinks 第二次删除行数 = %d, 期望 0", n)
}
}