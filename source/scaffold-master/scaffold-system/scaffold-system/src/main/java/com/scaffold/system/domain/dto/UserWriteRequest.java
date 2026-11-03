package com.scaffold.system.domain.dto;

import java.util.List;

public class UserWriteRequest {

    private String username;
    private String password;
    private String nickname;
    private String phone;
    private String email;
    private Long deptId;
    private Integer status;
    private List<Long> roleIds;
    private List<Long> postIds;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
    public String getNickname() { return nickname; }
    public void setNickname(String nickname) { this.nickname = nickname; }
    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public Long getDeptId() { return deptId; }
    public void setDeptId(Long deptId) { this.deptId = deptId; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer status) { this.status = status; }
    public List<Long> getRoleIds() { return roleIds; }
    public void setRoleIds(List<Long> roleIds) { this.roleIds = roleIds; }
    public List<Long> getPostIds() { return postIds; }
    public void setPostIds(List<Long> postIds) { this.postIds = postIds; }
}
