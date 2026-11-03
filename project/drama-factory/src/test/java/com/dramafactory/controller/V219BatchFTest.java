package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.service.PromptRecipeService;
import com.dramafactory.service.RunService;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class V219BatchFTest {

    @Test
    void render_requestNull_usesEmptyVariablesAndReturnsContent() {
        PromptRecipeService service = mock(PromptRecipeService.class);
        RecipeController controller = new RecipeController(service);
        when(service.render(eq(1L), eq(Map.of()))).thenReturn("hello");

        RecipeController.RenderResponse response = controller.render(1L, null);

        assertEquals("hello", response.content());
    }

    @Test
    void apply_requestNull_usesEmptyVariablesNullTargetAndReturnsResult() {
        PromptRecipeService service = mock(PromptRecipeService.class);
        RecipeController controller = new RecipeController(service);
        when(service.apply(eq(2L), eq(Map.of()), isNull()))
                .thenReturn(new PromptRecipeService.ApplyResult("rc", "mp", null));

        RecipeController.ApplyResponse response = controller.apply(2L, null);

        assertEquals("rc", response.renderedContent());
        assertNull(response.target());
    }

    @Test
    void list_singleRun_entersAndExitsLoopAndMapsToResponse() {
        RunService runService = mock(RunService.class);
        RunController controller = new RunController(runService);

        Run run = new Run();
        run.setId(1L);
        run.setGoal("g");
        run.setStatus(RunStatus.DRAFT);
        run.setProjectId(9L);

        when(runService.listRuns()).thenReturn(List.of(run));

        List<Records.RunResponse> result = controller.list();

        assertEquals(1, result.size());
        assertEquals(1L, result.get(0).id());
    }

    @Test
    void approve_requestNull_approvedFalseNoteNullAndReturnsDetail() {
        RunService runService = mock(RunService.class);
        RunController controller = new RunController(runService);
        Records.RunDetailResponse detail = mock(Records.RunDetailResponse.class);
        when(runService.getRun(3L)).thenReturn(detail);

        Records.RunDetailResponse response = controller.approve(3L, null);

        verify(runService).approve(3L, false, null);
        assertNotNull(response);
    }
}