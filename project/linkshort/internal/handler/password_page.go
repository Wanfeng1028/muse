package handler

import (
	"html"
	"net/http"
	"strings"
)

// renderPasswordPage 渲染密码门页面。slug 与 errMsg 在输出前做 HTML 转义。
func renderPasswordPage(w http.ResponseWriter, slug, errMsg string, status int) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(status)

	escSlug := html.EscapeString(slug)
	escErr := html.EscapeString(errMsg)

	var b strings.Builder
	b.WriteString("<!DOCTYPE html>")
	b.WriteString(`<html lang="zh-CN"><head>`)
	b.WriteString(`<meta charset="utf-8">`)
	b.WriteString(`<meta name="viewport" content="width=device-width, initial-scale=1">`)
	b.WriteString(`<title>该链接受密码保护 · 短链</title>`)
	b.WriteString(`<link rel="stylesheet" href="/ui/assets/css/style.css">`)
	b.WriteString(`<style>`)
	b.WriteString(`.gate-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}`)
	b.WriteString(`.gate-card{background:#EDE6D6;border:1px solid #d8cdb4;border-radius:10px;padding:36px 40px;max-width:420px;width:100%}`)
	b.WriteString(`.gate-card h1{font-size:20px;margin:16px 0 8px;color:#1F1B16}`)
	b.WriteString(`.gate-hint{color:#6b6257;font-size:14px;margin:0 0 20px}`)
	b.WriteString(`.gate-err{color:#B3402A;font-size:14px;margin:0 0 12px}`)
	b.WriteString(`.gate-card input[type=password]{width:100%;box-sizing:border-box}`)
	b.WriteString(`.gate-foot{margin-top:20px;font-size:12px;color:#8a8177}`)
	b.WriteString(`</style>`)
	b.WriteString(`</head><body>`)
	b.WriteString(`<div class="gate-wrap"><div class="gate-card">`)
	b.WriteString(`<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#8A5A33" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>`)
	b.WriteString(`<h1>该链接受密码保护</h1>`)
	b.WriteString(`<p class="gate-hint">请输入访问密码后继续跳转</p>`)
	if escErr != "" {
		b.WriteString(`<p class="gate-err">`)
		b.WriteString(escErr)
		b.WriteString(`</p>`)
	}
	b.WriteString(`<form method="post" action="/`)
	b.WriteString(escSlug)
	b.WriteString(`">`)
	b.WriteString(`<input class="input" type="password" name="password" required autofocus placeholder="访问密码" autocomplete="current-password">`)
	b.WriteString(`<button class="btn primary" type="submit" style="width:100%;margin-top:12px">解锁并跳转</button>`)
	b.WriteString(`</form>`)
	b.WriteString(`<div class="gate-foot">短链 <span class="mono">`)
	b.WriteString(escSlug)
	b.WriteString(`</span> · 密码保护</div>`)
	b.WriteString(`</div></div>`)
	b.WriteString(`</body></html>`)

	_, _ = w.Write([]byte(b.String()))
}
