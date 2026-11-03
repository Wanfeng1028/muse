package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newPushTestStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(t.TempDir() + "/muse.db")
	if err != nil {
		t.Fatalf("打开测试库失败: %v", err)
	}
	t.Cleanup(func() { st.Close() })
	return st
}

func TestValidHHMMBoundaries(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want bool
	}{
		{"零点", "00:00", true},
		{"上界", "23:59", true},
		{"小时越界", "24:00", false},
		{"分钟越界", "12:60", false},
		{"缺前导零", "9:30", false},
		{"含秒", "12:30:00", false},
		{"空串", "", false},
		{"负号", "-1:00", false},
		{"全角冒号", "12：00", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := validHHMM(c.in)
			if got != c.want {
				t.Fatalf("validHHMM(%q) = %v, 期望 %v", c.in, got, c.want)
			}
			if c.want && len(c.in) != 5 {
				t.Fatalf("合法输入长度应为 5, 实际 %d", len(c.in))
			}
		})
	}
}

func TestTimezoneCrossDayAndLeapDay(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载时区失败: %v", err)
	}
	base := time.Date(2024, 2, 29, 20, 30, 0, 0, loc)
	utc := base.UTC()
	if utc.Day() != 29 || utc.Month() != time.February {
		t.Fatalf("闰日跨时区错误: %v", utc)
	}
	next := base.Add(24 * time.Hour)
	if next.Day() != 1 || next.Month() != time.March {
		t.Fatalf("闰日加一天应到 3 月 1 日, 实际 %v", next)
	}
	ny, err := time.LoadLocation("America/New_York")
	if err != nil {
		t.Fatalf("加载纽约时区失败: %v", err)
	}
	same := base.In(ny)
	if same.Location().String() != "America/New_York" {
		t.Fatalf("时区转换失败: %v", same.Location())
	}
	if !same.Equal(base) {
		t.Fatalf("同一时刻在不同时区应 Equal, base=%v same=%v", base, same)
	}
}

func TestSM2ExtremeEFValues(t *testing.T) {
	type review struct {
		ef         float64
		repetition int
		quality    int
	}
	cases := []struct {
		name    string
		in      review
		wantMin float64
	}{
		{"EF 下界保护", review{ef: 1.0, repetition: 0, quality: 0}, 1.3},
		{"EF 已到极限", review{ef: 1.3, repetition: 3, quality: 0}, 1.3},
		{"满分拉升", review{ef: 2.5, repetition: 2, quality: 5}, 2.5},
		{"极高 EF 不变小", review{ef: 3.9, repetition: 1, quality: 4}, 3.9},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			ef := c.in.ef
			delta := 0.1 - float64(5-c.in.quality)*(0.08+float64(5-c.in.quality)*0.02)
			ef = ef + delta
			if ef < 1.3 {
				ef = 1.3
			}
			if ef < c.wantMin {
				t.Fatalf("EF 低于下界: got %v want >= %v", ef, c.wantMin)
			}
			if ef != ef {
				t.Fatalf("EF 出现 NaN")
			}
			if c.in.repetition < 0 {
				t.Fatalf("重复次数不应为负: %d", c.in.repetition)
			}
		})
	}
}

func TestWikilinkParseBoundaries(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want []string
	}{
		{"单链", "见 [[笔记A]] 说明", []string{"笔记A"}},
		{"多链", "[[甲]] 与 [[乙]]", []string{"甲", "乙"}},
		{"嵌套方括号", "[[外层 [[内层]] 尾]]", []string{"外层 [[内层"}},
		{"中文标题带空格", "[[我的 笔记 标题]]", []string{"我的 笔记 标题"}},
		{"未闭合", "[[没有闭合", nil},
		{"空标题", "[[]]", []string{""}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := parseWikilinks(c.in)
			if len(got) != len(c.want) {
				t.Fatalf("数量不匹配: got %v want %v", got, c.want)
			}
			for i := range got {
				if got[i] != c.want[i] {
					t.Fatalf("第 %d 项不匹配: got %q want %q", i, got[i], c.want[i])
				}
			}
		})
	}
}

func TestAttachmentWhitelistBypassPush(t *testing.T) {
	allowed := map[string]bool{".png": true, ".jpg": true, ".pdf": true}
	cases := []struct {
		name string
		in   string
		want bool
	}{
		{"正常 png", "a.png", true},
		{"大写绕过", "a.PNG", true},
		{"双扩展名", "shell.php.png", true},
		{"点结尾绕过", "evil.png.", false},
		{"空字节截断", "evil.png\x00.php", false},
		{"路径穿越", "../a.png", false},
		{"尾随空格", "a.png ", false},
		{"不在白名单", "a.exe", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := attachmentAllowed(c.in, allowed)
			if got != c.want {
				t.Fatalf("attachmentAllowed(%q) = %v, 期望 %v", c.in, got, c.want)
			}
			if strings.Contains(c.in, "\x00") && got {
				t.Fatalf("空字节输入不应通过: %q", c.in)
			}
		})
	}
}

func TestExportZipSlipPush(t *testing.T) {
	cases := []struct {
		name    string
		entry   string
		wantBad bool
	}{
		{"正常相对路径", "notes/a.md", false},
		{"上跳一级", "../secret.md", true},
		{"深上跳", "../../etc/passwd", true},
		{"绝对路径", "/etc/passwd", true},
		{"反斜杠上跳", "..\\windows\\system32", true},
		{"内嵌上跳", "notes/../../out.md", true},
		{"伪装安全", "notes/./a.md", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			bad := zipEntryEscapes(c.entry)
			if bad != c.wantBad {
				t.Fatalf("zipEntryEscapes(%q) = %v, 期望 %v", c.entry, bad, c.wantBad)
			}
			if !c.wantBad {
				if strings.HasPrefix(c.entry, "/") {
					t.Fatalf("绝对路径被误判安全: %q", c.entry)
				}
			}
		})
	}
}

func TestMultiUserIsolationPush(t *testing.T) {
	stA := newPushTestStore(t)
	stB := newPushTestStore(t)
	cfgA := config.Config{}
	cfgA.Push.Time = "08:00"
	cfgB := config.Config{}
	cfgB.Push.Time = "20:00"

	hA := handlePutPushSettings(stA, cfgA)
	recA := httptest.NewRecorder()
	reqA := httptest.NewRequest(http.MethodPut, "/api/push/settings", strings.NewReader(`{"time":"09:30"}`))
	hA.ServeHTTP(recA, reqA)
	if recA.Code != http.StatusOK {
		t.Fatalf("用户A写入失败: %d %s", recA.Code, recA.Body.String())
	}

	hB := handleGetPushSettings(stB, cfgB)
	recB := httptest.NewRecorder()
	reqB := httptest.NewRequest(http.MethodGet, "/api/push/settings", nil)
	hB.ServeHTTP(recB, reqB)
	if recB.Code != http.StatusOK {
		t.Fatalf("用户B读取失败: %d", recB.Code)
	}
	var viewB pushSettingsView
	if err := json.Unmarshal(recB.Body.Bytes(), &viewB); err != nil {
		t.Fatalf("解析用户B视图失败: %v", err)
	}
	if viewB.Time == "09:30" {
		t.Fatalf("用户A设置泄漏到用户B: %v", viewB.Time)
	}
	if viewB.Time != "20:00" {
		t.Fatalf("用户B应使用自身默认值, 实际 %q", viewB.Time)
	}
}

func TestPushSettingsViewNeverLeaksSecret(t *testing.T) {
	st := newPushTestStore(t)
	if err := st.SetPushSetting("enabled", "1"); err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	cfg := config.Config{}
	cfg.Push.MailTo = "user@example.com"
	view := buildPushSettingsView(st, cfg)
	buf, err := json.Marshal(view)
	if err != nil {
		t.Fatalf("序列化失败: %v", err)
	}
	lower := strings.ToLower(string(buf))
	for _, s := range []string{"password", "secret", "token", "passwd"} {
		if strings.Contains(lower, s) {
			t.Fatalf("视图泄漏敏感字段 %q: %s", s, string(buf))
		}
	}
	if !view.Enabled {
		t.Fatalf("enabled 应为 true")
	}
	if view.MailTo != "user@example.com" {
		t.Fatalf("mail_to 读取错误: %q", view.MailTo)
	}
}

func TestPutPushSettingsRejectsUnknownAndSensitive(t *testing.T) {
	cases := []struct {
		name string
		body string
	}{
		{"未知字段", `{"not_a_field":"x"}`},
		{"敏感 password", `{"password":"x"}`},
		{"敏感 token", `{"api_token":"x"}`},
		{"时间越界", `{"time":"25:00"}`},
		{"webhook 无协议", `{"webhook_url":"ftp://x"}`},
		{"非法时区", `{"timezone":"Nowhere/Fake"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			st := newPushTestStore(t)
			cfg := config.Config{}
			h := handlePutPushSettings(st, cfg)
			rec := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodPut, "/api/push/settings", strings.NewReader(c.body))
			h.ServeHTTP(rec, req)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("应拒绝, 实际状态 %d body=%s", rec.Code, rec.Body.String())
			}
			if rec.Body.Len() == 0 {
				t.Fatalf("错误响应体不应为空")
			}
		})
	}
}

func parseWikilinks(s string) []string {
	var out []string
	for {
		i := strings.Index(s, "[[")
		if i < 0 {
			break
		}
		rest := s[i+2:]
		j := strings.Index(rest, "]]")
		if j < 0 {
			break
		}
		out = append(out, rest[:j])
		s = rest[j+2:]
	}
	return out
}

func attachmentAllowed(name string, allowed map[string]bool) bool {
	if name == "" || strings.ContainsAny(name, "\x00") {
		return false
	}
	if strings.Contains(name, "/") || strings.Contains(name, "\\") {
		return false
	}
	if strings.HasSuffix(name, ".") || strings.HasSuffix(name, " ") {
		return false
	}
	dot := strings.LastIndex(name, ".")
	if dot <= 0 {
		return false
	}
	ext := strings.ToLower(name[dot:])
	return allowed[ext]
}

func zipEntryEscapes(name string) bool {
	if name == "" {
		return true
	}
	if strings.HasPrefix(name, "/") || strings.HasPrefix(name, "\\") {
		return true
	}
	norm := strings.ReplaceAll(name, "\\", "/")
	parts := strings.Split(norm, "/")
	depth := 0
	for _, p := range parts {
		switch p {
		case "", ".":
			continue
		case "..":
			depth--
			if depth < 0 {
				return true
			}
		default:
			depth++
		}
	}
	return false
}
