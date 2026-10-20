package store

// 深测补强：双链反向链接一致性（删除/改名/重建场景）。
// 模型生成 + 编排手工修正落盘（修正：UpdateNote 签名为 (n Note) 无 ctx 参数）。
// 锁定的均为当前产品行为：links 表 FK（source 端 CASCADE / target 端 SET NULL），
// resolveBacklinks 在建笔记/改标题时回填同名悬空链接。

import "testing"

func TestBacklinks_删引用者后消失(t *testing.T) {
	s := newDeepTestStore(t)
	tID := seedNote(t, s, "T", "目标笔记")
	aID := seedNote(t, s, "A", "[[T]]")

	links, err := s.Backlinks(tID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 1 {
		t.Fatalf("期望 1 条反向链接，实际 %d", len(links))
	}

	if err := s.DeleteNote(aID); err != nil {
		t.Fatalf("DeleteNote 失败: %v", err)
	}

	links, err = s.Backlinks(tID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 0 {
		t.Fatalf("删除引用者后期望 0 条反向链接，实际 %d", len(links))
	}
}

func TestBacklinks_删目标后links残留置空(t *testing.T) {
	s := newDeepTestStore(t)
	tID := seedNote(t, s, "T", "目标笔记")
	_ = seedNote(t, s, "A", "[[T]]")

	if err := s.DeleteNote(tID); err != nil {
		t.Fatalf("DeleteNote 失败: %v", err)
	}

	links, err := s.Backlinks(tID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 0 {
		t.Fatalf("删除目标后期望 0 条反向链接，实际 %d", len(links))
	}

	var count int
	err = s.db.QueryRow("SELECT COUNT(*) FROM links WHERE target_id IS NULL AND target_title='T'").Scan(&count)
	if err != nil {
		t.Fatalf("查询残留 links 失败: %v", err)
	}
	if count != 1 {
		t.Fatalf("期望残留 1 条 target_id 为 NULL 的链接，实际 %d", count)
	}
	// 残留行是当前设计（供同名重建回填）
}

func TestBacklinks_同名重建回填(t *testing.T) {
	s := newDeepTestStore(t)
	tID := seedNote(t, s, "T", "目标笔记")
	aID := seedNote(t, s, "A", "[[T]]")

	if err := s.DeleteNote(tID); err != nil {
		t.Fatalf("DeleteNote 失败: %v", err)
	}

	t2ID := seedNote(t, s, "T", "重建目标")

	links, err := s.Backlinks(t2ID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 1 {
		t.Fatalf("同名重建后期望 1 条反向链接，实际 %d", len(links))
	}
	if links[0].ID != aID {
		t.Fatalf("期望回填到引用者 A (id=%d)，实际 id=%d", aID, links[0].ID)
	}
}

func TestBacklinks_目标改名后仍可解析(t *testing.T) {
	s := newDeepTestStore(t)
	tID := seedNote(t, s, "T", "目标内容")
	aID := seedNote(t, s, "A", "[[T]]")

	// 修改 T 的标题为 "T新"（UpdateNote 无 ctx 参数）
	if _, err := s.UpdateNote(Note{ID: tID, Title: "T新", Body: "目标内容"}); err != nil {
		t.Fatalf("UpdateNote 失败: %v", err)
	}

	links, err := s.Backlinks(tID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 1 {
		t.Fatalf("目标改名后期望 1 条反向链接，实际 %d", len(links))
	}
	// TargetTitle 保留当时 [[...]] 里的原文
	if links[0].TargetTitle != "T" {
		t.Fatalf("期望 TargetTitle 为 'T'（当时原文），实际 '%s'", links[0].TargetTitle)
	}

	bID := seedNote(t, s, "B", "[[T新]]")

	links, err = s.Backlinks(tID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 2 {
		t.Fatalf("新增引用者后期望 2 条反向链接，实际 %d", len(links))
	}
	// 按引用者 id 倒序，B 在前
	if links[0].ID != bID {
		t.Fatalf("期望第一条为 B (id=%d)，实际 id=%d", bID, links[0].ID)
	}
	if links[1].ID != aID {
		t.Fatalf("期望第二条为 A (id=%d)，实际 id=%d", aID, links[1].ID)
	}
}

func TestBacklinks_引用者改名不影响(t *testing.T) {
	s := newDeepTestStore(t)
	tID := seedNote(t, s, "T", "目标内容")
	aID := seedNote(t, s, "A", "[[T]]")

	if _, err := s.UpdateNote(Note{ID: aID, Title: "A新", Body: "[[T]]"}); err != nil {
		t.Fatalf("UpdateNote 失败: %v", err)
	}

	links, err := s.Backlinks(tID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 1 {
		t.Fatalf("引用者改名后期望 1 条反向链接，实际 %d", len(links))
	}
	if links[0].Title != "A新" {
		t.Fatalf("期望 Title 为 'A新'，实际 '%s'", links[0].Title)
	}
}

func TestBacklinks_悬空引用不污染(t *testing.T) {
	s := newDeepTestStore(t)
	aID := seedNote(t, s, "A", "[[不存在的标题]]")

	links, err := s.Backlinks(999999)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 0 {
		t.Fatalf("悬空引用目标期望 0 条反向链接，实际 %d", len(links))
	}

	links, err = s.Backlinks(aID)
	if err != nil {
		t.Fatalf("Backlinks 失败: %v", err)
	}
	if len(links) != 0 {
		t.Fatalf("悬空引用者自身期望 0 条反向链接，实际 %d", len(links))
	}
}
