package com.dramafactory.repository;

import com.dramafactory.model.MediaProvider;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * 媒体供应商仓储。
 */
public interface MediaProviderRepository extends JpaRepository<MediaProvider, Long> {

    /** 按 id 升序查询全部供应商 */
    List<MediaProvider> findAllByOrderByIdAsc();

    /** 按模块查询供应商，id 升序 */
    List<MediaProvider> findByModuleOrderByIdAsc(String module);
}
