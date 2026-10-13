package com.dramafactory.repository;

import com.dramafactory.model.ProviderModel;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;

import java.util.List;

/**
 * 供应商模型配置仓储。
 */
public interface ProviderModelRepository extends JpaRepository<ProviderModel, Long> {

    /** 按供应商 id 查询其模型，id 升序 */
    List<ProviderModel> findByProviderIdOrderByIdAsc(Long providerId);

    /** 按供应商 id 删除其全部模型 */
    @Modifying
    void deleteByProviderId(Long providerId);
}
