// 文件：src/test/java/com/dramafactory/service/PromptTemplateServiceV229Test.java

package com.dramafactory.service;

import com.dramafactory.model.AgentType;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.repository.PromptTemplateRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PromptTemplateServiceV229Test {

    @Mock
    private PromptTemplateRepository promptTemplateRepository;

    @InjectMocks
    private PromptTemplateService promptTemplateService;

    @Test
    @DisplayName("getByAgent：agentType 为 null 抛 IllegalArgumentException")
    void getByAgentNullAgentType() {
        assertThatThrownBy(() -> promptTemplateService.getByAgent(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("agentType 不能为空");
        verify(promptTemplateRepository, never()).findByAgentType(any());
    }

    @Test
    @DisplayName("getByAgent：repository 返回空 Optional 抛 IllegalStateException")
    void getByAgentNotFound() {
        when(promptTemplateRepository.findByAgentType(AgentType.SCRIPT)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> promptTemplateService.getByAgent(AgentType.SCRIPT))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("未找到 AgentType=" + AgentType.SCRIPT + " 的 Prompt 模板");

        verify(promptTemplateRepository).findByAgentType(AgentType.SCRIPT);
    }

    @Test
    @DisplayName("getByAgent：正常返回模板")
    void getByAgentFound() {
        PromptTemplate template = new PromptTemplate();
        template.setAgentType(AgentType.BOARD);
        template.setName("分镜默认模板");
        template.setContent("只输出 JSON 数组");
        when(promptTemplateRepository.findByAgentType(AgentType.BOARD)).thenReturn(Optional.of(template));

        PromptTemplate result = promptTemplateService.getByAgent(AgentType.BOARD);

        assertThat(result).isSameAs(template);
        assertThat(result.getAgentType()).isEqualTo(AgentType.BOARD);
        verify(promptTemplateRepository).findByAgentType(AgentType.BOARD);
    }

    @Test
    @DisplayName("update：agentType 为 null 抛 IllegalArgumentException")
    void updateNullAgentType() {
        assertThatThrownBy(() -> promptTemplateService.update(null, "新内容"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("agentType 不能为空");
        verify(promptTemplateRepository, never()).save(any());
    }

    @Test
    @DisplayName("update：content 为 null 抛 IllegalArgumentException")
    void updateNullContent() {
        assertThatThrownBy(() -> promptTemplateService.update(AgentType.VIDEO, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("模板内容不能为空");
        verify(promptTemplateRepository, never()).save(any());
    }

    @Test
    @DisplayName("update：content 为空白抛 IllegalArgumentException")
    void updateBlankContent() {
        assertThatThrownBy(() -> promptTemplateService.update(AgentType.VIDEO, "   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("模板内容不能为空");
        verify(promptTemplateRepository, never()).save(any());
    }

    @Test
    @DisplayName("update：getByAgent 抛出的 IllegalStateException 向上传播")
    void updatePropagatesGetByAgentException() {
        when(promptTemplateRepository.findByAgentType(AgentType.EDIT)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> promptTemplateService.update(AgentType.EDIT, "新剪辑内容"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("未找到 AgentType=" + AgentType.EDIT + " 的 Prompt 模板");

        verify(promptTemplateRepository).findByAgentType(AgentType.EDIT);
        verify(promptTemplateRepository, never()).save(any());
    }

    @Test
    @DisplayName("update：正常更新后刷新内容与 updatedAt 并调用 save")
    void updateSuccess() {
        PromptTemplate template = new PromptTemplate();
        template.setAgentType(AgentType.QC);
        template.setName("质检默认模板");
        template.setContent("旧内容");
        LocalDateTime oldUpdatedAt = LocalDateTime.now().minusDays(1);
        template.setUpdatedAt(oldUpdatedAt);
        when(promptTemplateRepository.findByAgentType(AgentType.QC)).thenReturn(Optional.of(template));
        when(promptTemplateRepository.save(any(PromptTemplate.class))).thenAnswer(inv -> inv.getArgument(0));

        LocalDateTime before = LocalDateTime.now();
        PromptTemplate result = promptTemplateService.update(AgentType.QC, "新的质检内容");

        assertThat(result).isSameAs(template);
        assertThat(result.getContent()).isEqualTo("新的质检内容");
        assertThat(result.getUpdatedAt()).isNotNull();
        assertThat(result.getUpdatedAt()).isAfterOrEqualTo(before);

        ArgumentCaptor<PromptTemplate> captor = ArgumentCaptor.forClass(PromptTemplate.class);
        verify(promptTemplateRepository).save(captor.capture());
        assertThat(captor.getValue().getContent()).isEqualTo("新的质检内容");
    }
}
