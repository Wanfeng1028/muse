package store

import (
	"context"
	"testing"
)

// TestCreateNoteFor_IdempotentClientNoteID 同一幂等键重复创建返回同一笔记，不产生重复行。
func TestCreateNoteFor_IdempotentClientNoteID(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()

	first, err := s.CreateNoteFor(ctx, Note{Title: "离线笔记", Body: "b", ClientNoteID: "cid-123"}, DefaultUser)
	if err != nil {
		t.Fatalf("CreateNoteFor: %v", err)
	}
	if first.ClientNoteID != "cid-123" {
		t.Fatalf("first.ClientNoteID=%q, want cid-123", first.ClientNoteID)
	}
	second, err := s.CreateNoteFor(ctx, Note{Title: "离线笔记", Body: "b", ClientNoteID: "cid-123"}, DefaultUser)
	if err != nil {
		t.Fatalf("CreateNoteFor 重复: %v", err)
	}
	if second.ID != first.ID {
		t.Fatalf("second.ID=%d, want %d", second.ID, first.ID)
	}
	var count int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM notes`).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 1 {
		t.Fatalf("notes count=%d, want 1", count)
	}

	// 不同幂等键 → 不同笔记
	third, err := s.CreateNoteFor(ctx, Note{Title: "另一篇", Body: "b", ClientNoteID: "cid-456"}, DefaultUser)
	if err != nil {
		t.Fatalf("third: %v", err)
	}
	if third.ID == first.ID {
		t.Fatalf("third.ID 与 first 相同")
	}

	// 无幂等键 → 老行为：每次都建新行
	a, err := s.CreateNote(Note{Title: "普通", Body: "b"})
	if err != nil {
		t.Fatalf("a: %v", err)
	}
	b, err := s.CreateNote(Note{Title: "普通", Body: "b"})
	if err != nil {
		t.Fatalf("b: %v", err)
	}
	if a.ID == b.ID {
		t.Fatalf("无幂等键时应建两行")
	}

	// 过长幂等键 → 报错
	long := make([]byte, 65)
	for i := range long {
		long[i] = 'x'
	}
	if _, err := s.CreateNoteFor(ctx, Note{Title: "长", ClientNoteID: string(long)}, DefaultUser); err == nil {
		t.Fatalf("过长 clientNoteId 应报错")
	}
}
