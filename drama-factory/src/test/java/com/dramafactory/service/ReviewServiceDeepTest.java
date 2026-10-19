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
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ReviewHistoryRepository;
import com.dramafactory.repository.ReviewItemRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

/**
 * Deep integration tests for {@link ReviewService} using a real Spring context and an
 * isolated in-memory H2 database.
 *
 * <p>Only the {@link CurrentUser} dependency is mocked via {@code @MockBean}; all
 * persistence goes through real repositories backed by H2. The reason a test double is
 * used for {@link CurrentUser} is that the production implementation reads from an HTTP
 * request scoped attribute that is not reachable inside a plain JUnit test.</p>
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:reviewdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class ReviewServiceDeepTest {

    @Autowired
    private ReviewService reviewService;

    @Autowired
    private ReviewItemRepository reviewItemRepository;

    @Autowired
    private ReviewHistoryRepository reviewHistoryRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @MockBean
    private CurrentUser currentUser;

    @BeforeEach
    void cleanState() {
        reviewHistoryRepository.deleteAll();
        reviewItemRepository.deleteAll();
        episodeRepository.deleteAll();
        dramaProjectRepository.deleteAll();
        when(currentUser.currentUserId()).thenReturn("user-a");
    }

    // ------------------------------------------------------------------
    // fixtures
    // ------------------------------------------------------------------

    private Episode persistEpisode(String owner, long episodeNo, String title) {
        DramaProject project = new DramaProject();
        project.setOwnerId(owner);
        project.setTitle("proj-" + owner + "-" + episodeNo);
        project = dramaProjectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo((int) episodeNo);
        episode.setTitle(title);
        return episodeRepository.save(episode);
    }

    // ------------------------------------------------------------------
    // submit
    // ------------------------------------------------------------------

    @Test
    void submit_whenNoItemExists_createsDraftThenTransitionsToPendingL1AndWritesHistory() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");

        Records.ReviewResult result = reviewService.submit(episode.getId(), "SCRIPT", 0);

        assertThat(result.kind()).isEqualTo(ReviewKind.SCRIPT);
        assertThat(result.status()).isEqualTo(ReviewStatus.PENDING_L1);
        assertThat(result.changed()).isTrue();

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT)
                .orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.PENDING_L1);
        assertThat(stored.getSubmittedBy()).isEqualTo("user-a");

        List<ReviewHistory> histories = reviewHistoryRepository
                .findByReviewItemIdOrderByCreatedAtAsc(stored.getId(), org.springframework.data.domain.PageRequest.of(0, 10))
                .getContent();
        assertThat(histories).hasSize(1);
        assertThat(histories.get(0).getEvent()).isEqualTo("SUBMIT");
        assertThat(histories.get(0).getFromStatus()).isEqualTo(ReviewStatus.DRAFT);
        assertThat(histories.get(0).getToStatus()).isEqualTo(ReviewStatus.PENDING_L1);
        assertThat(histories.get(0).getActorId()).isEqualTo("user-a");
    }

    @Test
    void submit_whenAlreadyPendingL1_isIdempotentAndWritesNoHistory() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        Records.ReviewResult first = reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem afterFirst = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        long historyCountAfterFirst = reviewHistoryRepository.count();

        Records.ReviewResult second = reviewService.submit(episode.getId(), "SCRIPT", afterFirst.getVersion());

        assertThat(first.changed()).isTrue();
        assertThat(second.changed()).isFalse();
        assertThat(second.status()).isEqualTo(ReviewStatus.PENDING_L1);
        assertThat(reviewHistoryRepository.count()).isEqualTo(historyCountAfterFirst);
    }

    @Test
    void submit_withIllegalKind_throwsIllegalArgumentExceptionAndPersistsNothing() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");

        assertThatThrownBy(() -> reviewService.submit(episode.getId(), "NOT_A_KIND", 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("NOT_A_KIND");

        assertThat(reviewItemRepository.count()).isZero();
        assertThat(reviewHistoryRepository.count()).isZero();
    }

    // ------------------------------------------------------------------
    // state machine approve / reject
    // ------------------------------------------------------------------

    @Test
    void scriptApproveFlow_submitThenL1ThenL2_reachesApprovedAndWritesFullHistory() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");

        reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();

        Records.ReviewResult l1 = reviewService.l1Approve(episode.getId(), item.getVersion(), "l1 ok");
        assertThat(l1.status()).isEqualTo(ReviewStatus.PENDING_L2);
        assertThat(l1.changed()).isTrue();

        item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        Records.ReviewResult l2 = reviewService.l2Approve(episode.getId(), item.getVersion(), "l2 ok");
        assertThat(l2.status()).isEqualTo(ReviewStatus.APPROVED);
        assertThat(l2.changed()).isTrue();

        item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        assertThat(item.getStatus()).isEqualTo(ReviewStatus.APPROVED);
        assertThat(item.getL1ReviewerId()).isEqualTo("user-a");
        assertThat(item.getL2ReviewerId()).isEqualTo("user-a");
        assertThat(item.getLastComment()).isEqualTo("l2 ok");

        List<ReviewHistory> histories = reviewHistoryRepository
                .findByReviewItemIdOrderByCreatedAtAsc(item.getId(),
                        org.springframework.data.domain.PageRequest.of(0, 20))
                .getContent();
        assertThat(histories).extracting(ReviewHistory::getEvent)
                .containsExactly("SUBMIT", "L1_APPROVE", "L2_APPROVE");
    }

    @Test
    void l1Reject_whenPendingL1_movesBackToDraftAndPersistsHistory() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();

        Records.ReviewResult result = reviewService.l1Reject(episode.getId(), item.getVersion(), "redo");

        assertThat(result.status()).isEqualTo(ReviewStatus.DRAFT);
        assertThat(result.changed()).isTrue();

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.DRAFT);

        List<ReviewHistory> histories = reviewHistoryRepository
                .findByReviewItemIdOrderByCreatedAtAsc(stored.getId(),
                        org.springframework.data.domain.PageRequest.of(0, 20))
                .getContent();
        assertThat(histories).extracting(ReviewHistory::getEvent)
                .containsExactly("SUBMIT", "L1_REJECT");
    }

    @Test
    void l2Approve_whenStillPendingL1_throwsIllegalStateAndDoesNotMutateState() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        long historyBefore = reviewHistoryRepository.count();

        assertThatThrownBy(() -> reviewService.l2Approve(episode.getId(), item.getVersion(), "too early"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("L2_APPROVE");

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.PENDING_L1);
        assertThat(reviewHistoryRepository.count()).isEqualTo(historyBefore);
    }

    @Test
    void boardApprove_whenStatusIsDraft_throwsIllegalStateAndKeepsDraft() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "BOARD", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.BOARD).orElseThrow();
        reviewService.boardReject(episode.getId(), item.getVersion(), "back to draft");

        ReviewItem afterReject = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.BOARD).orElseThrow();
        assertThat(afterReject.getStatus()).isEqualTo(ReviewStatus.DRAFT);

        assertThatThrownBy(() -> reviewService.boardApprove(
                episode.getId(), afterReject.getVersion(), "approve from draft"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("APPROVE");

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.BOARD).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.DRAFT);
    }

    // ------------------------------------------------------------------
    // version / optimistic lock
    // ------------------------------------------------------------------

    @Test
    void submit_withStaleVersion_throwsReviewConflictException() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        int staleVersion = item.getVersion() + 99;

        assertThatThrownBy(() -> reviewService.submit(episode.getId(), "SCRIPT", staleVersion))
                .isInstanceOf(ReviewConflictException.class);
    }

    @Test
    void concurrentApprovalsOnSameItem_onlyOneSucceedsAndOtherThrowsConflict() throws Exception {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        int versionAtRead = item.getVersion();

        int threads = 4;
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch go = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger conflict = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    ready.countDown();
                    try {
                        go.await(5, TimeUnit.SECONDS);
                        reviewService.l1Approve(episode.getId(), versionAtRead, "concurrent");
                        success.incrementAndGet();
                    } catch (ReviewConflictException | org.springframework.orm.ObjectOptimisticLockingFailureException e) {
                        conflict.incrementAndGet();
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    } catch (RuntimeException re) {
                        conflict.incrementAndGet();
                    } finally {
                        done.countDown();
                    }
                });
            }
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            go.countDown();
            assertThat(done.await(20, TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }

        assertThat(success.get()).isEqualTo(1);
        assertThat(conflict.get()).isEqualTo(threads - 1);

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.PENDING_L2);

        List<ReviewHistory> histories = reviewHistoryRepository
                .findByReviewItemIdOrderByCreatedAtAsc(stored.getId(),
                        org.springframework.data.domain.PageRequest.of(0, 20))
                .getContent();
        assertThat(histories).extracting(ReviewHistory::getEvent)
                .containsExactly("SUBMIT", "L1_APPROVE");
    }

    // ------------------------------------------------------------------
    // ownership / not found
    // ------------------------------------------------------------------

    @Test
    void submit_whenCurrentUserIsNotOwner_throwsForbiddenException() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        when(currentUser.currentUserId()).thenReturn("user-b");

        assertThatThrownBy(() -> reviewService.submit(episode.getId(), "SCRIPT", 0))
                .isInstanceOf(ForbiddenException.class);

        assertThat(reviewItemRepository.count()).isZero();
        assertThat(reviewHistoryRepository.count()).isZero();
    }

    @Test
    void getReview_whenCurrentUserIsNotOwner_throwsForbiddenException() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        when(currentUser.currentUserId()).thenReturn("user-b");

        assertThatThrownBy(() -> reviewService.getReview(episode.getId(), "SCRIPT"))
                .isInstanceOf(ForbiddenException.class);
    }

    @Test
    void submit_whenEpisodeDoesNotExist_throwsResourceNotFoundException() {
        assertThatThrownBy(() -> reviewService.submit(999_999L, "SCRIPT", 0))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void l1Approve_whenKindIsBoardOnly_throwsResourceNotFoundException() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "BOARD", 0);

        assertThatThrownBy(() -> reviewService.l1Approve(episode.getId(), 0, "wrong kind"))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // ------------------------------------------------------------------
    // concurrency: submit idempotency per (episode, kind)
    // ------------------------------------------------------------------

    @Test
    void concurrentSubmitOnSameEpisodeAndKind_leavesExactlyOneReviewItem() throws Exception {
        Episode episode = persistEpisode("user-a", 1, "ep-1");

        int threads = 6;
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch go = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    ready.countDown();
                    try {
                        go.await(5, TimeUnit.SECONDS);
                        reviewService.submit(episode.getId(), "SCRIPT", 0);
                    } catch (RuntimeException ignored) {
                        // conflicting writers are expected to fail; we assert final state
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                });
            }
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            go.countDown();
            assertThat(done.await(20, TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }

        List<ReviewItem> items = reviewItemRepository
                .findAll()
                .stream()
                .filter(it -> it.getKind() == ReviewKind.SCRIPT
                        && it.getEpisode() != null
                        && episode.getId().equals(it.getEpisode().getId()))
                .toList();
        assertThat(items).hasSize(1);
        assertThat(items.get(0).getStatus()).isEqualTo(ReviewStatus.PENDING_L1);
    }

    // ------------------------------------------------------------------
    // reset / regenerate audit
    // ------------------------------------------------------------------

    @Test
    void resetOnScriptRegenerated_whenApproved_movesToDraftAndWritesRegenerateHistory() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");
        reviewService.submit(episode.getId(), "SCRIPT", 0);
        ReviewItem item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        reviewService.l1Approve(episode.getId(), item.getVersion(), "ok");
        item = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        reviewService.l2Approve(episode.getId(), item.getVersion(), "ok");

        reviewService.resetOnScriptRegenerated(episode.getId());

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.DRAFT);
        assertThat(stored.getSubmittedBy()).isNull();
        assertThat(stored.getL1ReviewerId()).isNull();
        assertThat(stored.getL2ReviewerId()).isNull();

        List<ReviewHistory> histories = reviewHistoryRepository
                .findByReviewItemIdOrderByCreatedAtAsc(stored.getId(),
                        org.springframework.data.domain.PageRequest.of(0, 20))
                .getContent();
        assertThat(histories).extracting(ReviewHistory::getEvent)
                .containsExactly("SUBMIT", "L1_APPROVE", "L2_APPROVE", "REGENERATE");
        ReviewHistory regenerate = histories.get(histories.size() - 1);
        assertThat(regenerate.getFromStatus()).isEqualTo(ReviewStatus.APPROVED);
        assertThat(regenerate.getToStatus()).isEqualTo(ReviewStatus.DRAFT);
    }

    @Test
    void resetOnScriptRegenerated_whenNoItem_createsDraftWithoutHistory() {
        Episode episode = persistEpisode("user-a", 1, "ep-1");

        reviewService.resetOnScriptRegenerated(episode.getId());

        ReviewItem stored = reviewItemRepository
                .findByEpisodeIdAndKind(episode.getId(), ReviewKind.SCRIPT).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ReviewStatus.DRAFT);
        assertThat(reviewHistoryRepository.count()).isZero();
    }
}
