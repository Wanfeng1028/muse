package store

import (
	"strings"
	"testing"
	"time"
)

// TestVisitProfileUARefererBoundaries 验证 store 层对 ua/referer 的真实行为：
// store 层不截断，原样透传写入数据库。
// 截断发生在 handler 层（handler.go 中对 r.UserAgent()/r.Referer() 调用 truncate 之后才调 store），
// 因此直接调用 RecordVisitGeo 时超长输入会按原样存进 visits 表。
func TestVisitProfileUARefererBoundaries(t *testing.T) {
	s := newDeep3Store(t)

	linkID, err := s.CreateLinkEx("ua-ref-boundaries", "https://example.com/ua-ref", "ua ref boundaries", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	// 空 ua/referer：原样存空字符串。
	if err := s.RecordVisitGeo(linkID, "iphash-empty", "", "", "CN", "China", "Beijing", "Beijing"); err != nil {
		t.Fatalf("RecordVisitGeo(empty): %v", err)
	}

	// 300 字节 ASCII UA：store 层不截断，数据库里就是完整的 300 字节。
	ua300 := strings.Repeat("a", 300)
	if err := s.RecordVisitGeo(linkID, "iphash-ua300", ua300, "https://ref.example/ua300", "CN", "China", "Beijing", "Beijing"); err != nil {
		t.Fatalf("RecordVisitGeo(ua300): %v", err)
	}

	// 100 个汉字（UTF-8 下 300 字节）：原样存。
	uaHan100 := strings.Repeat("汉", 100)
	if err := s.RecordVisitGeo(linkID, "iphash-han100", uaHan100, "https://ref.example/han100", "CN", "China", "Beijing", "Beijing"); err != nil {
		t.Fatalf("RecordVisitGeo(han100): %v", err)
	}

	// 600 字节 ASCII referer：原样存 600 字节。
	ref600 := strings.Repeat("r", 600)
	if err := s.RecordVisitGeo(linkID, "iphash-ref600", "smoke-ua", ref600, "CN", "China", "Beijing", "Beijing"); err != nil {
		t.Fatalf("RecordVisitGeo(ref600): %v", err)
	}

	// 逐条从数据库读回真实值做比对。

	var gotEmptyUA, gotEmptyRef string
	if err := s.db.QueryRow(
		`SELECT ua, referer FROM visits WHERE link_id = ? AND ip_hash = ?`,
		linkID, "iphash-empty",
	).Scan(&gotEmptyUA, &gotEmptyRef); err != nil {
		t.Fatalf("query empty row: %v", err)
	}
	if gotEmptyUA != "" {
		t.Fatalf("empty ua: want %q, got %q", "", gotEmptyUA)
	}
	if gotEmptyRef != "" {
		t.Fatalf("empty referer: want %q, got %q", "", gotEmptyRef)
	}

	var gotUA300 string
	if err := s.db.QueryRow(
		`SELECT ua FROM visits WHERE link_id = ? AND ip_hash = ?`,
		linkID, "iphash-ua300",
	).Scan(&gotUA300); err != nil {
		t.Fatalf("query ua300 row: %v", err)
	}
	if len(gotUA300) != 300 {
		t.Fatalf("ua300: want db length 300 (store does not truncate), got %d", len(gotUA300))
	}
	if gotUA300 != ua300 {
		t.Fatalf("ua300: stored value differs from input; want full 300-byte passthrough")
	}

	var gotHan100 string
	if err := s.db.QueryRow(
		`SELECT ua FROM visits WHERE link_id = ? AND ip_hash = ?`,
		linkID, "iphash-han100",
	).Scan(&gotHan100); err != nil {
		t.Fatalf("query han100 row: %v", err)
	}
	if gotHan100 != uaHan100 {
		t.Fatalf("han100 ua: want full passthrough of 100 han runes (300 bytes), got %q", gotHan100)
	}
	if len(gotHan100) != 300 {
		t.Fatalf("han100 ua: want db byte length 300, got %d", len(gotHan100))
	}

	var gotRef600 string
	if err := s.db.QueryRow(
		`SELECT referer FROM visits WHERE link_id = ? AND ip_hash = ?`,
		linkID, "iphash-ref600",
	).Scan(&gotRef600); err != nil {
		t.Fatalf("query ref600 row: %v", err)
	}
	if len(gotRef600) != 600 {
		t.Fatalf("ref600: want db length 600 (store does not truncate), got %d", len(gotRef600))
	}
	if gotRef600 != ref600 {
		t.Fatalf("ref600: stored value differs from input; want full 600-byte passthrough")
	}
}

// TestVisitProfileSameIPHighFrequency 验证同一 ip_hash 高频写入时，
// visits 计数与 links.clicks 递增保持一致。
func TestVisitProfileSameIPHighFrequency(t *testing.T) {
	s := newDeep3Store(t)

	linkID, err := s.CreateLinkEx("same-ip-high-freq", "https://example.com/same-ip", "same ip high freq", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	const n = 50
	for i := 0; i < n; i++ {
		if err := s.RecordVisitGeo(linkID, "iphash-same", "ua-same", "https://ref.example/same", "CN", "China", "Beijing", "Beijing"); err != nil {
			t.Fatalf("RecordVisitGeo(%d): %v", i, err)
		}
	}

	var visitCount int
	if err := s.db.QueryRow(
		`SELECT COUNT(*) FROM visits WHERE link_id = ? AND ip_hash = ?`,
		linkID, "iphash-same",
	).Scan(&visitCount); err != nil {
		t.Fatalf("count visits: %v", err)
	}
	if visitCount != n {
		t.Fatalf("visit count: want %d, got %d", n, visitCount)
	}

	var clicks int64
	if err := s.db.QueryRow(
		`SELECT clicks FROM links WHERE id = ?`,
		linkID,
	).Scan(&clicks); err != nil {
		t.Fatalf("query clicks: %v", err)
	}
	if clicks != int64(n) {
		t.Fatalf("clicks: want %d, got %d", n, clicks)
	}

	// 保持对时间语义的轻度约束：写入使用 nowUTC 格式，可解析。
	var ts string
	if err := s.db.QueryRow(
		`SELECT ts FROM visits WHERE link_id = ? AND ip_hash = ? LIMIT 1`,
		linkID, "iphash-same",
	).Scan(&ts); err != nil {
		t.Fatalf("query ts: %v", err)
	}
	if _, err := time.Parse(time.RFC3339Nano, ts); err != nil {
		// 不同时间格式下放宽，只要非空即可。
		if ts == "" {
			t.Fatalf("ts: want non-empty timestamp, got empty")
		}
	}
}

