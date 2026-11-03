package com.scaffold.system.domain.vo;

import java.util.ArrayList;
import java.util.List;

public class RouteVO {

    private Long id;
    private Long parentId;
    private String name;
    private String path;
    private String component;
    private String icon;
    private String permission;
    private List<RouteVO> children = new ArrayList<>();

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getParentId() { return parentId; }
    public void setParentId(Long parentId) { this.parentId = parentId; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getPath() { return path; }
    public void setPath(String path) { this.path = path; }
    public String getComponent() { return component; }
    public void setComponent(String component) { this.component = component; }
    public String getIcon() { return icon; }
    public void setIcon(String icon) { this.icon = icon; }
    public String getPermission() { return permission; }
    public void setPermission(String permission) { this.permission = permission; }
    public List<RouteVO> getChildren() { return children; }
    public void setChildren(List<RouteVO> children) { this.children = children; }
}
