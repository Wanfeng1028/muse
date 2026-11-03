package com.scaffold.framework.audit;

public interface OperationLogRecorder {

    void record(OperationLogEntry entry);
}
