package com.dramafactory.service;

import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.PageRequest;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

public class UsageServiceByRunLimitValidationTest {

    private VideoTaskRepository videoTaskRepository;
    private AgentStepRepository agentStepRepository;
    private RunRepository runRepository;
    private UsageService usageService;

    @BeforeEach
    void setUp() {
        videoTaskRepository = mock(VideoTaskRepository.class);
        agentStepRepository = mock(AgentStepRepository.class);
        runRepository = mock(RunRepository.class);
        usageService = new UsageService(videoTaskRepository, agentStepRepository, runRepository);
    }

    @Test
    void byRun_zero_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> usageService.byRun(0));
        assertEquals("limit 参数非法", ex.getMessage());
        verify(runRepository, never()).findAllByOrderByCreatedAtDesc(any(PageRequest.class));
    }

    @Test
    void byRun_negative_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> usageService.byRun(-5));
        assertEquals("limit 参数非法", ex.getMessage());
        verify(runRepository, never()).findAllByOrderByCreatedAtDesc(any(PageRequest.class));
    }

    @Test
    void byRun_over500_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> usageService.byRun(501));
        assertEquals("limit 参数非法", ex.getMessage());
        verify(runRepository, never()).findAllByOrderByCreatedAtDesc(any(PageRequest.class));
    }

    @Test
    void byRun_one_returnsPageSizeOne() {
        when(runRepository.findAllByOrderByCreatedAtDesc(any(PageRequest.class))).thenReturn(List.of());

        List<UsageService.RunUsage> result = usageService.byRun(1);

        assertThat(result).isEmpty();
        ArgumentCaptor<PageRequest> captor = ArgumentCaptor.forClass(PageRequest.class);
        verify(runRepository).findAllByOrderByCreatedAtDesc(captor.capture());
        assertEquals(1, captor.getValue().getPageSize());
        assertEquals(0, captor.getValue().getPageNumber());
    }

    @Test
    void byRun_500_returnsPageSize500() {
        when(runRepository.findAllByOrderByCreatedAtDesc(any(PageRequest.class))).thenReturn(List.of());

        List<UsageService.RunUsage> result = usageService.byRun(500);

        assertThat(result).isEmpty();
        ArgumentCaptor<PageRequest> captor = ArgumentCaptor.forClass(PageRequest.class);
        verify(runRepository).findAllByOrderByCreatedAtDesc(captor.capture());
        assertEquals(500, captor.getValue().getPageSize());
        assertEquals(0, captor.getValue().getPageNumber());
    }
}
