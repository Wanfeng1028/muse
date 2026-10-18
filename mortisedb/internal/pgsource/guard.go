// guard.go 提供只读 SQL 白名单校验。
package pgsource

import (
	"errors"
	"regexp"
	"strings"
)

var readOnlyPattern = regexp.MustCompile(`(?is)^\s*(select|with)\b`)

// AssertReadOnlySQL 校验 query 是否为允许的只读语句。
func AssertReadOnlySQL(query string) error {
	trimmed := strings.TrimSpace(query)
	if !readOnlyPattern.MatchString(trimmed) {
		return errors.New("只读校验失败：SQL 必须以 SELECT 或 WITH 开头")
	}
	if strings.Contains(trimmed, ";") {
		return errors.New("只读校验失败：SQL 中不允许包含分号，禁止多语句")
	}
	return nil
}
