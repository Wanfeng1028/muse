// Package infer 提供数据源列类型推断与值解析能力。
// 支持 CSV、JSON 的列结构推断，统一类型提升，以及字符串到具体类型的解析。
package infer

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// Column 表示一列的名称与推断类型。
// Type 取值：INTEGER、REAL、TEXT、BOOLEAN、DATETIME。
type Column struct {
	Name string
	Type string
}

// 采样行数上限。
const sampleLimit = 500

// InferCSV 采样 CSV 文件前 500 行推断列类型。
// delimiter 为空时使用逗号。空行跳过，列数不一致的行按表头截断或补空。
func InferCSV(path, delimiter string) ([]Column, error) {
	if delimiter == "" {
		delimiter = ","
	}
	if len([]rune(delimiter)) != 1 {
		return nil, fmt.Errorf("分隔符必须为单个字符: %q", delimiter)
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("打开 CSV 文件失败: %w", err)
	}
	defer f.Close()

	r := csv.NewReader(bufio.NewReader(f))
	r.Comma = []rune(delimiter)[0]
	r.FieldsPerRecord = -1
	r.LazyQuotes = true

	header, err := r.Read()
	if err != nil {
		return nil, fmt.Errorf("读取 CSV 表头失败: %w", err)
	}
	// 去掉 BOM
	if len(header) > 0 {
		header[0] = strings.TrimPrefix(header[0], "\ufeff")
	}
	n := len(header)
	// 每列收集样本值的推断类型
	colTypes := make([][]string, n)
	count := 0
	for count < sampleLimit {
		rec, err := r.Read()
		if err != nil {
			break
		}
		// 跳过空行
		if len(rec) == 0 || (len(rec) == 1 && strings.TrimSpace(rec[0]) == "") {
			continue
		}
		// 截断或补空，保持列数一致
		if len(rec) > n {
			rec = rec[:n]
		}
		for len(rec) < n {
			rec = append(rec, "")
		}
		for i := 0; i < n; i++ {
			colTypes[i] = append(colTypes[i], detectType(rec[i]))
		}
		count++
	}

	cols := make([]Column, n)
	for i := 0; i < n; i++ {
		cols[i] = Column{Name: header[i], Type: UnifyTypes(colTypes[i])}
	}
	return cols, nil
}

// InferJSON 采样 JSON 文件前 500 个元素推断列类型。
// root 为空表示顶层就是数组，否则按 "data.items" 形式导航到数组。
// 元素必须为对象，嵌套值转 JSON 字符串后按 TEXT 处理。
func InferJSON(path, root string) ([]Column, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("读取 JSON 文件失败: %w", err)
	}
	var top any
	if err := json.Unmarshal(data, &top); err != nil {
		return nil, fmt.Errorf("解析 JSON 失败: %w", err)
	}

	// 按 root 导航
	node := top
	if strings.TrimSpace(root) != "" {
		for _, seg := range strings.Split(root, ".") {
			seg = strings.TrimSpace(seg)
			if seg == "" {
				continue
			}
			m, ok := node.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("root 路径 %q 处不是对象", seg)
			}
			v, ok := m[seg]
			if !ok {
				return nil, fmt.Errorf("root 路径缺少字段: %q", seg)
			}
			node = v
		}
	}

	arr, ok := node.([]any)
	if !ok {
		return nil, fmt.Errorf("root 指向的节点不是数组")
	}

	// 收集列顺序与样本
	var order []string
	colSamples := make(map[string][]string)
	seen := make(map[string]bool)
	count := 0
	for _, elem := range arr {
		if count >= sampleLimit {
			break
		}
		obj, ok := elem.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("数组元素必须为对象")
		}
		for k, v := range obj {
			if !seen[k] {
				seen[k] = true
				order = append(order, k)
			}
			colSamples[k] = append(colSamples[k], detectJSONType(v))
		}
		count++
	}

	cols := make([]Column, 0, len(order))
	for _, name := range order {
		cols = append(cols, Column{Name: name, Type: UnifyTypes(colSamples[name])})
	}
	return cols, nil
}

// detectType 根据单个字符串值推断其类型。
func detectType(s string) string {
	t := strings.TrimSpace(s)
	if t == "" {
		return "" // 空值不参与推断
	}
	lower := strings.ToLower(t)
	if lower == "true" || lower == "false" || t == "1" || t == "0" || t == "是" || t == "否" {
		return "BOOLEAN"
	}
	if _, err := strconv.ParseInt(t, 10, 64); err == nil {
		return "INTEGER"
	}
	if _, err := strconv.ParseFloat(t, 64); err == nil {
		return "REAL"
	}
	if isDatetime(t) {
		return "DATETIME"
	}
	return "TEXT"
}

// detectJSONType 根据 JSON 原生值推断类型字符串。
func detectJSONType(v any) string {
	switch val := v.(type) {
	case nil:
		return ""
	case bool:
		return "BOOLEAN"
	case float64:
		// JSON 数字默认 float64，整数值视为 INTEGER
		if val == float64(int64(val)) {
			return "INTEGER"
		}
		return "REAL"
	case string:
		return detectType(val)
	default:
		// 嵌套对象/数组转 JSON 字符串后视为 TEXT
		return "TEXT"
	}
}

// isDatetime 判断字符串是否可解析为日期时间。
func isDatetime(s string) bool {
	layouts := []string{
		time.RFC3339,
		"2006-01-02 15:04:05",
		"2006-01-02T15:04:05",
		"2006-01-02 15:04",
		"2006-01-02",
		"2006/01/02",
		"2006/01/02 15:04:05",
	}
	for _, l := range layouts {
		if _, err := time.Parse(l, s); err == nil {
			return true
		}
	}
	return false
}

// UnifyTypes 对一组类型做提升：INTEGER+REAL→REAL；出现 TEXT→TEXT；
// BOOLEAN+INTEGER→INTEGER；DATETIME 仅当全部可解析为日期才保留否则 TEXT；空→TEXT。
func UnifyTypes(ts []string) string {
	if len(ts) == 0 {
		return "TEXT"
	}
	hasText := false
	hasReal := false
	hasInteger := false
	hasBoolean := false
	hasDatetime := false
	nonEmpty := false
	for _, t := range ts {
		if t == "" {
			continue
		}
		nonEmpty = true
		switch t {
		case "TEXT":
			hasText = true
		case "REAL":
			hasReal = true
		case "INTEGER":
			hasInteger = true
		case "BOOLEAN":
			hasBoolean = true
		case "DATETIME":
			hasDatetime = true
		}
	}
	if !nonEmpty {
		return "TEXT"
	}
	if hasText {
		return "TEXT"
	}
	// DATETIME 仅当所有值都是日期时才保留
	if hasDatetime {
		onlyDatetime := hasDatetime && !hasReal && !hasInteger && !hasBoolean
		if onlyDatetime {
			return "DATETIME"
		}
		return "TEXT"
	}
	if hasReal {
		return "REAL"
	}
	if hasInteger && hasBoolean {
		return "INTEGER"
	}
	if hasInteger {
		return "INTEGER"
	}
	if hasBoolean {
		return "BOOLEAN"
	}
	return "TEXT"
}

// ParseValue 将字符串按目标类型解析为对应值。
// 空串返回 nil；BOOLEAN 接受 true/false/1/0/是/否；
// DATETIME 尝试多种布局后统一转为 RFC3339 UTC 字符串。
func ParseValue(s, typ string) (any, error) {
	if s == "" {
		return nil, nil
	}
	switch typ {
	case "INTEGER":
		v, err := strconv.ParseInt(strings.TrimSpace(s), 10, 64)
		if err != nil {
			return nil, fmt.Errorf("解析 INTEGER 失败 %q: %w", s, err)
		}
		return v, nil
	case "REAL":
		v, err := strconv.ParseFloat(strings.TrimSpace(s), 64)
		if err != nil {
			return nil, fmt.Errorf("解析 REAL 失败 %q: %w", s, err)
		}
		return v, nil
	case "BOOLEAN":
		switch strings.ToLower(strings.TrimSpace(s)) {
		case "true", "1", "是":
			return int64(1), nil
		case "false", "0", "否":
			return int64(0), nil
		default:
			return nil, fmt.Errorf("解析 BOOLEAN 失败 %q", s)
		}
	case "DATETIME":
		t, err := parseDatetime(s)
		if err != nil {
			return nil, err
		}
		return t.UTC().Format(time.RFC3339), nil
	default: // TEXT
		return s, nil
	}
}

// parseDatetime 尝试多种布局解析日期时间。
func parseDatetime(s string) (time.Time, error) {
	s = strings.TrimSpace(s)
	layouts := []string{
		time.RFC3339,
		"2006-01-02 15:04:05",
		"2006-01-02T15:04:05",
		"2006-01-02 15:04",
		"2006-01-02",
		"2006/01/02",
		"2006/01/02 15:04:05",
	}
	for _, l := range layouts {
		if t, err := time.Parse(l, s); err == nil {
			return t, nil
		}
	}
	return time.Time{}, fmt.Errorf("解析 DATETIME 失败 %q", s)
}

// NormalizeComparable 将可比值规范化：能解析为日期时间的统一转 RFC3339，
// 使水位线比较不受 "2006-01-02 15:04:05" 与 RFC3339 两种写法的影响；不可解析则原样返回。
func NormalizeComparable(v string) string {
	if t, err := parseDatetime(v); err == nil {
		return t.UTC().Format(time.RFC3339)
	}
	return v
}

// SQLiteType 将推断类型映射为 SQLite 列类型。BOOLEAN→INTEGER，其余直映。
func SQLiteType(typ string) string {
	switch typ {
	case "BOOLEAN":
		return "INTEGER"
	case "INTEGER", "REAL", "TEXT", "DATETIME":
		return typ
	default:
		return "TEXT"
	}
}

// Stringify 将任意值转为字符串，nil 返回空串，供主键统一转换。
func Stringify(v any) string {
	if v == nil {
		return ""
	}
	switch val := v.(type) {
	case string:
		return val
	case []byte:
		return string(val)
	default:
		return fmt.Sprintf("%v", v)
	}
}

// 保证 filepath 被引用（用于未来路径处理扩展），避免未使用导入。
var _ = filepath.Join
