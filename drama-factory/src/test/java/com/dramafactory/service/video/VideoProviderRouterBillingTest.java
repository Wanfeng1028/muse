package com.dramafactory.service.video;

import com.dramafactory.billing.BillingProperties;
import com.dramafactory.billing.BudgetExceededException;
import com.dramafactory.billing.BudgetMode;
import com.dramafactory.billing.BudgetPolicy;
import com.dramafactory.billing.CostLedgerService;
import com.dramafactory.billing.ProviderCostEstimator;
import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * VideoProviderRouter 计费相关行为测试。
 */
class VideoProviderRouterBillingTest {

    private interface SubmitBehavior {
        String submit(String name);
    }

    private static VideoProvider stubProvider(String name, SubmitBehavior behavior) {
        return new VideoProvider() {
            @Override
            public String name() {
                return name;
            }

            @Override
            public String submit(Shot shot, int seconds) {
                return behavior.submit(name);
            }

            @Override
            public VideoProvider.ProbeResult poll(String taskId) {
                throw new UnsupportedOperationException();
            }
        };
    }

    private static BudgetPolicy warnPolicy() {
        return new BudgetPolicy(BudgetMode.WARN, 1000d, 0.1);
    }

    private static BudgetPolicy capPolicy() {
        return new BudgetPolicy(BudgetMode.CAP, 1000d, 0.1);
    }

    @Test
    void billingEnabled_preferredProviderSucceeds_recordsEstimateAndReserve() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        Environment env = mock(Environment.class);
        CostLedgerService costLedgerService = mock(CostLedgerService.class);
        ProviderCostEstimator costEstimator = mock(ProviderCostEstimator.class);
        BillingProperties billingProperties = mock(BillingProperties.class);

        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        when(billingProperties.isEnabled()).thenReturn(true);
        when(billingProperties.toBudgetPolicy()).thenReturn(warnPolicy());

        when(costEstimator.estimate(any(), eq(10))).thenReturn(0.8);
        when(costLedgerService.recordEstimate(any(), anyString(), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(101L);

        VideoProvider agnes = stubProvider("agnes", name -> name + "-task");
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null, null,
                costLedgerService, costEstimator, billingProperties);

        Shot shot = new Shot();
        VideoProviderRouter.RouteResult result = router.submit(shot, 10);

        assertNotNull(result);
        assertEquals("agnes", result.providerName());
        assertEquals(101L, result.ledgerEntryId());

        verify(costLedgerService, times(1)).recordEstimate(isNull(), eq("agnes"), eq("agnes"),
                eq("video-generate"), eq(0.8), anyString());
        verify(costLedgerService, times(1)).reserve(eq(101L), any(BudgetPolicy.class));
        verify(costLedgerService, never()).refund(any());
    }

    @Test
    void billingEnabled_preferredFails_fallsBackAndRefunds() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        Environment env = mock(Environment.class);
        CostLedgerService costLedgerService = mock(CostLedgerService.class);
        ProviderCostEstimator costEstimator = mock(ProviderCostEstimator.class);
        BillingProperties billingProperties = mock(BillingProperties.class);

        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        when(billingProperties.isEnabled()).thenReturn(true);
        when(billingProperties.toBudgetPolicy()).thenReturn(warnPolicy());

        when(costEstimator.estimate(any(), eq(10))).thenReturn(0.8);
        when(costLedgerService.recordEstimate(any(), eq("agnes"), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(101L);
        when(costLedgerService.recordEstimate(any(), eq("minimax"), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(202L);

        VideoProvider agnes = stubProvider("agnes", name -> {
            throw new RuntimeException("agnes failed");
        });
        VideoProvider minimax = stubProvider("minimax", name -> name + "-task");
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null, null,
                costLedgerService, costEstimator, billingProperties);

        Shot shot = new Shot();
        VideoProviderRouter.RouteResult result = router.submit(shot, 10);

        assertNotNull(result);
        assertEquals("minimax", result.providerName());
        assertEquals(202L, result.ledgerEntryId());

        verify(costLedgerService, times(1)).refund(eq(101L));
        verify(costLedgerService, times(1)).reserve(eq(202L), any(BudgetPolicy.class));
    }

    @Test
    void capBudgetExceeded_skipsProviderAndFallsBackWithoutRefund() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        Environment env = mock(Environment.class);
        CostLedgerService costLedgerService = mock(CostLedgerService.class);
        ProviderCostEstimator costEstimator = mock(ProviderCostEstimator.class);
        BillingProperties billingProperties = mock(BillingProperties.class);

        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        when(billingProperties.isEnabled()).thenReturn(true);
        when(billingProperties.toBudgetPolicy()).thenReturn(capPolicy());

        when(costEstimator.estimate(any(), eq(10))).thenReturn(0.8);
        when(costLedgerService.recordEstimate(any(), eq("agnes"), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(101L);
        when(costLedgerService.recordEstimate(any(), eq("minimax"), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(202L);

        org.mockito.Mockito.doThrow(new BudgetExceededException("cap exceeded"))
                .when(costLedgerService).reserve(eq(101L), any(BudgetPolicy.class));

        VideoProvider agnes = stubProvider("agnes", name -> name + "-task");
        VideoProvider minimax = stubProvider("minimax", name -> name + "-task");
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null, null,
                costLedgerService, costEstimator, billingProperties);

        Shot shot = new Shot();
        VideoProviderRouter.RouteResult result = router.submit(shot, 10);

        assertNotNull(result);
        assertEquals("minimax", result.providerName());
        assertEquals(202L, result.ledgerEntryId());

        verify(costLedgerService, never()).refund(any());
        verify(costLedgerService, times(1)).reserve(eq(202L), any(BudgetPolicy.class));
    }

    @Test
    void billingDisabled_doesNotTouchLedger() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        Environment env = mock(Environment.class);
        CostLedgerService costLedgerService = mock(CostLedgerService.class);
        ProviderCostEstimator costEstimator = mock(ProviderCostEstimator.class);
        BillingProperties billingProperties = mock(BillingProperties.class);

        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        when(billingProperties.isEnabled()).thenReturn(false);

        VideoProvider agnes = stubProvider("agnes", name -> name + "-task");
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null, null,
                costLedgerService, costEstimator, billingProperties);

        Shot shot = new Shot();
        VideoProviderRouter.RouteResult result = router.submit(shot, 10);

        assertNotNull(result);
        assertEquals("agnes", result.providerName());
        assertNull(result.ledgerEntryId());

        verify(costLedgerService, never()).recordEstimate(any(), anyString(), anyString(), anyString(), anyDouble(), anyString());
        verify(costLedgerService, never()).reserve(any(), any());
        verify(costLedgerService, never()).refund(any());
    }

    @Test
    void legacyConstructor_submitsWithoutLedger() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        Environment env = mock(Environment.class);

        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");

        VideoProvider agnes = stubProvider("agnes", name -> name + "-task");
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null, null, null, null, null);

        Shot shot = new Shot();
        VideoProviderRouter.RouteResult result = router.submit(shot, 10);

        assertNotNull(result);
        assertEquals("agnes", result.providerName());
        assertNull(result.ledgerEntryId());
    }

    @Test
    void allProvidersFail_throwsAndRefundsEachEntry() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        Environment env = mock(Environment.class);
        CostLedgerService costLedgerService = mock(CostLedgerService.class);
        ProviderCostEstimator costEstimator = mock(ProviderCostEstimator.class);
        BillingProperties billingProperties = mock(BillingProperties.class);

        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        when(billingProperties.isEnabled()).thenReturn(true);
        when(billingProperties.toBudgetPolicy()).thenReturn(warnPolicy());

        when(costEstimator.estimate(any(), eq(10))).thenReturn(0.8);
        when(costLedgerService.recordEstimate(any(), eq("agnes"), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(101L);
        when(costLedgerService.recordEstimate(any(), eq("minimax"), anyString(), anyString(), anyDouble(), anyString()))
                .thenReturn(202L);

        VideoProvider agnes = stubProvider("agnes", name -> {
            throw new RuntimeException("agnes failed");
        });
        VideoProvider minimax = stubProvider("minimax", name -> {
            throw new RuntimeException("minimax failed");
        });
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null, null,
                costLedgerService, costEstimator, billingProperties);

        Shot shot = new Shot();
        RuntimeException ex = assertThrows(RuntimeException.class, () -> router.submit(shot, 10));
        assertTrue(ex.getMessage() != null && ex.getMessage().contains("所有视频通道均失败"));

        verify(costLedgerService, times(1)).refund(eq(101L));
        verify(costLedgerService, times(1)).refund(eq(202L));
    }
}
