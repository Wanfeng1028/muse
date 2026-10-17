package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func renderPasswordPageForTest(slug, errMsg string, status int) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	renderPasswordPage(rec, slug, errMsg, status)
	return rec
}

func TestPasswordPageContentTypeAndStatus(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "", http.StatusOK)

	if rec.Code != http.StatusOK {
		t.Fatalf("状态码期望 %d，实际 %d", http.StatusOK, rec.Code)
	}
	gotCT := rec.Header().Get("Content-Type")
	if gotCT != "text/html; charset=utf-8" {
		t.Fatalf("Content-Type 期望 %q，实际 %q", "text/html; charset=utf-8", gotCT)
	}
}

func TestPasswordPageStatusForbidden(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "密码不对", http.StatusForbidden)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("状态码期望 %d，实际 %d", http.StatusForbidden, rec.Code)
	}
	body := rec.Body.String()
	if !strings.Contains(body, "密码不对") {
		t.Fatalf("错误信息应出现在页面中，实际页面：%s", body)
	}
}

func TestPasswordPageFormActionUsesEscapedSlug(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "", http.StatusOK)
	body := rec.Body.String()

	if !strings.Contains(body, `action="/abc123"`) {
		t.Fatalf("表单 action 应指向 /abc123，实际页面：%s", body)
	}
	if !strings.Contains(body, `<span class="mono">abc123</span>`) {
		t.Fatalf("页脚应展示短码 abc123，实际页面：%s", body)
	}
}

func TestPasswordPageEscapesSlugHTML(t *testing.T) {
	rec := renderPasswordPageForTest(`a"><script>alert(1)</script>`, "", http.StatusOK)
	body := rec.Body.String()

	if strings.Contains(body, `<script>alert(1)</script>`) {
		t.Fatalf("slug 中的脚本标签必须被转义，实际页面：%s", body)
	}
	if !strings.Contains(body, `a&#34;&gt;&lt;script&gt;alert(1)&lt;/script&gt;`) {
		t.Fatalf("slug 应被 HTML 转义后输出，实际页面：%s", body)
	}
}

func TestPasswordPageEscapesErrMsgHTML(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", `<img src=x onerror=alert(1)>`, http.StatusForbidden)
	body := rec.Body.String()

	if strings.Contains(body, `<img src=x onerror=alert(1)>`) {
		t.Fatalf("errMsg 中的 img 标签必须被转义，实际页面：%s", body)
	}
	if !strings.Contains(body, `&lt;img src=x onerror=alert(1)&gt;`) {
		t.Fatalf("errMsg 应被 HTML 转义后输出，实际页面：%s", body)
	}
}

func TestPasswordPageEmptyErrMsgOmitsErrorParagraph(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "", http.StatusOK)
	body := rec.Body.String()

	if strings.Contains(body, `class="gate-err"`) {
		t.Fatalf("空错误信息不应渲染 gate-err 段落，实际页面：%s", body)
	}
	if !strings.Contains(body, `class="gate-hint"`) {
		t.Fatalf("提示段落应始终渲染，实际页面：%s", body)
	}
}

func TestPasswordPageNonEmptyErrMsgRendersErrorParagraph(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "密码错误", http.StatusForbidden)
	body := rec.Body.String()

	if !strings.Contains(body, `class="gate-err"`) {
		t.Fatalf("非空错误信息应渲染 gate-err 段落，实际页面：%s", body)
	}
	if !strings.Contains(body, `密码错误`) {
		t.Fatalf("错误信息文本应出现在页面中，实际页面：%s", body)
	}
}

func TestPasswordPagePasswordInputAttributes(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "", http.StatusOK)
	body := rec.Body.String()

	if !strings.Contains(body, `type="password"`) {
		t.Fatalf("应渲染 password 类型输入框，实际页面：%s", body)
	}
	if !strings.Contains(body, `name="password"`) {
		t.Fatalf("输入框 name 应为 password，实际页面：%s", body)
	}
	if !strings.Contains(body, `required`) {
		t.Fatalf("输入框应带 required 属性，实际页面：%s", body)
	}
}

func TestPasswordPageFormMethodIsPost(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "", http.StatusOK)
	body := rec.Body.String()

	if !strings.Contains(body, `method="post"`) {
		t.Fatalf("表单 method 应为 post，实际页面：%s", body)
	}
	if !strings.Contains(body, `type="submit"`) {
		t.Fatalf("应渲染提交按钮，实际页面：%s", body)
	}
}

func TestPasswordPageTitleAndHead(t *testing.T) {
	rec := renderPasswordPageForTest("abc123", "", http.StatusOK)
	body := rec.Body.String()

	if !strings.Contains(body, `<!DOCTYPE html>`) {
		t.Fatalf("页面应以 DOCTYPE 开头，实际页面：%s", body)
	}
	if !strings.Contains(body, `<title>该链接受密码保护 · 短链</title>`) {
		t.Fatalf("标题应正确渲染，实际页面：%s", body)
	}
	if !strings.Contains(body, `<meta charset="utf-8">`) {
		t.Fatalf("应包含 utf-8 字符集声明，实际页面：%s", body)
	}
}

func TestPasswordPageSlugWithSpecialCharsInFooter(t *testing.T) {
	rec := renderPasswordPageForTest("a&b", "", http.StatusOK)
	body := rec.Body.String()

	if !strings.Contains(body, `<span class="mono">a&amp;b</span>`) {
		t.Fatalf("页脚短码中的 & 应转义为 &amp;，实际页面：%s", body)
	}
	if !strings.Contains(body, `action="/a&amp;b"`) {
		t.Fatalf("表单 action 中的 & 应转义为 &amp;，实际页面：%s", body)
	}
}

func TestPasswordPageConcurrentRenderRaceSafe(t *testing.T) {
	const workers = 8
	done := make(chan *httptest.ResponseRecorder, workers)

	for i := 0; i < workers; i++ {
		go func(n int) {
			rec := renderPasswordPageForTest("slug"+string(rune('0'+n)), "err", http.StatusForbidden)
			done <- rec
		}(i)
	}

	for i := 0; i < workers; i++ {
		rec := <-done
		if rec.Code != http.StatusForbidden {
			t.Fatalf("并发渲染状态码期望 %d，实际 %d", http.StatusForbidden, rec.Code)
		}
		if rec.Header().Get("Content-Type") != "text/html; charset=utf-8" {
			t.Fatalf("并发渲染 Content-Type 不一致，实际 %q", rec.Header().Get("Content-Type"))
		}
	}
}
