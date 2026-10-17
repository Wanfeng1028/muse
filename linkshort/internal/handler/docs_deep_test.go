package handler

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

func newDocsRecorder() *httptest.ResponseRecorder {
	return httptest.NewRecorder()
}

func TestDocsDeepHappyPathContentTypeAndBody(t *testing.T) {
	rec := newDocsRecorder()
	req := httptest.NewRequest(http.MethodGet, "/docs", nil)

	handleDocs(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := rec.Header().Get("Content-Type"); got != "text/html; charset=utf-8" {
		t.Fatalf("期望 Content-Type 为 text/html; charset=utf-8，实际 %q", got)
	}
	body := rec.Body.String()
	if body == "" {
		t.Fatalf("期望响应体非空，实际为空")
	}
	if !strings.Contains(strings.ToLower(body), "<html") && !strings.Contains(strings.ToLower(body), "<!doctype") {
		t.Fatalf("期望响应体是 HTML 文档，实际前 64 字节为 %q", firstN(body, 64))
	}
}

func TestDocsDeepBodyMatchesEmbeddedAsset(t *testing.T) {
	want, err := webFS.ReadFile("web/docs.html")
	if err != nil {
		t.Fatalf("读取内嵌 web/docs.html 失败: %v", err)
	}

	rec := newDocsRecorder()
	req := httptest.NewRequest(http.MethodGet, "/docs", nil)
	handleDocs(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if got := rec.Body.Bytes(); string(got) != string(want) {
		t.Fatalf("期望响应体与内嵌 web/docs.html 完全一致，长度 got=%d want=%d", len(got), len(want))
	}
}

func TestDocsDeepContentLengthConsistency(t *testing.T) {
	want, err := webFS.ReadFile("web/docs.html")
	if err != nil {
		t.Fatalf("读取内嵌 web/docs.html 失败: %v", err)
	}

	rec := newDocsRecorder()
	req := httptest.NewRequest(http.MethodGet, "/docs", nil)
	handleDocs(rec, req)

	if rec.Body.Len() != len(want) {
		t.Fatalf("期望响应体长度 %d，实际 %d", len(want), rec.Body.Len())
	}
	read, err := io.ReadAll(rec.Body)
	if err != nil {
		t.Fatalf("读取响应体失败: %v", err)
	}
	if string(read) != string(want) {
		t.Fatalf("响应体与内嵌文件不一致，got=%d want=%d", len(read), len(want))
	}
}

func TestDocsDeepDoesNotLeakErrorOnSuccess(t *testing.T) {
	rec := newDocsRecorder()
	req := httptest.NewRequest(http.MethodGet, "/docs", nil)
	handleDocs(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
	if strings.Contains(rec.Body.String(), "docs not available") {
		t.Fatalf("成功路径不应出现错误文案 %q", "docs not available")
	}
}

func TestDocsDeepSupportsHeadMethod(t *testing.T) {
	rec := newDocsRecorder()
	req := httptest.NewRequest(http.MethodHead, "/docs", nil)
	handleDocs(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("HEAD 期望状态码 200，实际 %d", rec.Code)
	}
	if got := rec.Header().Get("Content-Type"); got != "text/html; charset=utf-8" {
		t.Fatalf("HEAD 期望 Content-Type 为 text/html; charset=utf-8，实际 %q", got)
	}
}

func TestDocsDeepIgnoresQueryAndPath(t *testing.T) {
	recA := newDocsRecorder()
	reqA := httptest.NewRequest(http.MethodGet, "/docs?x=1&y=2", nil)
	handleDocs(recA, reqA)

	recB := newDocsRecorder()
	reqB := httptest.NewRequest(http.MethodGet, "/some/other/path", nil)
	handleDocs(recB, reqB)

	if recA.Code != http.StatusOK || recB.Code != http.StatusOK {
		t.Fatalf("期望两次请求状态码均为 200，实际 %d 与 %d", recA.Code, recB.Code)
	}
	if recA.Body.String() != recB.Body.String() {
		t.Fatalf("期望不同路径/查询参数返回相同内容，长度 %d 与 %d", recA.Body.Len(), recB.Body.Len())
	}
}

func TestDocsDeepConcurrentRequestsAreRaceFree(t *testing.T) {
	want, err := webFS.ReadFile("web/docs.html")
	if err != nil {
		t.Fatalf("读取内嵌 web/docs.html 失败: %v", err)
	}

	const goroutines = 32
	var wg sync.WaitGroup
	wg.Add(goroutines)
	errs := make(chan string, goroutines)

	for i := 0; i < goroutines; i++ {
		go func(idx int) {
			defer wg.Done()
			rec := newDocsRecorder()
			req := httptest.NewRequest(http.MethodGet, "/docs", nil)
			handleDocs(rec, req)
			if rec.Code != http.StatusOK {
				errs <- "并发请求状态码不是 200"
				return
			}
			if rec.Body.String() != string(want) {
				errs <- "并发请求响应体与内嵌文件不一致"
				return
			}
		}(i)
	}
	wg.Wait()
	close(errs)

	for msg := range errs {
		t.Fatalf("并发用例失败: %s", msg)
	}
}

func TestDocsDeepRepeatedCallsAreIdempotent(t *testing.T) {
	var first string
	for i := 0; i < 5; i++ {
		rec := newDocsRecorder()
		req := httptest.NewRequest(http.MethodGet, "/docs", nil)
		handleDocs(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("第 %d 次调用期望状态码 200，实际 %d", i, rec.Code)
		}
		body := rec.Body.String()
		if i == 0 {
			first = body
			continue
		}
		if body != first {
			t.Fatalf("第 %d 次调用响应体与首次不一致，长度 %d 与 %d", i, len(body), len(first))
		}
	}
	if first == "" {
		t.Fatalf("期望首次响应体非空")
	}
}

func TestDocsDeepBodyHasNoErrorPlaceholder(t *testing.T) {
	rec := newDocsRecorder()
	req := httptest.NewRequest(http.MethodGet, "/docs", nil)
	handleDocs(rec, req)

	body := rec.Body.String()
	if strings.Contains(body, "TODO") {
		t.Fatalf("响应体不应包含 TODO 占位")
	}
	if strings.Contains(body, "略") {
		t.Fatalf("响应体不应包含省略标记")
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际 %d", rec.Code)
	}
}

func firstN(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
