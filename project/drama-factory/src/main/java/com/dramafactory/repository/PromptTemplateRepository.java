package com.dramafactory.repository;

import com.dramafactory.model.AgentType;
import com.dramafactory.model.PromptTemplate;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * {@link PromptTemplate} 仓库。
 */
public interface PromptTemplateRepository extends JpaRepository<PromptTemplate, Long> {

    /**
     * 按 Agent 类型查询模板。
     *
     * @param agentType Agent 类型
     * @return 对应模板
     */
    Optional<PromptTemplate> findByAgentType(AgentType agentType);
}
