package handler

import (
	"strings"
	"testing"
)

func TestV118BulkPerItemPassword(t *testing.T) {
	js := v117Read(t, "web/assets/js/bulk.js")
	for _, want := range []string{
		`(?:\s+(\S+))?(?:\s+(\S+))?`,
		`var pw = match[3]`,
		`if (pw) item.password = pw;`,
		`else if (sharedPassword) item.password = sharedPassword;`,
		`sentPw.push(!!item.password)`,
		`sentPw[item.index]`,
		`"已设"`,
	} {
		if !strings.Contains(js, want) {
			t.Fatalf("bulk.js missing %q", want)
		}
	}
	for _, banned := range []string{
		"textContent = pw",
		"innerHTML = pw",
		"textContent = item.password",
		"innerHTML = item.password",
		"textContent = sharedPassword",
		"innerHTML = sharedPassword",
	} {
		if strings.Contains(js, banned) {
			t.Fatalf("bulk.js must never echo a password into the DOM: %q", banned)
		}
	}
	html := v117Read(t, "web/bulk.html")
	for _, want := range []string{"逐项密码", "逐项密码优先于统一密码"} {
		if !strings.Contains(html, want) {
			t.Fatalf("bulk.html missing %q", want)
		}
	}
}
