package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.config.CurrentUser;
import com.dramafactory.exception.ForbiddenException;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.exception.ReviewConflictException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.ReviewHistory;
import com.dramafactory.model.ReviewItem;
import com.dramafactory.model.ReviewKind;
import com.dramafactory.model.ReviewStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ReviewHistoryRepository;
import com.dramafactory.repository.ReviewItemRepository;
import jakarta.persistence.OptimisticLockException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * 审核流服务：剧本两级审核、分镜一级审核，含乐观锁与历史审计。
 */
@Service
public class ReviewService {

    private final ReviewItemRepository reviewItemRepository;
    private final ReviewHistoryRepository reviewHistoryRepository;
    private final EpisodeRepository episodeRepository;
    private final CurrentUser currentUser;

    public ReviewService(ReviewItemRepository reviewItemRepository,
                         ReviewHistoryRepository reviewHistoryRepository,
                         EpisodeRepository episodeRepository,
                         CurrentUser currentUser) {
        this.reviewItemRepository = reviewItemRepository;
        this.reviewHistoryRepository = reviewHistoryRepository;
        this.episodeRepository = episodeRepository;
        this.currentUser = currentUser;
    }

    // ==================== 写操作 ====================

    @Transactional
    public Records.ReviewResult submit(Long episodeId, String kindName, int version) {
        Episode episode = requireOwner(episodeId);
        ReviewKind kind = parseKind(kindName);
        String actor = currentUser.currentUserId();

        ReviewItem item = reviewItemRepository.findByEpisodeIdAndKind(episodeId, kind).orElse(null);
        if (item == null) {
            // 不存在就先创建一条 DRAFT
            item = new ReviewItem();
            item.setEpisode(episode);
            item.setKind(kind);
            item.setStatus(ReviewStatus.DRAFT);
            item.setSubmittedBy(actor);
            item.setSubmittedAt(LocalDateTime.now());
            item = saveItem(item);
        }

        // 版本检查优先
        checkVersion(item, version);

        // 幂等：目标状态已经等于当前状态
        ReviewStatus target = (kind == ReviewKind.SCRIPT) ? ReviewStatus.PENDING_L1 : ReviewStatus.PENDING;
        if (item.getStatus() == target) {
            return new Records.ReviewResult(kind, item.getStatus(), item.getVersion(), false);
        }

        // 只有 DRAFT 才能 SUBMIT
        if (item.getStatus() != ReviewStatus.DRAFT) {
            throw new IllegalStateException("非法流转: from=" + item.getStatus()
                    + ", event=SUBMIT, to=" + target);
        }

        ReviewStatus from = item.getStatus();
        item.setStatus(target);
        item.setSubmittedBy(actor);
        item.setSubmittedAt(LocalDateTime.now());
        item = saveItem(item);

        writeHistory(item, from, target, "SUBMIT", actor, null);
        return new Records.ReviewResult(kind, item.getStatus(), item.getVersion(), true);
    }

    @Transactional
    public Records.ReviewResult l1Approve(Long episodeId, int version, String comment) {
        return doScriptL1(episodeId, version, comment, true);
    }

    @Transactional
    public Records.ReviewResult l1Reject(Long episodeId, int version, String comment) {
        return doScriptL1(episodeId, version, comment, false);
    }

    @Transactional
    public Records.ReviewResult l2Approve(Long episodeId, int version, String comment) {
        return doScriptL2(episodeId, version, comment, true);
    }

    @Transactional
    public Records.ReviewResult l2Reject(Long episodeId, int version, String comment) {
        return doScriptL2(episodeId, version, comment, false);
    }

    @Transactional
    public Records.ReviewResult boardApprove(Long episodeId, int version, String comment) {
        return doBoard(episodeId, version, comment, true);
    }

    @Transactional
    public Records.ReviewResult boardReject(Long episodeId, int version, String comment) {
        return doBoard(episodeId, version, comment, false);
    }

    // ==================== 查询 ====================

    @Transactional(readOnly = true)
    public Records.ReviewDetailResponse getReview(Long episodeId, String kindName) {
        requireOwner(episodeId);
        ReviewKind kind = parseKind(kindName);
        Optional<ReviewItem> found = reviewItemRepository.findByEpisodeIdAndKind(episodeId, kind);
        if (found.isEmpty()) {
            return new Records.ReviewDetailResponse(kind, ReviewStatus.DRAFT, 0,
                    null, null, null, null, false);
        }
        ReviewItem item = found.get();
        boolean selfReviewed = (item.getL1ReviewerId() != null && item.getL1ReviewerId().equals(item.getSubmittedBy()))
                || (item.getL2ReviewerId() != null && item.getL2ReviewerId().equals(item.getSubmittedBy()));
        return new Records.ReviewDetailResponse(kind, item.getStatus(), item.getVersion(),
                item.getSubmittedBy(), item.getL1ReviewerId(), item.getL2ReviewerId(),
                item.getLastComment(), selfReviewed);
    }

    @Transactional(readOnly = true)
    public List<Records.ReviewHistoryResponse> getHistory(Long episodeId, String kindName, int page, int size) {
        requireOwner(episodeId);
        ReviewKind kind = parseKind(kindName);
        Optional<ReviewItem> found = reviewItemRepository.findByEpisodeIdAndKind(episodeId, kind);
        if (found.isEmpty()) {
            return new ArrayList<>();
        }
        Page<ReviewHistory> pageResult = reviewHistoryRepository
                .findByReviewItemIdOrderByCreatedAtAsc(found.get().getId(), PageRequest.of(page, size));
        List<Records.ReviewHistoryResponse> result = new ArrayList<>();
        for (ReviewHistory h : pageResult.getContent()) {
            result.add(new Records.ReviewHistoryResponse(
                    h.getFromStatus() == null ? null : h.getFromStatus().name(),
                    h.getToStatus() == null ? null : h.getToStatus().name(),
                    h.getEvent(), h.getActorId(), h.getComment(), h.getCreatedAt()));
        }
        return result;
    }

    @Transactional(readOnly = true)
    public List<Records.ReviewQueueItem> queue(Long projectId, String kindName, String statusName) {
        String owner = currentUser.currentUserId();
        ReviewKind kind = null;
        if (kindName != null && !kindName.isBlank()) {
            kind = parseKind(kindName);
        }
        ReviewKind[] kinds = kind == null ? ReviewKind.values() : new ReviewKind[]{kind};
        ReviewStatus statusFilter = null;
        if (statusName != null && !statusName.isBlank()) {
            statusFilter = parseStatus(statusName);
        }

        List<Episode> episodes = episodeRepository.findByProjectIdOrderByEpisodeNoAsc(projectId);
        List<Records.ReviewQueueItem> result = new ArrayList<>();
        for (Episode ep : episodes) {
            // 队列只看自己的：非本人项目直接跳过
            if (ep.getProject() == null || !owner.equals(ep.getProject().getOwnerId())) {
                continue;
            }
            for (ReviewKind k : kinds) {
                Optional<ReviewItem> found = reviewItemRepository.findByEpisodeIdAndKind(ep.getId(), k);
                if (found.isEmpty()) {
                    continue;
                }
                ReviewItem item = found.get();
                if (statusFilter != null && item.getStatus() != statusFilter) {
                    continue;
                }
                result.add(new Records.ReviewQueueItem(ep.getId(), ep.getEpisodeNo(), ep.getTitle(),
                        k, item.getStatus(), item.getVersion(), item.getSubmittedBy()));
            }
        }
        return result;
    }

    // ==================== 重生成打回 ====================

    @Transactional
    public void resetOnScriptRegenerated(Long episodeId) {
        resetInternal(episodeId, ReviewKind.SCRIPT);
    }

    @Transactional
    public void resetOnBoardRegenerated(Long episodeId) {
        resetInternal(episodeId, ReviewKind.BOARD);
    }

    @Transactional(readOnly = true)
    public boolean isScriptApproved(Long episodeId) {
        Optional<ReviewItem> found = reviewItemRepository.findByEpisodeIdAndKind(episodeId, ReviewKind.SCRIPT);
        return found.isPresent() && found.get().getStatus() == ReviewStatus.APPROVED;
    }

    // ==================== 内部辅助 ====================

    private Records.ReviewResult doScriptL1(Long episodeId, int version, String comment, boolean approve) {
        Episode episode = requireOwner(episodeId);
        ReviewItem item = requireKind(episodeId, ReviewKind.SCRIPT);
        checkVersion(item, version);

        String actor = currentUser.currentUserId();
        ReviewStatus target = approve ? ReviewStatus.PENDING_L2 : ReviewStatus.DRAFT;
        String event = approve ? "L1_APPROVE" : "L1_REJECT";

        // 幂等
        if (item.getStatus() == target) {
            return new Records.ReviewResult(ReviewKind.SCRIPT, item.getStatus(), item.getVersion(), false);
        }

        // 状态前置：只有 PENDING_L1
        if (item.getStatus() != ReviewStatus.PENDING_L1) {
            throw new IllegalStateException("非法流转: from=" + item.getStatus()
                    + ", event=" + event + ", to=" + target);
        }

        ReviewStatus from = item.getStatus();
        item.setStatus(target);
        item.setL1ReviewerId(actor);
        item.setL1ReviewedAt(LocalDateTime.now());
        if (comment != null) {
            item.setLastComment(comment);
        }
        item = saveItem(item);

        writeHistory(item, from, target, event, actor, comment);
        return new Records.ReviewResult(ReviewKind.SCRIPT, item.getStatus(), item.getVersion(), true);
    }

    private Records.ReviewResult doScriptL2(Long episodeId, int version, String comment, boolean approve) {
        Episode episode = requireOwner(episodeId);
        ReviewItem item = requireKind(episodeId, ReviewKind.SCRIPT);
        checkVersion(item, version);

        String actor = currentUser.currentUserId();
        ReviewStatus target = approve ? ReviewStatus.APPROVED : ReviewStatus.REJECTED;
        String event = approve ? "L2_APPROVE" : "L2_REJECT";

        if (item.getStatus() == target) {
            return new Records.ReviewResult(ReviewKind.SCRIPT, item.getStatus(), item.getVersion(), false);
        }

        if (item.getStatus() != ReviewStatus.PENDING_L2) {
            throw new IllegalStateException("非法流转: from=" + item.getStatus()
                    + ", event=" + event + ", to=" + target);
        }

        ReviewStatus from = item.getStatus();
        item.setStatus(target);
        item.setL2ReviewerId(actor);
        item.setL2ReviewedAt(LocalDateTime.now());
        if (comment != null) {
            item.setLastComment(comment);
        }
        item = saveItem(item);

        writeHistory(item, from, target, event, actor, comment);
        return new Records.ReviewResult(ReviewKind.SCRIPT, item.getStatus(), item.getVersion(), true);
    }

    private Records.ReviewResult doBoard(Long episodeId, int version, String comment, boolean approve) {
        Episode episode = requireOwner(episodeId);
        ReviewItem item = requireKind(episodeId, ReviewKind.BOARD);
        checkVersion(item, version);

        String actor = currentUser.currentUserId();
        ReviewStatus target = approve ? ReviewStatus.APPROVED : ReviewStatus.DRAFT;
        String event = approve ? "APPROVE" : "REJECT";

        if (item.getStatus() == target) {
            return new Records.ReviewResult(ReviewKind.BOARD, item.getStatus(), item.getVersion(), false);
        }

        if (item.getStatus() != ReviewStatus.PENDING) {
            throw new IllegalStateException("非法流转: from=" + item.getStatus()
                    + ", event=" + event + ", to=" + target);
        }

        ReviewStatus from = item.getStatus();
        item.setStatus(target);
        if (approve) {
            item.setL1ReviewerId(actor);
            item.setL1ReviewedAt(LocalDateTime.now());
        }
        if (comment != null) {
            item.setLastComment(comment);
        }
        item = saveItem(item);

        writeHistory(item, from, target, event, actor, comment);
        return new Records.ReviewResult(ReviewKind.BOARD, item.getStatus(), item.getVersion(), true);
    }

    private void resetInternal(Long episodeId, ReviewKind kind) {
        Optional<Episode> episodeOpt = episodeRepository.findById(episodeId);
        if (episodeOpt.isEmpty()) {
            return;
        }
        Episode episode = episodeOpt.get();

        ReviewItem item = reviewItemRepository.findByEpisodeIdAndKind(episodeId, kind).orElse(null);
        if (item == null) {
            // 不存在就新建一条 DRAFT，不写历史
            item = new ReviewItem();
            item.setEpisode(episode);
            item.setKind(kind);
            item.setStatus(ReviewStatus.DRAFT);
            item.setSubmittedBy(null);
            item.setSubmittedAt(null);
            item.setL1ReviewerId(null);
            item.setL2ReviewerId(null);
            item.setLastComment(null);
            saveItem(item);
            return;
        }

        ReviewStatus from = item.getStatus();
        item.setStatus(ReviewStatus.DRAFT);
        item.setSubmittedBy(null);
        item.setSubmittedAt(null);
        item.setL1ReviewerId(null);
        item.setL1ReviewedAt(null);
        item.setL2ReviewerId(null);
        item.setL2ReviewedAt(null);
        item.setLastComment(null);
        item = saveItem(item);

        writeHistory(item, from, ReviewStatus.DRAFT, "REGENERATE", null, null);
    }

    private Episode requireOwner(Long episodeId) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
        String owner = episode.getProject() == null ? null : episode.getProject().getOwnerId();
        String current = currentUser.currentUserId();
        if (owner == null || current == null || !owner.equals(current)) {
            throw new ForbiddenException("Episode", episodeId);
        }
        return episode;
    }

    private ReviewItem requireKind(Long episodeId, ReviewKind expected) {
        Optional<ReviewItem> found = reviewItemRepository.findByEpisodeIdAndKind(episodeId, expected);
        if (found.isEmpty()) {
            throw new ResourceNotFoundException("ReviewItem", episodeId);
        }
        ReviewItem item = found.get();
        if (item.getKind() != expected) {
            throw new ResourceNotFoundException("ReviewItem", episodeId);
        }
        return item;
    }

    private void checkVersion(ReviewItem item, int version) {
        if (item.getVersion() != version) {
            throw new ReviewConflictException(item.getId(), item.getStatus(), item.getVersion());
        }
    }

    private ReviewItem saveItem(ReviewItem item) {
        try {
            return reviewItemRepository.save(item);
        } catch (OptimisticLockException e) {
            // 并发写入冲突，重新查库取最新状态后抛 409
            ReviewItem latest = reviewItemRepository.findById(item.getId()).orElse(item);
            throw new ReviewConflictException(latest.getId(), latest.getStatus(), latest.getVersion());
        }
    }

    private void writeHistory(ReviewItem item, ReviewStatus from, ReviewStatus to,
                              String event, String actor, String comment) {
        ReviewHistory history = new ReviewHistory();
        history.setReviewItem(item);
        history.setEpisodeId(item.getEpisode() == null ? null : item.getEpisode().getId());
        history.setKind(item.getKind());
        history.setFromStatus(from);
        history.setToStatus(to);
        history.setEvent(event);
        history.setActorId(actor);
        history.setComment(comment);
        history.setItemVersionAfter(item.getVersion());
        reviewHistoryRepository.save(history);
    }

    private ReviewKind parseKind(String kindName) {
        if (kindName == null || kindName.isBlank()) {
            throw new IllegalArgumentException("kind 不能为空");
        }
        try {
            return ReviewKind.valueOf(kindName);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("非法 kind: " + kindName);
        }
    }

    private ReviewStatus parseStatus(String statusName) {
        try {
            return ReviewStatus.valueOf(statusName);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("非法 status: " + statusName);
        }
    }
}
