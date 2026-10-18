package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func deep3Render(slug, errMsg string, status int) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	renderPasswordPage(rec, slug, errMsg, status)
	return rec
}

func TestDeep3PasswordPageHeaderWrittenBeforeBody(t *testing.T) {
	rec := deep3Render("slug", "", http.StatusTeapot)
	if rec.Code != http.StatusTeapot {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusTeapot)
	}
	if got := rec.Header().Get("Content-Type"); got != "text/html; charset=utf-8" {
		t.Fatalf("Content-Type = %q, want text/html; charset=utf-8", got)
	}
	body := rec.Body.String()
	if !strings.HasPrefix(body, "<!DOCTYPE html>") {
		t.Fatalf("body should start with doctype, got prefix %q", body[:min(30, len(body))])
	}
}

func TestDeep3PasswordPageEmptySlugStillRendersForm(t *testing.T) {
	rec := deep3Render("", "", http.StatusOK)
	body := rec.Body.String()
	if !strings.Contains(body, `action="/"`) {
		t.Fatalf("empty slug should yield action=\"/\", body: %s", body)
	}
	if !strings.Contains(body, `<span class="mono"></span>`) {
		t.Fatalf("empty slug footer span should be empty, body: %s", body)
	}
	if strings.Contains(body, `class="gate-err"`) {
		t.Fatalf("no errMsg should not render gate-err, body: %s", body)
	}
}

func TestDeep3PasswordPageWhitespaceErrMsgRenders(t *testing.T) {
	rec := deep3Render("slug", " ", http.StatusUnauthorized)
	body := rec.Body.String()
	if !strings.Contains(body, `class="gate-err"`) {
		t.Fatalf("whitespace errMsg is non-empty and should render gate-err, body: %s", body)
	}
	if !strings.Contains(body, `<p class="gate-err"> </p>`) {
		t.Fatalf("whitespace errMsg should be preserved, body: %s", body)
	}
}

func TestDeep3PasswordPageVeryLongSlugRenderedFully(t *testing.T) {
	long := strings.Repeat("x", 5000)
	rec := deep3Render(long, "", http.StatusOK)
	body := rec.Body.String()
	if strings.Count(body, long) != 2 {
		t.Fatalf("long slug should appear twice (form action + footer), count = %d", strings.Count(body, long))
	}
	if !strings.Contains(body, `action="/`+long+`"`) {
		t.Fatalf("long slug should be in form action")
	}
}

func TestDeep3PasswordPageVeryLongErrMsgRenderedFully(t *testing.T) {
	long := strings.Repeat("e", 4000)
	rec := deep3Render("slug", long, http.StatusUnauthorized)
	body := rec.Body.String()
	if !strings.Contains(body, `<p class="gate-err">`+long+`</p>`) {
		t.Fatalf("long errMsg should be fully rendered")
	}
}

func TestDeep3PasswordPageScriptInErrMsgCannotEscapeAttr(t *testing.T) {
	payload := `</p><script>alert('x')</script><p>`
	rec := deep3Render("slug", payload, http.StatusForbidden)
	body := rec.Body.String()
	if strings.Contains(body, `<script>alert('x')</script>`) {
		t.Fatalf("errMsg script tag must be escaped, body: %s", body)
	}
	if !strings.Contains(body, `&lt;script&gt;`) {
		t.Fatalf("escaped script tag missing, body: %s", body)
	}
}

func TestDeep3PasswordPageSingleQuoteAndDoubleQuoteEscaped(t *testing.T) {
	rec := deep3Render(`a'"b`, `c'"d`, http.StatusForbidden)
	body := rec.Body.String()
	if strings.Contains(body, `action="/a'"b"`) {
		t.Fatalf("raw single quote in slug must be escaped, body: %s", body)
	}
	if !strings.Contains(body, `&#39;`) {
		t.Fatalf("single quote should be escaped to &#39;, body: %s", body)
	}
	if !strings.Contains(body, `&#34;`) {
		t.Fatalf("double quote should be escaped to &#34;, body: %s", body)
	}
}

func TestDeep3PasswordPageBacktickAndEqualsEscapedInSlug(t *testing.T) {
	rec := deep3Render("`=<>", "", http.StatusOK)
	body := rec.Body.String()
	if !strings.Contains(body, "`=<>") && !strings.Contains(body, "`=&lt;&gt;") {
		t.Fatalf("backtick/equals should be preserved or escaped, body: %s", body)
	}
	if strings.Contains(body, `action="/`+"`"+`"`) {
		t.Fatalf("raw backtick inside action attr must not break attribute, body: %s", body)
	}
}

func TestDeep3PasswordPageSVGIconPresent(t *testing.T) {
	rec := deep3Render("slug", "", http.StatusOK)
	body := rec.Body.String()
	if !strings.Contains(body, `<svg viewBox="0 0 24 24"`) {
		t.Fatalf("lock svg icon should be present, body: %s", body)
	}
	if !strings.Contains(body, `stroke="#8A5A33"`) {
		t.Fatalf("svg stroke color should match source, body: %s", body)
	}
}

func TestDeep3PasswordPagePasswordInputAutofocusAndPlaceholder(t *testing.T) {
	rec := deep3Render("slug", "", http.StatusOK)
	body := rec.Body.String()
	if !strings.Contains(body, `autofocus`) {
		t.Fatalf("input should have autofocus, body: %s", body)
	}
	if !strings.Contains(body, `autocomplete="current-password"`) {
		t.Fatalf("input should declare autocomplete, body: %s", body)
	}
	if !strings.Contains(body, `placeholder="访问密码"`) {
		t.Fatalf("placeholder text mismatch, body: %s", body)
	}
}

func TestDeep3PasswordPageStylesheetAndInlineStyleIncluded(t *testing.T) {
	rec := deep3Render("slug", "", http.StatusOK)
	body := rec.Body.String()
	if !strings.Contains(body, `<link rel="stylesheet" href="/ui/assets/css/style.css">`) {
		t.Fatalf("stylesheet link missing, body: %s", body)
	}
	if !strings.Contains(body, `.gate-wrap{min-height:100vh;`) {
		t.Fatalf("inline gate-wrap style missing, body: %s", body)
	}
	if !strings.Contains(body, `</style>`) {
		t.Fatalf("style close tag missing, body: %s", body)
	}
}

func TestDeep3PasswordPageUnicodeErrMsgPreserved(t *testing.T) {
	msg := "密码错误 · 请重试 ✓"
	rec := deep3Render("slug", msg, http.StatusUnauthorized)
	body := rec.Body.String()
	if !strings.Contains(body, msg) {
		t.Fatalf("unicode errMsg should be preserved verbatim, body: %s", body)
	}
}

func TestDeep3PasswordPageUnicodeSlugEscapedCorrectly(t *testing.T) {
	slug := "短码-üñî"
	rec := deep3Render(slug, "", http.StatusOK)
	body := rec.Body.String()
	if !strings.Contains(body, `action="/`+slug+`"`) {
		t.Fatalf("unicode slug should appear in action, body: %s", body)
	}
	if !strings.Contains(body, `<span class="mono">`+slug+`</span>`) {
		t.Fatalf("unicode slug should appear in footer, body: %s", body)
	}
}

func TestDeep3PasswordPageBodyEndsWithClosingHTML(t *testing.T) {
	rec := deep3Render("slug", "", http.StatusOK)
	body := rec.Body.String()
	if !strings.HasSuffix(body, `</body></html>`) {
		t.Fatalf("body should end with </body></html>, tail = %q", body[max(0, len(body)-40):])
	}
	if strings.Count(body, `<!DOCTYPE html>`) != 1 {
		t.Fatalf("exactly one doctype expected, got %d", strings.Count(body, `<!DOCTYPE html>`))
	}
}

func TestDeep3PasswordPageMultipleStatusCodes(t *testing.T) {
	cases := []struct {
		name   string
		status int
	}{
		{"ok", http.StatusOK},
		{"unauthorized", http.StatusUnauthorized},
		{"forbidden", http.StatusForbidden},
		{"notfound", http.StatusNotFound},
		{"servererror", http.StatusInternalServerError},
	}
	for _, tc := range cases {
		rec := deep3Render("slug", "err", tc.status)
		if rec.Code != tc.status {
			t.Fatalf("%s: status = %d, want %d", tc.name, rec.Code, tc.status)
		}
		if rec.Header().Get("Content-Type") != "text/html; charset=utf-8" {
			t.Fatalf("%s: content type mismatch: %q", tc.name, rec.Header().Get("Content-Type"))
		}
	}
}

func TestDeep3PasswordPageGateClassesPresent(t *testing.T) {
	rec := deep3Render("slug", "x", http.StatusForbidden)
	body := rec.Body.String()
	for _, cls := range []string{
		`class="gate-wrap"`,
		`class="gate-card"`,
		`class="gate-hint"`,
		`class="gate-err"`,
		`class="gate-foot"`,
	} {
		if !strings.Contains(body, cls) {
			t.Fatalf("expected %s in body, body: %s", cls, body)
		}
	}
}
