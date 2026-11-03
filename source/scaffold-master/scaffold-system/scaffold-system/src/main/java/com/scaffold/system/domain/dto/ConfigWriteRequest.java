package com.scaffold.system.domain.dto;

public class ConfigWriteRequest {

    private String name;
    private String key;
    private String value;
    private String type;
    private Boolean builtin;
    private String remark;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getKey() { return key; }
    public void setKey(String key) { this.key = key; }
    public String getValue() { return value; }
    public void setValue(String value) { this.value = value; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public Boolean getBuiltin() { return builtin; }
    public void setBuiltin(Boolean builtin) { this.builtin = builtin; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
}
