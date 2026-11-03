package com.scaffold.system.domain.dto;

import jakarta.validation.constraints.NotBlank;

public class LoginRequest {

    @NotBlank(message = "不能为空")
    private String username;

    @NotBlank(message = "不能为空")
    private String password;

    private String captcha;

    private String captchaUuid;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
    public String getCaptcha() { return captcha; }
    public void setCaptcha(String captcha) { this.captcha = captcha; }
    public String getCaptchaUuid() { return captchaUuid; }
    public void setCaptchaUuid(String captchaUuid) { this.captchaUuid = captchaUuid; }
}
