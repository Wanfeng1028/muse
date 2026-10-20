package store

import (
"sync"
"testing"
)

func TestStoreLimitR2_PairingUnderRace(t *testing.T) {
st := newTestStore(t)
mv := int64(4)
id, err := st.CreateLinkEx("b2pr1", "https://example.com/lc1", "", nil, &mv, true, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}

const goroutines = 32
var wg sync.WaitGroup
start := make(chan struct{})
var mu sync.Mutex
okCount := 0

wg.Add(goroutines)
for i := 0; i < goroutines; i++ {
go func() {
defer wg.Done()
<-start
ok, err := st.TryConsumeVisit(id)
if err != nil {
return
}
if ok {
if err := st.RecordVisitNoCount(id, "h", "ua", "", "", "", "", ""); err != nil {
return
}
mu.Lock()
okCount++
mu.Unlock()
}
}()
}
close(start)
wg.Wait()

if okCount != 4 {
t.Fatalf("ok 次数 = %d, 期望 4", okCount)
}

link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink 失败: %v", err)
}
if link.Clicks != 4 {
t.Fatalf("Clicks = %d, 期望 4", link.Clicks)
}

stats, err := st.LinkDailyClicks(id, 7)
if err != nil {
t.Fatalf("LinkDailyClicks 失败: %v", err)
}
var sum int64
for _, s := range stats {
sum += s.Clicks
}
if sum != 4 {
t.Fatalf("visits 求和 = %d, 期望 4", sum)
}
}

func TestStoreLimitR2_PairingSerial(t *testing.T) {
st := newTestStore(t)
mv := int64(3)
id, err := st.CreateLinkEx("b2pr2", "https://example.com/lc2", "", nil, &mv, true, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}

var results []bool
for i := 0; i < 5; i++ {
ok, err := st.TryConsumeVisit(id)
if err != nil {
t.Fatalf("TryConsumeVisit 失败: %v", err)
}
results = append(results, ok)
if ok {
if err := st.RecordVisitNoCount(id, "h", "ua", "", "", "", "", ""); err != nil {
t.Fatalf("RecordVisitNoCount 失败: %v", err)
}
}
}

for i := 0; i < 3; i++ {
if !results[i] {
t.Fatalf("第 %d 次 ok = false, 期望 true", i+1)
}
}
for i := 3; i < 5; i++ {
if results[i] {
t.Fatalf("第 %d 次 ok = true, 期望 false", i+1)
}
}

link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink 失败: %v", err)
}
if link.Clicks != 3 {
t.Fatalf("Clicks = %d, 期望 3", link.Clicks)
}

stats, err := st.LinkDailyClicks(id, 7)
if err != nil {
t.Fatalf("LinkDailyClicks 失败: %v", err)
}
var sum int64
for _, s := range stats {
sum += s.Clicks
}
if sum != 3 {
t.Fatalf("visits 求和 = %d, 期望 3", sum)
}
}

func TestStoreLimitR2_NoCountAlone(t *testing.T) {
st := newTestStore(t)
mv := int64(2)
id, err := st.CreateLinkEx("b2pr3", "https://example.com/lc3", "", nil, &mv, true, false)
if err != nil {
t.Fatalf("CreateLinkEx 失败: %v", err)
}

for i := 0; i < 3; i++ {
if err := st.RecordVisitNoCount(id, "h", "ua", "", "", "", "", ""); err != nil {
t.Fatalf("RecordVisitNoCount 失败: %v", err)
}
}

link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink 失败: %v", err)
}
if link.Clicks != 0 {
t.Fatalf("Clicks = %d, 期望 0", link.Clicks)
}

stats, err := st.LinkDailyClicks(id, 7)
if err != nil {
t.Fatalf("LinkDailyClicks 失败: %v", err)
}
var sum int64
for _, s := range stats {
sum += s.Clicks
}
if sum != 3 {
t.Fatalf("visits 求和 = %d, 期望 3", sum)
}
}