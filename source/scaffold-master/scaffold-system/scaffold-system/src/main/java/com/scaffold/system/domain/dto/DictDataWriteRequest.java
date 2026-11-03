package com.scaffold.system.domain.dto;

public class DictDataWriteRequest {

    private String dictType;
    private String label;
    private String value;
    private Integer sort;
    private Integer status;
    private String tone;
    private Boolean def;
    private String remark;

    public String getDictType() { return dictType; }
    public void setDictType(String dictType) { this.dictType = dictType; }
    public String getLabel() { return label; }
    public void setLabel(String label) { this.label = label; }
    public String getValue() { return value; }
    public void setValue(String value) { this.value = value; }
    public Integer getSort() { return sort; }
    public void setSort(Integer sort) { this.sort = sort; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer status) { this.status = status; }
    public String getTone() { return tone; }
    public void setTone(String tone) { this.tone = tone; }
    public Boolean getDef() { return def; }
    public void setDef(Boolean def) { this.def = def; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
}
