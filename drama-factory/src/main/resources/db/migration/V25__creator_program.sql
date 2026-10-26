-- V25 creator program

CREATE TABLE creator_profiles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    handle VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    bio VARCHAR(500),
    website VARCHAR(500),
    owner_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_creator_profiles_owner_id ON creator_profiles (owner_id);

CREATE TABLE creator_follows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    creator_id BIGINT NOT NULL,
    follower_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_creator_follows_creator_follower UNIQUE (creator_id, follower_id)
);

CREATE INDEX idx_creator_follows_creator_id ON creator_follows (creator_id);
CREATE INDEX idx_creator_follows_follower_id ON creator_follows (follower_id);
