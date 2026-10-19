package store

import (
	"testing"
)

// TestGraphCycleKept 验证 A↔B 双向链接保留两条边（环不去重）。
func TestGraphCycleKept(t *testing.T) {
	s := newTestStore(t)

	a, err := s.CreateNote(Note{Title: "A", Body: "指向 [[B]]"})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}
	b, err := s.CreateNote(Note{Title: "B", Body: "指回 [[A]]"})
	if err != nil {
		t.Fatalf("CreateNote B: %v", err)
	}

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() error: %v", err)
	}
	if len(gd.Edges) != 2 {
		t.Fatalf("期望 2 条边, 实际 %d 条: %+v", len(gd.Edges), gd.Edges)
	}
	got := map[[2]int64]bool{}
	for _, e := range gd.Edges {
		got[[2]int64{e.Source, e.Target}] = true
	}
	want := map[[2]int64]bool{
		{a.ID, b.ID}: true,
		{b.ID, a.ID}: true,
	}
	if len(got) != len(want) {
		t.Fatalf("边集合大小不匹配: 期望 %d, 实际 %d, got=%v", len(want), len(got), got)
	}
	for k := range want {
		if !got[k] {
			t.Fatalf("缺少期望边 %v, got=%v", k, got)
		}
	}
}

// TestGraphSelfLinkSkipped 验证自引用 [[S]] 不产生自环边。
func TestGraphSelfLinkSkipped(t *testing.T) {
	s := newTestStore(t)

	n, err := s.CreateNote(Note{Title: "S", Body: "自指 [[S]]"})
	if err != nil {
		t.Fatalf("CreateNote S: %v", err)
	}

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() error: %v", err)
	}

	hasSelf := false
	for _, e := range gd.Edges {
		if e.Source == e.Target {
			hasSelf = true
		}
		if e.Source == n.ID && e.Target == n.ID {
			t.Fatalf("不应存在自环边 (S→S), got=%+v", gd.Edges)
		}
	}
	if hasSelf {
		t.Fatalf("存在自环边, got=%+v", gd.Edges)
	}

	found := false
	for _, node := range gd.Nodes {
		if node.ID == n.ID && node.Title == "S" {
			found = true
		}
	}
	if !found {
		t.Fatalf("nodes 中应包含 S(id=%d), got=%+v", n.ID, gd.Nodes)
	}
}

// TestGraphDuplicateLinkDedup 验证同一笔记正文多次 [[B]] 去重为 1 条边。
func TestGraphDuplicateLinkDedup(t *testing.T) {
	s := newTestStore(t)

	a, err := s.CreateNote(Note{Title: "A", Body: "开头 [[B]] 中间 [[B]] 结尾 [[B]]"})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}
	b, err := s.CreateNote(Note{Title: "B", Body: "无外链"})
	if err != nil {
		t.Fatalf("CreateNote B: %v", err)
	}

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() error: %v", err)
	}

	count := 0
	for _, e := range gd.Edges {
		if e.Source == a.ID && e.Target == b.ID {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("期望恰 1 条 A→B, 实际 %d 条; 全部边=%+v", count, gd.Edges)
	}
}

// TestGraphDanglingLinkSkipped 验证悬空链接不产生边且不报错。
func TestGraphDanglingLinkSkipped(t *testing.T) {
	s := newTestStore(t)

	if _, err := s.CreateNote(Note{Title: "A", Body: "指向 [[根本不存在的标题]]"}); err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() 悬空链接不应报错, got err=%v", err)
	}
	if len(gd.Edges) != 0 {
		t.Fatalf("期望 edges 为空, 实际 %d 条: %+v", len(gd.Edges), gd.Edges)
	}
}

// TestGraphTitleCaseInsensitive 验证标题匹配大小写不敏感。
func TestGraphTitleCaseInsensitive(t *testing.T) {
	s := newTestStore(t)

	target, err := s.CreateNote(Note{Title: "Foo", Body: "无外链"})
	if err != nil {
		t.Fatalf("CreateNote Foo: %v", err)
	}
	src, err := s.CreateNote(Note{Title: "Src", Body: "小写链接 [[foo]]"})
	if err != nil {
		t.Fatalf("CreateNote Src: %v", err)
	}

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() error: %v", err)
	}

	found := false
	for _, e := range gd.Edges {
		if e.Source == src.ID && e.Target == target.ID {
			found = true
		}
	}
	if !found {
		t.Fatalf("期望边 (%d→%d) 因大小写不敏感匹配存在, 实际边=%+v",
			src.ID, target.ID, gd.Edges)
	}
}

// TestGraphEmptyDB 验证空库返回非 nil 空切片。
func TestGraphEmptyDB(t *testing.T) {
	s := newTestStore(t)

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() error: %v", err)
	}
	if gd.Nodes == nil {
		t.Fatalf("期望 Nodes 非 nil, 实际 nil")
	}
	if gd.Edges == nil {
		t.Fatalf("期望 Edges 非 nil, 实际 nil")
	}
	if len(gd.Nodes) != 0 {
		t.Fatalf("期望 len(Nodes)==0, 实际 %d", len(gd.Nodes))
	}
	if len(gd.Edges) != 0 {
		t.Fatalf("期望 len(Edges)==0, 实际 %d", len(gd.Edges))
	}
}

// TestGraphTagsAttached 验证 GraphNode.Tags 与笔记标签一致。
func TestGraphTagsAttached(t *testing.T) {
	s := newTestStore(t)

	n, err := s.CreateNote(Note{
		Title: "Tagged",
		Body:  "正文",
		Tags:  []string{"ai", "go"},
	})
	if err != nil {
		t.Fatalf("CreateNote Tagged: %v", err)
	}

	gd, err := s.Graph()
	if err != nil {
		t.Fatalf("Graph() error: %v", err)
	}

	var target *GraphNode
	for i := range gd.Nodes {
		if gd.Nodes[i].ID == n.ID {
			target = &gd.Nodes[i]
			break
		}
	}
	if target == nil {
		t.Fatalf("nodes 中未找到 id=%d, got=%+v", n.ID, gd.Nodes)
	}

	got := map[string]bool{}
	for _, tag := range target.Tags {
		got[tag] = true
	}
	for _, want := range []string{"ai", "go"} {
		if !got[want] {
			t.Fatalf("期望标签 %q 存在, 实际 tags=%v", want, target.Tags)
		}
	}
}
