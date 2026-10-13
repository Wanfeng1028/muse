package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class VideoTaskIdempotencyTest {

    @Autowired
    private VideoTaskService videoTaskService;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    private Shot createShot() {
        DramaProject project = new DramaProject();
        project.setTitle("测试项目");
        project = dramaProjectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode = episodeRepository.save(episode);

        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(1);
        return shotRepository.save(shot);
    }

    @Test
    void submitTwice_secondIsIdempotent() {
        Shot shot = createShot();

        Records.SubmitOutcome first = videoTaskService.submit(shot.getId());
        Records.SubmitOutcome second = videoTaskService.submit(shot.getId());

        assertThat(first.created()).isTrue();
        assertThat(second.created()).isFalse();
        assertThat(second.task().id()).isEqualTo(first.task().id());

        List<VideoTask> all = videoTaskRepository.findByShotIdOrderByIdDesc(shot.getId());
        assertThat(all).hasSize(1);
        assertThat(all.get(0).getStatus()).isEqualTo(VideoTaskStatus.PENDING);
    }

    @Test
    void submitAfterDone_createsNewTask() {
        Shot shot = createShot();

        Records.SubmitOutcome first = videoTaskService.submit(shot.getId());

        VideoTask task = videoTaskRepository.findById(first.task().id()).orElseThrow();
        task.setStatus(VideoTaskStatus.DONE);
        task.setNextRetryAt(LocalDateTime.now());
        videoTaskRepository.save(task);

        Records.SubmitOutcome second = videoTaskService.submit(shot.getId());

        assertThat(second.created()).isTrue();
        assertThat(second.task().id()).isNotEqualTo(first.task().id());

        List<VideoTask> all = videoTaskRepository.findByShotIdOrderByIdDesc(shot.getId());
        assertThat(all).hasSize(2);
    }

    @Test
    void submitAllForEpisode_isIdempotent() {
        Shot shot = createShot();

        List<Records.VideoTaskResponse> first = videoTaskService.submitAllForEpisode(shot.getEpisode().getId());
        List<Records.VideoTaskResponse> second = videoTaskService.submitAllForEpisode(shot.getEpisode().getId());

        assertThat(first).hasSize(1);
        assertThat(second).hasSize(1);
        assertThat(second.get(0).id()).isEqualTo(first.get(0).id());

        List<VideoTask> all = videoTaskRepository.findByShotIdOrderByIdDesc(shot.getId());
        assertThat(all).hasSize(1);
    }
}
