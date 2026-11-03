package checker

import (
	"fmt"
	"regexp"
	"strings"
)

// AssertKeyword 对 body 做关键字断言。
// mode: "" 或 "exact" 为区分大小写包含；"ignorecase" 忽略大小写包含；"regex" 为正则匹配（Search 语义）。
// keyword 为空返回 nil（不断言）。mode 非法返回中文错误。正则是预编译失败返回中文错误（包装 regexp 错误原文）。
// 断言不通过返回中文错误，错误文本必须包含"关键字"三字（供上游归因分类）。
func AssertKeyword(body []byte, keyword, mode string) error {
	if keyword == "" {
		return nil
	}
	switch mode {
	case "", "exact":
		if !strings.Contains(string(body), keyword) {
			return fmt.Errorf("关键字断言失败：响应体不包含关键字")
		}
		return nil
	case "ignorecase":
		if !strings.Contains(strings.ToLower(string(body)), strings.ToLower(keyword)) {
			return fmt.Errorf("关键字断言失败：响应体不包含关键字")
		}
		return nil
	case "regex":
		re, err := regexp.Compile(keyword)
		if err != nil {
			return fmt.Errorf("关键字正则非法：%v", err)
		}
		if !re.Match(body) {
			return fmt.Errorf("关键字断言失败：响应体不匹配正则")
		}
		return nil
	default:
		return fmt.Errorf("关键字模式非法：%s", mode)
	}
}
