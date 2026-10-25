use std::fs;

#[test]
fn test_style_css_has_no_orphan_declaration_block() {
    let path = format!("{}/static/style.css", env!("CARGO_MANIFEST_DIR"));
    let content = fs::read_to_string(&path).unwrap_or_else(|e| panic!("无法读取 {}: {}", path, e));

    let mut brace_depth: i32 = 0;
    let mut in_comment = false;
    for (idx, line) in content.lines().enumerate() {
        let line_no = idx + 1;
        let trimmed = line.trim();
        if in_comment {
            if trimmed.contains("*/") {
                in_comment = false;
            }
            continue;
        }
        if trimmed.is_empty() || trimmed.starts_with("/*") {
            if trimmed.starts_with("/*") && !trimmed.contains("*/") {
                in_comment = true;
            }
            continue;
        }
        for ch in trimmed.chars() {
            match ch {
                '{' => brace_depth += 1,
                '}' => brace_depth -= 1,
                _ => {}
            }
        }
        // 只认真正的自定义属性声明（--name: ...），不把裸分隔线（如 ---）误报。
        let is_decl = match trimmed.strip_prefix("--") {
            Some(rest) => {
                let name_len = rest
                    .chars()
                    .take_while(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
                    .map(|c| c.len_utf8())
                    .sum::<usize>();
                name_len > 0 && rest[name_len..].trim_start().starts_with(':')
            }
            None => false,
        };
        if brace_depth == 0 && is_decl {
            panic!("第 {} 行存在孤立声明块: {}", line_no, trimmed);
        }
    }

    assert_eq!(
        brace_depth, 0,
        "花括号不配对，扫描结束时 brace_depth = {}",
        brace_depth
    );
    assert!(
        content.contains("[data-theme=\"dark\"]"),
        "style.css 缺少 [data-theme=\"dark\"] 选择器"
    );
    assert!(
        content.contains("--card-bg: rgba(33,29,23,0.92)"),
        "style.css 缺少 --card-bg: rgba(33,29,23,0.92) 声明"
    );
}
