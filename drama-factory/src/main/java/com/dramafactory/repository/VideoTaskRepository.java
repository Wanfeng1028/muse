package com.dramafactory.repository;

import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import com.dramafactory.service.UsageService;

/**
 * 视频生成任务数据访问层。
 */
public interface VideoTaskRepository extends JpaRepository<VideoTask, Long> {

    /**
     * 按状态计数（指标采集用）。
     *
     * @param status 任务状态
     * @return 该状态的任务数量
     */
    long countByStatus(VideoTaskStatus status);

    /**
     * 查询处于指定状态集合、且下次重试时间已到（早于等于给定时间）的任务，按主键升序排列。
     * 用于后台调度重试。
     *
     * @param statuses 任务状态集合
     * @param time     当前时间（含）
     * @return 待重试任务列表
     */
    List<VideoTask> findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(List<VideoTaskStatus> statuses, LocalDateTime time);

    /**
     * 查询某分镜下的所有视频任务，按主键倒序（最新的在前）。
     *
     * @param shotId 分镜 ID
     * @return 任务列表
     */
    List<VideoTask> findByShotIdOrderByIdDesc(Long shotId);

    /**
     * 查询某分镜下最近一次的视频任务。
     *
     * @param shotId 分镜 ID
     * @return 最新任务
     */
    Optional<VideoTask> findFirstByShotIdOrderByIdDesc(Long shotId);

    /**
     * 查询某剧集下所有分镜关联的视频任务（跨分镜聚合）。
     *
     * @param episodeId 剧集 ID
     * @return 任务列表
     */
    @Query("select t from VideoTask t where t.shot.episode.id = :episodeId")
    List<VideoTask> findByEpisodeId(@Param("episodeId") Long episodeId);

    /**
     * 查询指定 Shot 下处于给定状态集合中的第一条任务（按 id 升序）。
     * 用于幂等提交：判断是否存在 PENDING / PROCESSING 的进行中任务。
     */
    Optional<VideoTask> findFirstByShotIdAndStatusInOrderByIdAsc(Long shotId, Collection<VideoTaskStatus> statuses);


    @Query("SELECT SUM(v.tokensUsed) FROM VideoTask v")
    Long sumTokensUsed();

    @Query("SELECT SUM(v.costCents) FROM VideoTask v")
    Long sumCostCents();

    @Query("SELECT v.modelUsed AS modelUsed, v.tokensUsed AS tokensUsed, v.costCents AS costCents, v.createdAt AS createdAt FROM VideoTask v")
    List<UsageService.VideoTaskRow> findAllForModelUsage();

    @Query("SELECT v.modelUsed AS modelUsed, v.tokensUsed AS tokensUsed, v.costCents AS costCents, v.createdAt AS createdAt FROM VideoTask v WHERE v.createdAt >= :from")
    List<UsageService.VideoTaskRow> findForDailyUsage(@Param("from") LocalDateTime from);
}
