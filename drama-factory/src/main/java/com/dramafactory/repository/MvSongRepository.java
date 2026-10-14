package com.dramafactory.repository;

import com.dramafactory.model.MvSong;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface MvSongRepository extends JpaRepository<MvSong, Long> {

    Optional<MvSong> findByRunId(Long runId);
}
