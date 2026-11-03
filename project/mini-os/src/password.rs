pub fn validate_password(password: &str, username: &str) -> Result<(), String> {
    if password.chars().count() < 8 {
        return Err("密码至少 8 个字符".to_string());
    }
    if password.chars().count() > 128 {
        return Err("密码不能超过 128 个字符".to_string());
    }
    let has_letter = password.chars().any(|c| c.is_ascii_alphabetic());
    let has_digit = password.chars().any(|c| c.is_ascii_digit());
    if !has_letter || !has_digit {
        return Err("密码必须同时包含字母和数字".to_string());
    }
    if password.eq_ignore_ascii_case(username) {
        return Err("密码不能与用户名相同".to_string());
    }
    const BLACKLIST: &[&str] = &[
        "password",
        "12345678",
        "qwertyui",
        "abc12345",
        "11111111",
        "00000000",
        "1q2w3e4r",
        "password1",
        "123456789",
        "1234567890",
        "qwerty123",
        "1qaz2wsx",
        "admin123",
        "minios123",
        "letmein1",
    ];
    if BLACKLIST.iter().any(|&b| password.eq_ignore_ascii_case(b)) {
        return Err("这个密码太常见了，换一个更复杂的".to_string());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn too_short() {
        assert_eq!(
            validate_password("ab1", "alice"),
            Err("密码至少 8 个字符".to_string())
        );
    }

    #[test]
    fn too_long() {
        let pw = format!("{}1", "a".repeat(128));
        assert_eq!(
            validate_password(&pw, "alice"),
            Err("密码不能超过 128 个字符".to_string())
        );
    }

    #[test]
    fn missing_letter_and_digit() {
        assert_eq!(
            validate_password("abcdefgh", "alice"),
            Err("密码必须同时包含字母和数字".to_string())
        );
        assert_eq!(
            validate_password("12345678", "alice"),
            Err("密码必须同时包含字母和数字".to_string())
        );
    }

    #[test]
    fn same_as_username() {
        assert_eq!(
            validate_password("alice1234", "alice1234"),
            Err("密码不能与用户名相同".to_string())
        );
    }

    #[test]
    fn blacklisted() {
        assert_eq!(
            validate_password("abc12345", "alice"),
            Err("这个密码太常见了，换一个更复杂的".to_string())
        );
    }

    #[test]
    fn valid() {
        assert_eq!(validate_password("s3cureP4ss", "alice"), Ok(()));
    }
}
