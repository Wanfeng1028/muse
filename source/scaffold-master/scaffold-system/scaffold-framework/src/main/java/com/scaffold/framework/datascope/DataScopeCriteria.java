package com.scaffold.framework.datascope;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class DataScopeCriteria {

    private final boolean allScope;
    private final Long userId;
    private final List<Long> deptIds;

    private DataScopeCriteria(boolean allScope, Long userId, List<Long> deptIds) {
        this.allScope = allScope;
        this.userId = userId;
        this.deptIds = deptIds == null ? List.of() : List.copyOf(deptIds);
    }

    public static DataScopeCriteria all() {
        return new DataScopeCriteria(true, null, List.of());
    }

    public static DataScopeCriteria selfOnly(Long userId) {
        return new DataScopeCriteria(false, userId, List.of());
    }

    public static DataScopeCriteria limited(Long userId, List<Long> deptIds) {
        Set<Long> ids = new LinkedHashSet<>();
        if (deptIds != null) {
            deptIds.stream().filter(id -> id != null).forEach(ids::add);
        }
        return new DataScopeCriteria(false, userId, new ArrayList<>(ids));
    }

    public boolean isAllScope() {
        return allScope;
    }

    public Long getUserId() {
        return userId;
    }

    public List<Long> getDeptIds() {
        return Collections.unmodifiableList(deptIds);
    }
}
