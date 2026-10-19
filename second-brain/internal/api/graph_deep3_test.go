package api

import (
	"encoding/json"
	"net/http"
	"testing"
)

type graphResp struct {
	Nodes []struct {
		ID    int64    `json:"id"`
		Title string   `json:"title"`
		Tags  []string `json:"tags"`
	} `json:"nodes"`
	Edges []struct {
		Source int64 `json:"source"`
		Target int64 `json:"target"`
	} `json:"edges"`
}

// TestGraphAPIEmpty 验证空库返回 nodes/edges 均存在且为空数组（非 null）。
func TestGraphAPIEmpty(t *testing.T) {
	srv := newTestServer(t)

	resp := doJSON(t, srv, http.MethodGet, "/api/graph", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200, 实际 %d", resp.StatusCode)
	}

	var raw map[string]json.RawMessage
	decodeBody(t, resp, &raw)

	nodesRaw, ok := raw["nodes"]
	if !ok {
		t.Fatalf("响应缺少 nodes 字段, raw=%v", raw)
	}
	if string(nodesRaw) == "null" {
		t.Fatalf("nodes 不应为 null, 实际 %s", string(nodesRaw))
	}
	edgesRaw, ok := raw["edges"]
	if !ok {
		t.Fatalf("响应缺少 edges 字段, raw=%v", raw)
	}
	if string(edgesRaw) == "null" {
		t.Fatalf("edges 不应为 null, 实际 %s", string(edgesRaw))
	}

	var nodes []json.RawMessage
	if err := json.Unmarshal(nodesRaw, &nodes); err != nil {
		t.Fatalf("解码 nodes: %v", err)
	}
	if len(nodes) != 0 {
		t.Fatalf("期望 nodes 长度 0, 实际 %d: %s", len(nodes), string(nodesRaw))
	}
	var edges []json.RawMessage
	if err := json.Unmarshal(edgesRaw, &edges); err != nil {
		t.Fatalf("解码 edges: %v", err)
	}
	if len(edges) != 0 {
		t.Fatalf("期望 edges 长度 0, 实际 %d: %s", len(edges), string(edgesRaw))
	}
}

// TestGraphAPICycle 验证 A↔B 双链经 API 返回 2 节点 2 边且无自环。
func TestGraphAPICycle(t *testing.T) {
	srv := newTestServer(t)

	respA := doJSON(t, srv, http.MethodPost, "/api/notes",
		map[string]string{"title": "A", "body": "指向 [[B]]"})
	if respA.StatusCode != http.StatusCreated {
		t.Fatalf("创建 A 期望 201, 实际 %d", respA.StatusCode)
	}
	respA.Body.Close()

	respB := doJSON(t, srv, http.MethodPost, "/api/notes",
		map[string]string{"title": "B", "body": "指回 [[A]]"})
	if respB.StatusCode != http.StatusCreated {
		t.Fatalf("创建 B 期望 201, 实际 %d", respB.StatusCode)
	}
	respB.Body.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/graph", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200, 实际 %d", resp.StatusCode)
	}
	var g graphResp
	decodeBody(t, resp, &g)

	if len(g.Nodes) != 2 {
		t.Fatalf("期望 nodes 2 个, 实际 %d: %+v", len(g.Nodes), g.Nodes)
	}
	if len(g.Edges) != 2 {
		t.Fatalf("期望 edges 2 条, 实际 %d: %+v", len(g.Edges), g.Edges)
	}
	for _, e := range g.Edges {
		if e.Source == e.Target {
			t.Fatalf("不应有自环边, got=%+v", e)
		}
	}
}

// TestGraphAPIDangling 验证悬空链接 API 返回空 edges 数组。
func TestGraphAPIDangling(t *testing.T) {
	srv := newTestServer(t)

	respN := doJSON(t, srv, http.MethodPost, "/api/notes",
		map[string]string{"title": "Dangler", "body": "引用 [[不存在的标题xyz]]"})
	if respN.StatusCode != http.StatusCreated {
		t.Fatalf("创建 Dangler 期望 201, 实际 %d", respN.StatusCode)
	}
	respN.Body.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/graph", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200, 实际 %d", resp.StatusCode)
	}
	var raw map[string]json.RawMessage
	decodeBody(t, resp, &raw)
	edgesRaw, ok := raw["edges"]
	if !ok {
		t.Fatalf("响应缺少 edges 字段, raw=%v", raw)
	}
	if string(edgesRaw) == "null" {
		t.Fatalf("edges 不应为 null, 实际 %s", string(edgesRaw))
	}
	var edges []json.RawMessage
	if err := json.Unmarshal(edgesRaw, &edges); err != nil {
		t.Fatalf("解码 edges: %v", err)
	}
	if len(edges) != 0 {
		t.Fatalf("期望 edges 为空, 实际 %d 条: %s", len(edges), string(edgesRaw))
	}
}
