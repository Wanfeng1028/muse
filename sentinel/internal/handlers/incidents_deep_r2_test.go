package handlers

import (
	"fmt"
	"testing"
)

// 本文件为 r2 深测：incidents 列表分页三参数优先级 / 非法值降级链 / 钳制边界 /
// 分页 offset 正确性 / monitor_id 过滤 / is_public 校验回归组合边界。
// 只依赖 newTestServer / doJSON / seedIncidents 三个已存在 helper，互不依赖。

func getFloat(t *testing.T, body map[string]any, key string) float64 {
	t.Helper()
	v, ok := body[key]
	if !ok {
		t.Fatalf("响应缺少字段 %q，实际 body=%v", key, body)
	}
	f, ok := v.(float64)
	if !ok {
		t.Fatalf("字段 %q 期望 float64，实际 %T(%v)", key, v, v)
	}
	return f
}

func itemsOf(t *testing.T, body map[string]any) []any {
	t.Helper()
	v, ok := body["items"]
	if !ok {
		t.Fatalf("响应缺少 items，实际 body=%v", body)
	}
	items, ok := v.([]any)
	if !ok {
		t.Fatalf("items 期望 []any，实际 %T(%v)", v, v)
	}
	return items
}

func itemIDs(t *testing.T, items []any) []float64 {
	t.Helper()
	ids := make([]float64, 0, len(items))
	for i, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			t.Fatalf("items[%d] 期望 map[string]any，实际 %T(%v)", i, it, it)
		}
		idv, ok := m["id"]
		if !ok {
			t.Fatalf("items[%d] 缺少 id，实际 %v", i, m)
		}
		f, ok := idv.(float64)
		if !ok {
			t.Fatalf("items[%d].id 期望 float64，实际 %T(%v)", i, idv, idv)
		}
		ids = append(ids, f)
	}
	return ids
}

// ---------- A. 三参数优先级组合 ----------

func TestHandleListIncidentsR2PriorityPerPageWins(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?per_page=5&page_size=20&limit=50", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "page_size"); got != 5 {
		t.Fatalf("期望 page_size 5（per_page 胜），实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 5 {
		t.Fatalf("期望 items 长度 5，实际 %d", got)
	}
}

func TestHandleListIncidentsR2PriorityPageSizeOverLimit(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?page_size=7&limit=50", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "page_size"); got != 7 {
		t.Fatalf("期望 page_size 7（page_size 胜 limit），实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 7 {
		t.Fatalf("期望 items 长度 7，实际 %d", got)
	}
}

func TestHandleListIncidentsR2LimitResetsPage(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	// limit 分支：解析成功会 page=1。用 page=3&limit=8 验证 page 被重置为 1。
	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?page=3&limit=8", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "page_size"); got != 8 {
		t.Fatalf("期望 page_size 8（仅 limit），实际 %v", got)
	}
	if got := getFloat(t, body, "page"); got != 1 {
		t.Fatalf("期望 page 被 limit 重置为 1，实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 8 {
		t.Fatalf("期望 items 长度 8，实际 %d", got)
	}
}

// ---------- B. 非法值降级链 ----------

func TestHandleListIncidentsR2InvalidPerPageFallsToPageSize(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?per_page=abc&page_size=9", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "page_size"); got != 9 {
		t.Fatalf("期望 page_size 9（per_page 非法降级 page_size），实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 9 {
		t.Fatalf("期望 items 长度 9，实际 %d", got)
	}
}

func TestHandleListIncidentsR2InvalidPerPageAndPageSizeFallsToLimit(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?per_page=abc&page_size=xyz&limit=6", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "page_size"); got != 6 {
		t.Fatalf("期望 page_size 6（降级到 limit），实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 6 {
		t.Fatalf("期望 items 长度 6，实际 %d", got)
	}
}

func TestHandleListIncidentsR2AllInvalidFallsToDefault(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?per_page=abc&page_size=xyz&limit=zzz", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "page_size"); got != 20 {
		t.Fatalf("期望 page_size 20（全非法缺省），实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 20 {
		t.Fatalf("期望 items 长度 20，实际 %d", got)
	}
}

// ---------- C. 钳制边界 ----------

func TestHandleListIncidentsR2PageSizeClampLower(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	rec0, body0 := doJSON(t, srv.Routes(), "GET", "/api/incidents?per_page=0", "")
	if rec0.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec0.Code)
	}
	if got := getFloat(t, body0, "page_size"); got != 1 {
		t.Fatalf("期望 page_size 0 被钳制为 1，实际 %v", got)
	}

	recNeg, bodyNeg := doJSON(t, srv.Routes(), "GET", "/api/incidents?per_page=-5", "")
	if recNeg.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", recNeg.Code)
	}
	if got := getFloat(t, bodyNeg, "page_size"); got != 1 {
		t.Fatalf("期望 page_size -5 被钳制为 1，实际 %v", got)
	}
}

func TestHandleListIncidentsR2PageSizeClampUpper(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 5)

	rec100, body100 := doJSON(t, srv.Routes(), "GET", "/api/incidents?per_page=100", "")
	if rec100.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec100.Code)
	}
	if got := getFloat(t, body100, "page_size"); got != 100 {
		t.Fatalf("期望 page_size 100（上界保留），实际 %v", got)
	}

	rec101, body101 := doJSON(t, srv.Routes(), "GET", "/api/incidents?per_page=101", "")
	if rec101.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec101.Code)
	}
	if got := getFloat(t, body101, "page_size"); got != 100 {
		t.Fatalf("期望 page_size 101 被钳制为 100，实际 %v", got)
	}

	recBig, bodyBig := doJSON(t, srv.Routes(), "GET", "/api/incidents?page_size=99999", "")
	if recBig.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", recBig.Code)
	}
	if got := getFloat(t, bodyBig, "page_size"); got != 100 {
		t.Fatalf("期望 page_size 99999 被钳制为 100，实际 %v", got)
	}
}

func TestHandleListIncidentsR2PageClampInvalid(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 30)

	cases := []string{"page=0", "page=-2", "page=abc"}
	for _, q := range cases {
		rec, body := doJSON(t, srv.Routes(), "GET", "/api/incidents?"+q, "")
		if rec.Code != 200 {
			t.Fatalf("query %q 期望状态码 200，实际 %d", q, rec.Code)
		}
		if got := getFloat(t, body, "page"); got != 1 {
			t.Fatalf("query %q 期望 page 钳制为 1，实际 %v", q, got)
		}
	}
}

// ---------- D. 分页正确性 ----------

func TestHandleListIncidentsR2PaginationNoOverlap(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec1, body1 := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?page=1&per_page=10", "")
	if rec1.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec1.Code)
	}
	if got := getFloat(t, body1, "total"); got != 45 {
		t.Fatalf("期望 total 45，实际 %v", got)
	}
	if got := len(itemsOf(t, body1)); got != 10 {
		t.Fatalf("page=1 期望 items 长度 10，实际 %d", got)
	}

	rec2, body2 := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?page=2&per_page=10", "")
	if rec2.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec2.Code)
	}
	if got := getFloat(t, body2, "page"); got != 2 {
		t.Fatalf("期望 page 2，实际 %v", got)
	}
	if got := len(itemsOf(t, body2)); got != 10 {
		t.Fatalf("page=2 期望 items 长度 10，实际 %d", got)
	}

	ids1 := itemIDs(t, itemsOf(t, body1))
	ids2 := itemIDs(t, itemsOf(t, body2))
	seen := map[float64]bool{}
	for _, id := range ids1 {
		seen[id] = true
	}
	for _, id := range ids2 {
		if seen[id] {
			t.Fatalf("page=1 与 page=2 出现重复 id %v，offset 未生效", id)
		}
	}
}

func TestHandleListIncidentsR2PaginationLastPageRemainder(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?page=5&per_page=10", "")
	if rec.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := getFloat(t, body, "total"); got != 45 {
		t.Fatalf("期望 total 45，实际 %v", got)
	}
	if got := getFloat(t, body, "page"); got != 5 {
		t.Fatalf("期望 page 5，实际 %v", got)
	}
	if got := len(itemsOf(t, body)); got != 5 {
		t.Fatalf("最后一页期望 items 长度 5（45 的余数），实际 %d", got)
	}
}

func TestHandleListIncidentsR2MonitorIDFilter(t *testing.T) {
	srv, st := newTestServer(t)
	mid := seedIncidents(t, st, 45)

	recHit, bodyHit := doJSON(t, srv.Routes(), "GET",
		fmt.Sprintf("/api/incidents?monitor_id=%d", mid), "")
	if recHit.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", recHit.Code)
	}
	if got := getFloat(t, bodyHit, "total"); got != 45 {
		t.Fatalf("期望 monitor_id=%d 时 total 45，实际 %v", mid, got)
	}

	recMiss, bodyMiss := doJSON(t, srv.Routes(), "GET",
		"/api/incidents?monitor_id=999999", "")
	if recMiss.Code != 200 {
		t.Fatalf("期望状态码 200，实际 %d", recMiss.Code)
	}
	if got := getFloat(t, bodyMiss, "total"); got != 0 {
		t.Fatalf("期望 monitor_id=999999 时 total 0，实际 %v", got)
	}
	items := itemsOf(t, bodyMiss)
	if len(items) != 0 {
		t.Fatalf("期望 monitor_id=999999 时 items 为空数组，实际长度 %d", len(items))
	}
}

// ---------- E. is_public 回归组合边界 ----------

func TestCreateMonitorR2InvalidIsPublicCombos(t *testing.T) {
	srv, _ := newTestServer(t)

	cases := []struct {
		name string
		body string
	}{
		{"is_public=2", `{"name":"m1","kind":"http","target":"http://127.0.0.1:1/health","is_public":2}`},
		{"is_public=-1", `{"name":"m2","kind":"http","target":"http://127.0.0.1:1/health","is_public":-1}`},
	}
	for _, tc := range cases {
		rec, _ := doJSON(t, srv.Routes(), "POST", "/api/monitors", tc.body)
		if rec.Code != 400 {
			t.Fatalf("%s 期望状态码 400，实际 %d", tc.name, rec.Code)
		}
	}
}

func TestUpdateMonitorR2InvalidIsPublicKeepsDBValue(t *testing.T) {
	srv, st := newTestServer(t)

	// 先合法创建一个 is_public=1 的监控。
	recCreate, bodyCreate := doJSON(t, srv.Routes(), "POST", "/api/monitors",
		`{"name":"keep","kind":"http","target":"http://127.0.0.1:1/health","is_public":1}`)
	if recCreate.Code != 200 && recCreate.Code != 201 {
		t.Fatalf("创建监控期望 200/201，实际 %d", recCreate.Code)
	}
	idf, ok := bodyCreate["id"].(float64)
	if !ok {
		// 兼容部分实现把创建结果包裹在 data 里
		if data, ok2 := bodyCreate["data"].(map[string]any); ok2 {
			idf, ok = data["id"].(float64)
		}
	}
	if !ok {
		t.Fatalf("创建响应缺少 id，实际 body=%v", bodyCreate)
	}
	mid := int64(idf)

	// PUT is_public=2 应被校验拒绝。
	recUpd, _ := doJSON(t, srv.Routes(), "PUT",
		fmt.Sprintf("/api/monitors/%d", mid),
		`{"name":"keep","kind":"http","target":"http://127.0.0.1:1/health","is_public":2}`)
	if recUpd.Code != 400 {
		t.Fatalf("PUT is_public=2 期望状态码 400，实际 %d", recUpd.Code)
	}

	// 回查 DB，值必须不变。
	m, err := st.GetMonitor(mid)
	if err != nil {
		t.Fatalf("回查监控失败：%v", err)
	}
	if m.IsPublic != 1 {
		t.Fatalf("PUT 非法值后期望 DB is_public 保持 1，实际 %d", m.IsPublic)
	}
}

func TestUpdateMonitorR2ValidIsPublicFlip(t *testing.T) {
	srv, st := newTestServer(t)

	recCreate, bodyCreate := doJSON(t, srv.Routes(), "POST", "/api/monitors",
		`{"name":"flip","kind":"http","target":"http://127.0.0.1:1/health","is_public":1}`)
	if recCreate.Code != 200 && recCreate.Code != 201 {
		t.Fatalf("创建监控期望 200/201，实际 %d", recCreate.Code)
	}
	idf, ok := bodyCreate["id"].(float64)
	if !ok {
		if data, ok2 := bodyCreate["data"].(map[string]any); ok2 {
			idf, ok = data["id"].(float64)
		}
	}
	if !ok {
		t.Fatalf("创建响应缺少 id，实际 body=%v", bodyCreate)
	}
	mid := int64(idf)

	recUpd, _ := doJSON(t, srv.Routes(), "PUT",
		fmt.Sprintf("/api/monitors/%d", mid),
		`{"name":"flip","kind":"http","target":"http://127.0.0.1:1/health","is_public":0}`)
	if recUpd.Code != 200 {
		t.Fatalf("PUT is_public=0 合法翻转期望状态码 200，实际 %d", recUpd.Code)
	}

	m, err := st.GetMonitor(mid)
	if err != nil {
		t.Fatalf("回查监控失败：%v", err)
	}
	if m.IsPublic != 0 {
		t.Fatalf("合法翻转后期望 DB is_public=0，实际 %d", m.IsPublic)
	}
}
