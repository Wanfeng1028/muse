package store

import (
"regexp"
"testing"
)

func TestStoreSlugR2_Auto200Unique(t *testing.T) {
st := newTestStore(t)
seen := make(map[string]bool)
for i := 0; i < 200; i++ {
id, err := st.CreateLinkEx("", "https://example.com/u", "", nil, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 第 %d 次失败: %v", i, err)
}
link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink(%d) 失败: %v", id, err)
}
if link == nil {
t.Fatalf("GetLink(%d) 返回 nil", id)
}
seen[link.Slug] = true
}
if len(seen) != 200 {
t.Fatalf("自动 slug 去重计数 = %d, 期望 200", len(seen))
}
}

func TestStoreSlugR2_AutoFormat6Base62(t *testing.T) {
st := newTestStore(t)
re := regexp.MustCompile(`^[A-Za-z0-9]{6}$`)
for i := 0; i < 200; i++ {
id, err := st.CreateLinkEx("", "https://example.com/u", "", nil, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 第 %d 次失败: %v", i, err)
}
link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink(%d) 失败: %v", id, err)
}
if link == nil {
t.Fatalf("GetLink(%d) 返回 nil", id)
}
if len(link.Slug) != 6 {
t.Fatalf("第 %d 个 slug %q 长度 = %d, 期望 6", i, link.Slug, len(link.Slug))
}
if !re.MatchString(link.Slug) {
t.Fatalf("第 %d 个 slug %q 不匹配 ^[A-Za-z0-9]{6}$", i, link.Slug)
}
}
}

func TestStoreSlugR2_AutoNoConfusableFiltering(t *testing.T) {
// base62 未剔除易混淆字符是产品既定选择，见 util/slug.go 注释；本测试钉死该行为。
st := newTestStore(t)
all := ""
for i := 0; i < 200; i++ {
id, err := st.CreateLinkEx("", "https://example.com/u", "", nil, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 第 %d 次失败: %v", i, err)
}
link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink(%d) 失败: %v", id, err)
}
if link == nil {
t.Fatalf("GetLink(%d) 返回 nil", id)
}
all += link.Slug
}
found := false
for _, c := range []string{"0", "O", "1", "l"} {
if regexp.MustCompile(c).MatchString(all) {
found = true
break
}
}
if !found {
t.Fatalf("200 个自动 slug 中未出现易混淆字符 0/O/1/l, 拼接结果长度 %d", len(all))
}
}

func TestStoreSlugR2_CustomSlugPreserved(t *testing.T) {
st := newTestStore(t)
id, err := st.CreateLinkEx("MySlug9", "https://example.com/c", "", nil, nil, false, false)
if err != nil {
t.Fatalf("CreateLinkEx 自定义 slug 失败: %v", err)
}
link, err := st.GetLink(id)
if err != nil {
t.Fatalf("GetLink(%d) 失败: %v", id, err)
}
if link == nil {
t.Fatalf("GetLink(%d) 返回 nil", id)
}
if link.Slug != "MySlug9" {
t.Fatalf("自定义 slug = %q, 期望 %q", link.Slug, "MySlug9")
}
}
