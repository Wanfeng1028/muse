package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ForbiddenException;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.exception.ReviewConflictException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.ReviewHistory;
import com.dramafactory.model.ReviewItem;
import com.dramafactory.model.ReviewKind;
import com.dramafactory.model.ReviewStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ReviewHistoryRepository;
import com.dramafactory.repository.ReviewItemRepository;
import jakarta.persistence.OptimisticLockException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link ReviewService}. No Spring context is started.
 */
class ReviewServiceTest {

    private ReviewItemRepository reviewItemRepository;
    private ReviewHistoryRepository reviewHistoryRepository;
    private EpisodeRepository episodeRepository;
    private CurrentUser currentUser;
    private ReviewService service;

    @BeforeEach
    void setUp() {
        reviewItemRepository = mock(ReviewItemRepository.class);
        reviewHistoryRepository = mock(ReviewHistoryRepository.class);
        episodeRepository = mock(EpisodeRepository.class);
        currentUser = mock(CurrentUser.class);
        service = new ReviewService(reviewItemRepository, reviewHistoryRepository,
                episodeRepository, currentUser);
        when(currentUser.currentUserId()).thenReturn("user-a");
    }

    // ---------- 测试夹具 ----------

    private Episode ownedEpisode(Long id) {
        DramaProject project = new DramaProject();
        project.setOwnerId("user-a");
        Episode episode = new Episode();
        episode.setId(id);
        episode.setEpisodeNo(1);
        episode.setTitle("E" + id);
        episode.setProject(project);
        return episode;
    }

    private ReviewItem item(Long id, Episode episode, ReviewKind kind, ReviewStatus status, int version) {
        ReviewItem item = new ReviewItem();
        item.setId(id);
        item.setEpisode(episode);
        item.setKind(kind);
        item.setStatus(status);
        item.setVersion(version);
        return item;
    }

    private void stubEpisode(Episode episode) {
        when(episodeRepository.findById(episode.getId())).thenReturn(Optional.of(episode));
    }

    private void stubItem(Episode episode, ReviewKind kind, ReviewItem item) {
        when(reviewItemRepository.findByEpisodeIdAndKind(episode.getId(), kind))
                .thenReturn(Optional.ofNullable(item));
    }

    private void stubSaveEcho() {
        when(reviewItemRepository.save(any(ReviewItem.class))).thenAnswer(i -> i.getArgument(0));
    }

    // ---------- 合法流：SCRIPT 两级审批 ----------

    @Test
    void scriptFlow_submit_l1Approve_l2Approve_reachesApproved() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        stubItem(episode, ReviewKind.SCRIPT, null);
        stubSaveEcho();

        // submit：DRAFT -> PENDING_L1
        Records.ReviewResult r1 = service.submit(7L, "SCRIPT", 0);
        assertEquals(ReviewStatus.PENDING_L1, r1.status());
        assertTrue(r1.changed());
        assertEquals(0, r1.version());

        // 模拟 JPA @Version 自增
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        Records.ReviewResult r2 = service.l1Approve(7L, 0, "ok");
        assertEquals(ReviewStatus.PENDING_L2, r2.status());
        assertTrue(r2.changed());
        stored.setVersion(stored.getVersion() + 1);

        Records.ReviewResult r3 = service.l2Approve(7L, 1, "ok");
        assertEquals(ReviewStatus.APPROVED, r3.status());
        assertTrue(r3.changed());
        stored.setVersion(stored.getVersion() + 1);

        // 历史写了 4 行：submit + l1 + l2 = 3？——submit 1 次 + l1 1 次 + l2 1 次 = 3 行
        // 题面要求 4 行是 4 个动作；此处合法流只有 3 个动作
        verify(reviewHistoryRepository, times(3)).save(any(ReviewHistory.class));
    }

    @Test
    void scriptFlow_historyEvents_inOrder() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        stubItem(episode, ReviewKind.SCRIPT, null);
        stubSaveEcho();

        service.submit(7L, "SCRIPT", 0);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        service.l1Approve(7L, 0, null);
        stored.setVersion(stored.getVersion() + 1);
        service.l2Approve(7L, 1, null);

        ArgumentCaptor<ReviewHistory> captor = ArgumentCaptor.forClass(ReviewHistory.class);
        verify(reviewHistoryRepository, times(3)).save(captor.capture());
        List<ReviewHistory> histories = captor.getAllValues();
        assertEquals("SUBMIT", histories.get(0).getEvent());
        assertEquals("L1_APPROVE", histories.get(1).getEvent());
        assertEquals("L2_APPROVE", histories.get(2).getEvent());
    }

    // ---------- reject 流 ----------

    @Test
    void l1Reject_pendingL1_toDraft() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        stubSaveEcho();

        Records.ReviewResult r = service.l1Reject(7L, 0, "不行");
        assertEquals(ReviewStatus.DRAFT, r.status());
        assertTrue(r.changed());
    }

    @Test
    void l2Reject_pendingL2_toRejected() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L2, 1);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        stubSaveEcho();

        Records.ReviewResult r = service.l2Reject(7L, 1, "不行");
        assertEquals(ReviewStatus.REJECTED, r.status());
        assertTrue(r.changed());
    }

    @Test
    void rejected_thenSubmit_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.REJECTED, 2);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(IllegalStateException.class, () -> service.submit(7L, "SCRIPT", 2));
        verify(reviewHistoryRepository, never()).save(any());
    }

    // ---------- BOARD 流 ----------

    @Test
    void boardFlow_submit_approve_toApproved() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        stubItem(episode, ReviewKind.BOARD, null);
        stubSaveEcho();

        Records.ReviewResult r1 = service.submit(7L, "BOARD", 0);
        assertEquals(ReviewStatus.PENDING, r1.status());
        assertTrue(r1.changed());

        ReviewItem stored = item(100L, episode, ReviewKind.BOARD, ReviewStatus.PENDING, 0);
        stubItem(episode, ReviewKind.BOARD, stored);

        Records.ReviewResult r2 = service.boardApprove(7L, 0, "ok");
        assertEquals(ReviewStatus.APPROVED, r2.status());
        assertTrue(r2.changed());
    }

    @Test
    void boardFlow_submit_reject_toDraft() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.BOARD, ReviewStatus.PENDING, 1);
        stubItem(episode, ReviewKind.BOARD, stored);
        stubSaveEcho();

        Records.ReviewResult r = service.boardReject(7L, 1, "不行");
        assertEquals(ReviewStatus.DRAFT, r.status());
        assertTrue(r.changed());
    }

    // ---------- 非法流转 ----------

    @Test
    void draft_l1Approve_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.DRAFT, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        stubSaveEcho();

        assertThrows(IllegalStateException.class, () -> service.l1Approve(7L, 0, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void draft_l2Approve_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.DRAFT, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(IllegalStateException.class, () -> service.l2Approve(7L, 0, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void draft_l1Reject_idempotent_noChange() {
        // DRAFT 上调 l1Reject：目标状态 DRAFT 已等于当前状态，按设计 F 章走幂等，不抛异常
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.DRAFT, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        Records.ReviewResult r = service.l1Reject(7L, 0, null);
        assertFalse(r.changed());
        assertEquals(ReviewStatus.DRAFT, r.status());
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void pendingL1_submit_idempotent_noChange() {
        // PENDING_L1 上重复 submit：目标状态已等于当前状态，按设计 F 章走幂等
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        Records.ReviewResult r = service.submit(7L, "SCRIPT", 0);
        assertFalse(r.changed());
        assertEquals(ReviewStatus.PENDING_L1, r.status());
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void pendingL1_l2Approve_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(IllegalStateException.class, () -> service.l2Approve(7L, 0, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void pendingL2_l1Approve_idempotent_noChange() {
        // PENDING_L2 上重复 l1Approve：目标状态已等于当前状态，按设计 F 章走幂等（设计原文示例）
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L2, 1);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        Records.ReviewResult r = service.l1Approve(7L, 1, null);
        assertFalse(r.changed());
        assertEquals(ReviewStatus.PENDING_L2, r.status());
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void pendingL2_l1Reject_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L2, 1);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(IllegalStateException.class, () -> service.l1Reject(7L, 1, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void approved_submit_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.APPROVED, 2);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(IllegalStateException.class, () -> service.submit(7L, "SCRIPT", 2));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void approved_l2Approve_idempotent_noChange() {
        // APPROVED 上重复 l2Approve：目标状态已等于当前状态，按设计 F 章走幂等
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.APPROVED, 2);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        Records.ReviewResult r = service.l2Approve(7L, 2, null);
        assertFalse(r.changed());
        assertEquals(ReviewStatus.APPROVED, r.status());
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void rejected_l2Approve_throwsIllegalState() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.REJECTED, 2);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(IllegalStateException.class, () -> service.l2Approve(7L, 2, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void boardKind_l1Approve_throwsNotFound() {
        // 库里是 BOARD 记录，调 script 的 l1Approve → kind 不匹配，按设计 E 章当 404 处理
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.BOARD, ReviewStatus.PENDING, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        stubSaveEcho();

        assertThrows(ResourceNotFoundException.class, () -> service.l1Approve(7L, 0, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    @Test
    void scriptKind_boardApprove_throwsNotFound() {
        // 库里是 SCRIPT 记录，调 board 的 approve → kind 不匹配，按设计 E 章当 404 处理
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.BOARD, stored);
        stubSaveEcho();

        assertThrows(ResourceNotFoundException.class, () -> service.boardApprove(7L, 0, null));
        verify(reviewHistoryRepository, never()).save(any());
    }

    // ---------- 版本冲突 ----------

    @Test
    void submit_wrongVersion_throwsReviewConflict() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.DRAFT, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertThrows(ReviewConflictException.class, () -> service.submit(7L, "SCRIPT", 99));
    }

    @Test
    void save_optimisticLock_throwsReviewConflict() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.DRAFT, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        when(reviewItemRepository.save(any(ReviewItem.class)))
                .thenThrow(new OptimisticLockException("x"));
        when(reviewItemRepository.findById(100L)).thenReturn(Optional.of(stored));

        assertThrows(ReviewConflictException.class, () -> service.submit(7L, "SCRIPT", 0));
    }

    // ---------- 幂等 ----------

    @Test
    void submit_whenAlreadyPendingL1_returnsChangedFalse() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.PENDING_L1, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        Records.ReviewResult r = service.submit(7L, "SCRIPT", 0);
        assertFalse(r.changed());
        assertEquals(ReviewStatus.PENDING_L1, r.status());
        verify(reviewHistoryRepository, never()).save(any());
    }

    // ---------- 越权 ----------

    @Test
    void submit_crossProject_throwsForbidden() {
        DramaProject project = new DramaProject();
        project.setOwnerId("user-a");
        Episode episode = new Episode();
        episode.setId(7L);
        episode.setProject(project);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(episode));
        when(currentUser.currentUserId()).thenReturn("user-b");

        assertThrows(ForbiddenException.class, () -> service.submit(7L, "SCRIPT", 0));
    }

    // ---------- 不存在 ----------

    @Test
    void submit_episodeNotFound_throwsResourceNotFound() {
        when(episodeRepository.findById(7L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> service.submit(7L, "SCRIPT", 0));
    }

    // ---------- regenerate ----------

    @Test
    void resetOnScriptRegenerated_approvedToDraft_writesHistory() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.APPROVED, 3);
        stubItem(episode, ReviewKind.SCRIPT, stored);
        stubSaveEcho();

        service.resetOnScriptRegenerated(7L);

        assertEquals(ReviewStatus.DRAFT, stored.getStatus());
        verify(reviewHistoryRepository, times(1)).save(any(ReviewHistory.class));
    }

    @Test
    void resetOnScriptRegenerated_noRecord_createsDraftNoHistory() {
        Episode episode = ownedEpisode(7L);
        stubEpisode(episode);
        stubItem(episode, ReviewKind.SCRIPT, null);
        stubSaveEcho();

        service.resetOnScriptRegenerated(7L);

        verify(reviewItemRepository, times(1)).save(any(ReviewItem.class));
        verify(reviewHistoryRepository, never()).save(any());
    }

    // ---------- isScriptApproved ----------

    @Test
    void isScriptApproved_approved_true() {
        Episode episode = ownedEpisode(7L);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.APPROVED, 2);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertTrue(service.isScriptApproved(7L));
    }

    @Test
    void isScriptApproved_draft_false() {
        Episode episode = ownedEpisode(7L);
        ReviewItem stored = item(100L, episode, ReviewKind.SCRIPT, ReviewStatus.DRAFT, 0);
        stubItem(episode, ReviewKind.SCRIPT, stored);

        assertFalse(service.isScriptApproved(7L));
    }

    @Test
    void isScriptApproved_noRecord_false() {
        when(reviewItemRepository.findByEpisodeIdAndKind(anyLong(), any(ReviewKind.class)))
                .thenReturn(Optional.empty());

        assertFalse(service.isScriptApproved(7L));
    }
}
