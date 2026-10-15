package com.dramafactory.exception;

public class CanvasConflictException extends RuntimeException {

    private final int currentVersion;
    private final String updatedBy;

    public CanvasConflictException(int currentVersion, String updatedBy) {
        super("项目版本冲突：当前 revision 为 " + currentVersion + "（最后写入者 " + updatedBy + "），请刷新后重试");
        this.currentVersion = currentVersion;
        this.updatedBy = updatedBy;
    }

    public int getCurrentVersion() {
        return currentVersion;
    }

    public String getUpdatedBy() {
        return updatedBy;
    }
}
