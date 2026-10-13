package com.dramafactory.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDateTime;
import java.util.List;

import com.dramafactory.model.ProjectStatus;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.CharacterRole;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.model.FinalCutStatus;

public final class Records {

    private Records() {
    }

    public static record ProjectRequest(
            @NotBlank String title,
            String genre,
            String synopsis,
            ProjectStatus status,
            Integer targetEpisodes
    ) {
    }

    public static record ProjectResponse(
            Long id,
            String title,
            String genre,
            String synopsis,
            ProjectStatus status,
            Integer targetEpisodes,
            long episodeCount,
            long characterCount,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record EpisodeRequest(
            @NotNull Integer episodeNo,
            String title,
            String outline,
            EpisodeStatus status,
            Integer durationSec
    ) {
    }

    public static record EpisodeResponse(
            Long id,
            Long projectId,
            Integer episodeNo,
            String title,
            String outline,
            EpisodeStatus status,
            Integer durationSec,
            long sceneCount,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record CharacterRequest(
            @NotBlank String name,
            CharacterRole role,
            String description,
            String traits
    ) {
    }

    public static record CharacterResponse(
            Long id,
            Long projectId,
            String name,
            CharacterRole role,
            String description,
            String traits,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record SceneRequest(
            @NotNull Integer sceneNo,
            String location,
            String timeOfDay,
            String description,
            String dialogue,
            String prompt
    ) {
    }

    public static record SceneResponse(
            Long id,
            Long episodeId,
            Integer sceneNo,
            String location,
            String timeOfDay,
            String description,
            String dialogue,
            String prompt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record StatsResponse(
            long projects,
            long episodes,
            long characters,
            long scenes
    ) {
    }

    public static record GenerateScriptResponse(
            Long episodeId,
            int sceneCount,
            String scriptText
    ) {
    }

    public static record ErrorResponse(
            int status,
            String error,
            String message,
            LocalDateTime timestamp
    ) {
    }

    public static record ShotRequest(
            @NotNull Integer shotNo,
            ShotSize shotSize,
            CameraMove cameraMove,
            String description,
            Integer durationSeconds,
            String dialogue,
            String videoPrompt
    ) {
    }

    public static record ShotResponse(
            Long id,
            Long episodeId,
            Integer shotNo,
            ShotSize shotSize,
            String shotSizeLabel,
            CameraMove cameraMove,
            String cameraMoveLabel,
            String description,
            Integer durationSeconds,
            String dialogue,
            String videoPrompt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record ReorderRequest(
            List<Long> shotIds
    ) {
    }

    public static record VideoTaskResponse(
            Long id,
            Long shotId,
            String provider,
            String providerTaskId,
            VideoTaskStatus status,
            String statusLabel,
            Integer attempts,
            String videoUrl,
            Boolean hasLocalFile,
            String errorMessage,
            LocalDateTime nextRetryAt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record FinalCutResponse(
            Long id,
            Long episodeId,
            String title,
            String filePath,
            String fileName,
            FinalCutStatus status,
            String statusLabel,
            Double durationSeconds,
            String errorMessage,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record PipelineEpisodeView(
            Long episodeId,
            Integer episodeNo,
            String title,
            String status,
            long shotCount,
            long pendingTasks,
            long processingTasks,
            long doneTasks,
            long failedTasks,
            String finalCutStatus
    ) {
    }

    public static record PipelineProjectView(
            Long projectId,
            String title,
            List<PipelineEpisodeView> episodes
    ) {
    }
}
