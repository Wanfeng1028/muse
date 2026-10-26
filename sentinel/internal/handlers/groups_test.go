package handlers

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

func TestCreateGroupHandlerOKAndRejects(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"核心业务"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建期望 201，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	if id, ok := out["id"].(float64); !ok || id <= 0 {
		t.Fatalf("期望返回正 id，得到 %v", out["id"])
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"核心业务"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("重名期望 400，得到 %d", rec.Code)
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"   "}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("空名期望 400，得到 %d", rec.Code)
	}
	rec, out = doJSON(t, srv.Routes(), http.MethodGet, "/api/groups", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("列表期望 200，得到 %d", rec.Code)
	}
	items, ok := out["items"].([]any)
	if !ok || len(items) != 1 {
		t.Fatalf("期望列表 1 条，得到 %v", out["items"])
	}
}

func TestGroupMembersHandlerFlow(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"组A"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("建组期望 201，得到 %d", rec.Code)
	}
	gid := int64(out["id"].(float64))
	rec, _ = doJSON(t, srv.Routes(), http.MethodPost, fmt.Sprintf("/api/groups/%d/monitors", gid), fmt.Sprintf(`{"monitor_id":%d}`, mid))
	if rec.Code != http.StatusOK {
		t.Fatalf("加入期望 200，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodPost, fmt.Sprintf("/api/groups/%d/monitors", gid), `{"monitor_id":999999}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("不存在的监控加入期望 400，得到 %d", rec.Code)
	}
	rec, out = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/groups/%d/monitors", gid), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("成员列表期望 200，得到 %d", rec.Code)
	}
	items, ok := out["items"].([]any)
	if !ok || len(items) != 1 {
		t.Fatalf("期望成员 1 条，得到 %v", out["items"])
	}
	req := newReq(http.MethodDelete, fmt.Sprintf("/api/groups/%d/monitors/%d", gid, mid), nil)
	delRec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(delRec, req)
	if delRec.Code != http.StatusOK {
		t.Fatalf("移出期望 200，得到 %d body=%s", delRec.Code, delRec.Body.String())
	}
	req = newReq(http.MethodDelete, fmt.Sprintf("/api/groups/%d", gid), nil)
	delRec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(delRec, req)
	if delRec.Code != http.StatusOK {
		t.Fatalf("删组期望 200，得到 %d", delRec.Code)
	}
	rec, out = doJSON(t, srv.Routes(), http.MethodGet, "/api/groups", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("删组后列表期望 200，得到 %d", rec.Code)
	}
	items, ok = out["items"].([]any)
	if !ok || len(items) != 0 {
		t.Fatalf("删组后期望 0 条，得到 %v", out["items"])
	}
}
