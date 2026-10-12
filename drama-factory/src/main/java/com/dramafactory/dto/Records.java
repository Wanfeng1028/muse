package com.dramafactory.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDateTime;

import com.dramafactory.model.ProjectStatus;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.CharacterRole;

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
}
