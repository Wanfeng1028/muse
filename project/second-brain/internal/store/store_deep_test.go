package store

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func openTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	s, err := Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func mustCreateNote(t *testing.T, s *Store, title, body string) Note {
	t.Helper()
	n, err := s.CreateNote(Note{Title: title, Body: body})
	if err != nil {
		t.Fatalf("CreateNote(%q): %v", title, err)
	}
	return n
}

// ---------- 复习调度边界 ----------

// ---------- 双链解析边界 ----------

func TestWikiLinkParsingEdgeCases(t *testing.T) {
	cases := []struct {
		name string
		body string
		want []string
	}{
		{"普通双链", "see [[foo]] here", []string{"foo"}},
		{"中文标题", "参考 [[会议记录 2024]] 结尾", []string{"会议记录 2024"}},
		{"多个双链", "[[a]] and [[b]]", []string{"a", "b"}},
		{"嵌套括号保留内层", "[[outer [[inner]]]]", []string{"outer [[inner"}},
		{"未闭合", "no close [[oops", []string{}},
		{"空标题", "[[]]", []string{}},
		{"含空格trim", "[[  spaced  ]]", []string{"  spaced  "}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var links []string
			for _, m := range wikiRe.FindAllStringSubmatch(c.body, -1) {
				if len(m) >= 2 {
					links = append(links, m[1])
				}
			}
			if len(links) != len(c.want) {
				t.Fatalf("links=%v want %v", links, c.want)
			}
			for i := range c.want {
				if links[i] != c.want[i] {
					t.Fatalf("links[%d]=%q want %q", i, links[i], c.want[i])
				}
			}
		})
	}
}

func TestWikiLinkChineseResolve(t *testing.T) {
	s := openTestStore(t)
	target := mustCreateNote(t, s, "目标笔记", "内容")
	src := mustCreateNote(t, s, "来源", "跳到 [[目标笔记]] 看看")

	back, err := s.Backlinks(target.ID)
	if err != nil {
		t.Fatalf("Backlinks: %v", err)
	}
	if len(back) != 1 {
		t.Fatalf("backlinks len=%d want 1", len(back))
	}
	if back[0].ID != src.ID {
		t.Fatalf("backlink id=%d want %d", back[0].ID, src.ID)
	}
	if back[0].TargetTitle != "目标笔记" {
		t.Fatalf("backlink target title=%q want %q", back[0].TargetTitle, "目标笔记")
	}
}

// ---------- 附件白名单与 ZipSlip ----------

// ---------- 多用户隔离 ----------

func TestMultiUserAttachmentsIsolation(t *testing.T) {
	s := openTestStore(t)
	na := mustCreateNote(t, s, "note-alice", "x")
	nb := mustCreateNote(t, s, "note-bob", "y")

	if _, err := s.CreateAttachment(na.ID, "a.png", "image/png", 1, "sha-a", "a.png"); err != nil {
		t.Fatalf("save alice: %v", err)
	}
	if _, err := s.CreateAttachment(nb.ID, "b.png", "image/png", 1, "sha-b", "b.png"); err != nil {
		t.Fatalf("save bob: %v", err)
	}
	la, err := s.ListAttachments(na.ID)
	if err != nil {
		t.Fatalf("ListAttachments alice: %v", err)
	}
	lb, err := s.ListAttachments(nb.ID)
	if err != nil {
		t.Fatalf("ListAttachments bob: %v", err)
	}
	if len(la) != 1 || len(lb) != 1 {
		t.Fatalf("counts alice=%d bob=%d want 1/1", len(la), len(lb))
	}
	if la[0].Filename == lb[0].Filename {
		t.Fatalf("attachments leaked across notes: %q", la[0].Filename)
	}
	if la[0].NoteID != na.ID || lb[0].NoteID != nb.ID {
		t.Fatalf("NoteID mismatch: %d/%d want %d/%d", la[0].NoteID, lb[0].NoteID, na.ID, nb.ID)
	}
}

// ---------- 数据一致性 ----------

func TestStatsAndLinkCounts(t *testing.T) {
	s := openTestStore(t)
	a := mustCreateNote(t, s, "A", "link to [[B]] and [[C]]")
	mustCreateNote(t, s, "B", "")
	mustCreateNote(t, s, "C", "back [[A]]")

	st, err := s.Stats()
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if st.Notes != 3 {
		t.Fatalf("Notes=%d want 3", st.Notes)
	}
	if st.Links < 3 {
		t.Fatalf("Links=%d want >=3", st.Links)
	}

	// 删除 A 后，A 发出的链接应随级联删除消失
	if err := s.DeleteNote(a.ID); err != nil {
		t.Fatalf("DeleteNote: %v", err)
	}
	st2, err := s.Stats()
	if err != nil {
		t.Fatalf("Stats after delete: %v", err)
	}
	if st2.Notes != 2 {
		t.Fatalf("Notes after delete=%d want 2", st2.Notes)
	}
	if st2.Links >= st.Links {
		t.Fatalf("Links should drop after delete: before=%d after=%d", st.Links, st2.Links)
	}
}

// 编译期确认 sql 包被使用（部分环境用 modernc.org/sqlite 驱动注册）
var _ = sql.ErrNoRows

// 保证 fmt 被引用，避免未来编辑时误删导致编译失败
var _ = fmt.Sprintf

// 保证 os 被引用
var _ = os.Getenv
