CREATE DATABASE IF NOT EXISTS content_ai
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE content_ai;

CREATE TABLE IF NOT EXISTS users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'user',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_users_user_id (user_id),
  INDEX ix_users_username (username),
  INDEX ix_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_contents (
  content_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(255) NOT NULL,
  video_url VARCHAR(1024) NULL,
  transcript LONGTEXT NULL,
  raw_transcript LONGTEXT NULL,
  cleaned_transcript LONGTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_user_contents_content_id (content_id),
  CONSTRAINT fk_user_contents_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS keywords (
  keyword_id INT AUTO_INCREMENT PRIMARY KEY,
  keyword VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS content_keywords (
  id INT AUTO_INCREMENT PRIMARY KEY,
  content_id INT NOT NULL,
  keyword_id INT NOT NULL,
  score FLOAT NOT NULL DEFAULT 0,
  CONSTRAINT fk_content_keywords_content
    FOREIGN KEY (content_id) REFERENCES user_contents(content_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_content_keywords_keyword
    FOREIGN KEY (keyword_id) REFERENCES keywords(keyword_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS clusters (
  cluster_id INT AUTO_INCREMENT PRIMARY KEY,
  cluster_name VARCHAR(150) NOT NULL UNIQUE,
  description TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS taxonomy_nodes (
  taxonomy_node_id INT AUTO_INCREMENT PRIMARY KEY,
  taxonomy_version VARCHAR(50) NOT NULL,
  node_key VARCHAR(100) NOT NULL,
  display_name VARCHAR(150) NOT NULL,
  display_name_th VARCHAR(150) NULL,
  level INT NOT NULL,
  parent_key VARCHAR(100) NULL,
  is_leaf BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_trainable BOOLEAN NOT NULL DEFAULT FALSE,
  minimum_sample_count INT NOT NULL DEFAULT 0,
  source_dataset VARCHAR(100) NULL,
  source_category VARCHAR(100) NULL,
  source_subcategory TEXT NULL,
  mapping_rule TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_taxonomy_version_node_key (taxonomy_version, node_key),
  INDEX ix_taxonomy_nodes_taxonomy_version (taxonomy_version),
  INDEX ix_taxonomy_nodes_version_level (taxonomy_version, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dataset_collection_runs (
  collection_run_id INT AUTO_INCREMENT PRIMARY KEY,
  run_key VARCHAR(64) NOT NULL,
    dataset_source VARCHAR(100) NOT NULL DEFAULT 'youtube_public_research',
  dataset_version VARCHAR(100) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'running',
  region_code VARCHAR(10) NOT NULL DEFAULT 'TH',
  languages_json TEXT NOT NULL,
  query_config_json TEXT NOT NULL,
  candidate_artifact_path VARCHAR(1024) NULL,
  candidate_artifact_sha256 VARCHAR(64) NULL,
  review_artifact_path VARCHAR(1024) NULL,
  review_artifact_sha256 VARCHAR(64) NULL,
  manifest_path VARCHAR(1024) NULL,
  manifest_sha256 VARCHAR(64) NULL,
  candidates_seen INT NOT NULL DEFAULT 0,
  transcripts_collected INT NOT NULL DEFAULT 0,
  duplicates_skipped INT NOT NULL DEFAULT 0,
  errors_count INT NOT NULL DEFAULT 0,
  resume_count INT NOT NULL DEFAULT 0,
  last_resumed_at DATETIME NULL,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_dataset_collection_runs_run_key (run_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dataset_contents (
  dataset_id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  video_url VARCHAR(1024) NULL,
  transcript LONGTEXT NULL,
  category VARCHAR(100) NULL,
  source_platform VARCHAR(50) NOT NULL DEFAULT 'youtube',
  dataset_source VARCHAR(100) NOT NULL DEFAULT 'legacy',
  dataset_version VARCHAR(100) NOT NULL DEFAULT 'legacy-v1',
  collection_run_id INT NULL,
  source_record_id VARCHAR(255) NULL,
  source_youtube_id VARCHAR(32) NULL,
  source_creator VARCHAR(255) NULL,
  source_channel_id VARCHAR(64) NULL,
  source_category VARCHAR(100) NULL,
  source_subcategory VARCHAR(100) NULL,
  collection_query VARCHAR(255) NULL,
  source_release_url VARCHAR(1024) NULL,
  source_archive_sha256 VARCHAR(64) NULL,
  source_annotation_path VARCHAR(1024) NULL,
  source_annotation_sha256 VARCHAR(64) NULL,
  import_batch_id VARCHAR(64) NULL,
  taxonomy_version VARCHAR(50) NOT NULL DEFAULT 'legacy-v1',
  taxonomy_leaf_key VARCHAR(100) NULL,
  category_level_1 VARCHAR(150) NULL,
  category_level_2 VARCHAR(150) NULL,
  category_level_3 VARCHAR(150) NULL,
  language VARCHAR(20) NOT NULL DEFAULT 'und',
  verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
  label_source VARCHAR(100) NOT NULL DEFAULT 'unverified',
  license_name VARCHAR(100) NOT NULL DEFAULT 'unknown',
  license_url VARCHAR(1024) NULL,
  data_split VARCHAR(20) NOT NULL DEFAULT 'unassigned',
  split_strategy VARCHAR(100) NULL,
  creator_group_key VARCHAR(64) NULL,
  transcript_sha256 VARCHAR(64) NULL,
  transcript_segment_count INT NOT NULL DEFAULT 0,
  transcript_start_seconds FLOAT NULL,
  transcript_end_seconds FLOAT NULL,
  transcript_window_seconds INT NULL,
  transcript_source VARCHAR(50) NULL,
  transcript_acquisition_method VARCHAR(64) NOT NULL DEFAULT 'youtube_transcript_api',
  transcript_scope VARCHAR(32) NOT NULL DEFAULT 'first_window',
  transcript_timestamps_available BOOLEAN NOT NULL DEFAULT TRUE,
  caption_type VARCHAR(50) NULL,
  transcript_quality VARCHAR(30) NULL,
  reviewed_by VARCHAR(255) NULL,
  reviewed_at DATETIME NULL,
  review_notes TEXT NULL,
  statistics_captured_at DATETIME NULL,
  view_metric_version VARCHAR(64) NOT NULL DEFAULT 'unknown_v1',
  license_verified_at DATETIME NULL,
  raw_metadata_json TEXT NULL,
  collection_strategy VARCHAR(50) NULL,
  average_views_per_day FLOAT NOT NULL DEFAULT 0,
  engagement_rate FLOAT NOT NULL DEFAULT 0,
  is_training_eligible BOOLEAN NOT NULL DEFAULT FALSE,
  is_keyword_recommendation_eligible BOOLEAN NOT NULL DEFAULT FALSE,
  is_duration_recommendation_eligible BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  views INT NOT NULL DEFAULT 0,
  likes INT NOT NULL DEFAULT 0,
  comments INT NOT NULL DEFAULT 0,
  trend_score FLOAT NOT NULL DEFAULT 0,
  duration_seconds INT NULL,
  published_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_dataset_source_version_record (dataset_source, dataset_version, source_record_id),
  UNIQUE KEY uq_dataset_source_youtube_id (source_youtube_id),
  UNIQUE KEY uq_dataset_transcript_sha256 (transcript_sha256),
  INDEX ix_dataset_contents_taxonomy_leaf_key (taxonomy_leaf_key),
  INDEX ix_dataset_contents_creator_group_key (creator_group_key),
  INDEX ix_dataset_contents_source_channel_id (source_channel_id),
  INDEX ix_dataset_contents_collection_run_id (collection_run_id),
  INDEX ix_dataset_taxonomy_leaf (taxonomy_version, taxonomy_leaf_key),
  INDEX ix_dataset_training_eligibility (is_training_eligible, data_split, taxonomy_leaf_key),
  INDEX ix_dataset_view_metric_leaf (view_metric_version, taxonomy_leaf_key),
  CONSTRAINT fk_dataset_contents_collection_run
    FOREIGN KEY (collection_run_id) REFERENCES dataset_collection_runs(collection_run_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dataset_review_events (
  review_event_id INT AUTO_INCREMENT PRIMARY KEY,
  collection_run_id INT NOT NULL,
  dataset_id INT NULL,
  source_youtube_id VARCHAR(32) NOT NULL,
  decision VARCHAR(20) NOT NULL,
  proposed_leaf_key VARCHAR(100) NULL,
  reviewed_leaf_key VARCHAR(100) NULL,
  transcript_quality VARCHAR(30) NULL,
  reviewer VARCHAR(255) NOT NULL,
  notes TEXT NULL,
  review_artifact_sha256 VARCHAR(64) NOT NULL,
  reviewed_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_dataset_review_events_collection_run_id (collection_run_id),
  INDEX ix_dataset_review_events_dataset_id (dataset_id),
  INDEX ix_dataset_review_source_video (source_youtube_id, reviewed_at),
  CONSTRAINT fk_dataset_review_events_collection_run
    FOREIGN KEY (collection_run_id) REFERENCES dataset_collection_runs(collection_run_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_dataset_review_events_dataset
    FOREIGN KEY (dataset_id) REFERENCES dataset_contents(dataset_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS classification_models (
  model_id INT AUTO_INCREMENT PRIMARY KEY,
  model_key VARCHAR(100) NOT NULL,
  model_version VARCHAR(100) NOT NULL,
  taxonomy_version VARCHAR(50) NOT NULL,
  model_type VARCHAR(100) NOT NULL,
  artifact_path VARCHAR(1024) NULL,
  training_dataset_source VARCHAR(100) NULL,
  training_dataset_version VARCHAR(100) NULL,
  training_sample_count INT NOT NULL DEFAULT 0,
  status VARCHAR(30) NOT NULL DEFAULT 'draft',
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  trained_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_classification_model_key_version (model_key, model_version),
  INDEX ix_classification_models_active (is_active, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS model_evaluation_metrics (
  metric_id INT AUTO_INCREMENT PRIMARY KEY,
  model_id INT NOT NULL,
  dataset_split VARCHAR(20) NOT NULL DEFAULT 'test',
  language VARCHAR(20) NOT NULL DEFAULT 'und',
  taxonomy_level INT NOT NULL,
  taxonomy_leaf_key VARCHAR(100) NOT NULL DEFAULT '__overall__',
  metric_name VARCHAR(50) NOT NULL,
  metric_value FLOAT NOT NULL,
  sample_size INT NOT NULL DEFAULT 0,
  details TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_model_evaluation_metric (
    model_id, dataset_split, language, taxonomy_level, taxonomy_leaf_key, metric_name
  ),
  INDEX ix_model_evaluation_metrics_model_id (model_id),
  CONSTRAINT fk_model_evaluation_metrics_model
    FOREIGN KEY (model_id) REFERENCES classification_models(model_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS trending_items (
  item_id INT AUTO_INCREMENT PRIMARY KEY,
  keyword VARCHAR(255) NOT NULL,
  score FLOAT NOT NULL DEFAULT 0,
  source VARCHAR(100) NOT NULL DEFAULT 'unknown',
  domain VARCHAR(100) NULL,
  fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  meta TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_trending_items_keyword (keyword)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS analysis_results (
  result_id INT AUTO_INCREMENT PRIMARY KEY,
  content_id INT NOT NULL,
  cluster_id INT NULL,
  dataset_id INT NULL,
  classification_model_id INT NULL,
  taxonomy_version VARCHAR(50) NULL,
  taxonomy_leaf_key VARCHAR(100) NULL,
  category_level_1 VARCHAR(150) NULL,
  category_level_2 VARCHAR(150) NULL,
  category_level_3 VARCHAR(150) NULL,
  classification_confidence FLOAT NULL,
  classification_is_unknown BOOLEAN NOT NULL DEFAULT FALSE,
  summary TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_analysis_results_content
    FOREIGN KEY (content_id) REFERENCES user_contents(content_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_analysis_results_cluster
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_analysis_results_dataset
    FOREIGN KEY (dataset_id) REFERENCES dataset_contents(dataset_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_analysis_results_classification_model
    FOREIGN KEY (classification_model_id) REFERENCES classification_models(model_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cluster_runs (
  run_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  algorithm VARCHAR(50) NOT NULL DEFAULT 'kmeans',
  n_clusters INT NOT NULL,
  feature_dimension INT NOT NULL DEFAULT 0,
  inertia FLOAT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_cluster_runs_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cluster_memberships (
  membership_id INT AUTO_INCREMENT PRIMARY KEY,
  run_id INT NOT NULL,
  cluster_id INT NOT NULL,
  content_id INT NULL,
  dataset_id INT NULL,
  item_text TEXT NOT NULL,
  top_terms TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_cluster_memberships_run
    FOREIGN KEY (run_id) REFERENCES cluster_runs(run_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_cluster_memberships_cluster
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_cluster_memberships_content
    FOREIGN KEY (content_id) REFERENCES user_contents(content_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_cluster_memberships_dataset
    FOREIGN KEY (dataset_id) REFERENCES dataset_contents(dataset_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recommendations (
  rec_id INT AUTO_INCREMENT PRIMARY KEY,
  content_id INT NOT NULL,
  recommended_keywords TEXT NULL,
  recommended_duration INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_recommendations_content
    FOREIGN KEY (content_id) REFERENCES user_contents(content_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS system_configs (
  config_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  max_keywords INT NOT NULL DEFAULT 10,
  hook_duration INT NOT NULL DEFAULT 60,
  process_interval INT NOT NULL DEFAULT 24,
  notification_batch_size INT NOT NULL DEFAULT 50,
  youtube_region VARCHAR(2) NOT NULL DEFAULT 'TH',
  google_region VARCHAR(2) NOT NULL DEFAULT 'TH',
  tiktok_region VARCHAR(2) NOT NULL DEFAULT 'TH',
  enable_youtube_trending BOOLEAN NOT NULL DEFAULT TRUE,
  enable_google_trends BOOLEAN NOT NULL DEFAULT TRUE,
  enable_tiktok_trending BOOLEAN NOT NULL DEFAULT TRUE,
  auto_scan_interval_hours INT NOT NULL DEFAULT 6,
  asr_model_default VARCHAR(20) NOT NULL DEFAULT 'small',
  enable_model_toggle BOOLEAN NOT NULL DEFAULT TRUE,
  job_backend VARCHAR(20) NOT NULL DEFAULT 'inprocess',
  redis_url VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_system_configs_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS system_logs (
  log_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  action VARCHAR(255) NOT NULL,
  status VARCHAR(50) NOT NULL,
  detail TEXT NULL,
  timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_system_logs_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS trend_snapshot_runs (
  run_id INT AUTO_INCREMENT PRIMARY KEY,
  region VARCHAR(10) NOT NULL DEFAULT 'TH',
  snapshot_kind VARCHAR(32) NOT NULL DEFAULT 'global',
  status VARCHAR(20) NOT NULL DEFAULT 'running',
  provider_status TEXT NOT NULL,
  total_items INT NOT NULL DEFAULT 0,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  INDEX ix_trend_snapshot_runs_region (region),
  INDEX ix_trend_snapshot_run_kind_region (snapshot_kind, region, status),
  INDEX ix_trend_snapshot_runs_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_trend_watch_sessions (
  watch_session_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  session_key VARCHAR(64) NOT NULL,
  baseline_run_id INT NULL,
  last_seen_run_id INT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ended_at DATETIME NULL,
  UNIQUE KEY uq_user_trend_watch_session_key (session_key),
  INDEX ix_user_trend_watch_sessions_user (user_id),
  CONSTRAINT fk_user_trend_watch_sessions_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_user_trend_watch_sessions_baseline_run
    FOREIGN KEY (baseline_run_id) REFERENCES trend_snapshot_runs(run_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_user_trend_watch_sessions_last_seen_run
    FOREIGN KEY (last_seen_run_id) REFERENCES trend_snapshot_runs(run_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notifications (
  notification_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  watch_session_id INT NOT NULL,
  type VARCHAR(50) NOT NULL DEFAULT 'new_live_trend',
  trend_key VARCHAR(40) NOT NULL,
  platform VARCHAR(50) NOT NULL,
  title VARCHAR(500) NOT NULL,
  category VARCHAR(100) NOT NULL DEFAULT 'general',
  detected_at DATETIME NOT NULL,
  payload TEXT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_notification_user_session_trend (user_id, watch_session_id, trend_key),
  INDEX ix_notifications_user_session (user_id, watch_session_id),
  CONSTRAINT fk_notifications_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_notifications_watch_session
    FOREIGN KEY (watch_session_id) REFERENCES user_trend_watch_sessions(watch_session_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS trend_snapshot_items (
  item_id INT AUTO_INCREMENT PRIMARY KEY,
  run_id INT NOT NULL,
  platform VARCHAR(50) NOT NULL,
  ranking_scope VARCHAR(64) NOT NULL DEFAULT 'global',
  category_id VARCHAR(32) NULL,
  provider_rank INT NOT NULL DEFAULT 0,
  trend_key VARCHAR(40) NOT NULL,
  title VARCHAR(500) NOT NULL,
  category VARCHAR(100) NOT NULL DEFAULT 'general',
  source_platform VARCHAR(100) NOT NULL,
  video_url VARCHAR(1024) NULL,
  channel_title VARCHAR(255) NULL,
  thumbnail_url VARCHAR(1024) NULL,
  description TEXT NULL,
  duration_seconds INT NULL,
  views INT NOT NULL DEFAULT 0,
  likes INT NOT NULL DEFAULT 0,
  comments INT NOT NULL DEFAULT 0,
  views_available BOOLEAN NULL,
  likes_available BOOLEAN NULL,
  comments_available BOOLEAN NULL,
  search_volume INT NULL,
  trend_score FLOAT NOT NULL DEFAULT 0,
  engagement_signal FLOAT NOT NULL DEFAULT 0,
  view_metric_version VARCHAR(64) NOT NULL DEFAULT 'unknown_v1',
  published_at VARCHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_trend_snapshot_item_run_scope_key (run_id, platform, ranking_scope, trend_key),
  INDEX ix_trend_snapshot_items_run_id (run_id),
  INDEX ix_trend_snapshot_items_platform (platform),
  INDEX ix_trend_snapshot_scope_category (ranking_scope, category_id, provider_rank),
  INDEX ix_trend_snapshot_platform_metric (platform, view_metric_version),
  CONSTRAINT fk_trend_snapshot_items_run
    FOREIGN KEY (run_id) REFERENCES trend_snapshot_runs(run_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS followed_topics (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  match_type VARCHAR(20) NOT NULL,
  value VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_followed_topics_value (value),
  CONSTRAINT fk_followed_topics_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
