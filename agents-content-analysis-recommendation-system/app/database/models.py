from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR
from sqlalchemy.orm import relationship

from .db import Base


TranscriptText = Text().with_variant(LONGTEXT(), "mysql")
AnalysisPayloadText = Text().with_variant(LONGTEXT(), "mysql")


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    contents = relationship("UserContent", back_populates="owner", cascade="all, delete-orphan")
    logs = relationship("SystemLog", back_populates="user")
    configs = relationship("SystemConfig", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    followed_topics = relationship("FollowedTopic", back_populates="user", cascade="all, delete-orphan")
    trend_watch_sessions = relationship(
        "UserTrendWatchSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserContent(Base):
    __tablename__ = "user_contents"

    content_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    title = Column(String(255), nullable=False)
    video_url = Column(String(1024))
    transcript = Column(TranscriptText)
    raw_transcript = Column(TranscriptText)
    cleaned_transcript = Column(TranscriptText)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="contents")
    analysis_results = relationship("AnalysisResult", back_populates="content", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="content", cascade="all, delete-orphan")
    content_keywords = relationship("ContentKeyword", back_populates="content", cascade="all, delete-orphan")


class Keyword(Base):
    __tablename__ = "keywords"

    keyword_id = Column(Integer, primary_key=True)
    keyword = Column(String(100), unique=True, nullable=False)

    content_keywords = relationship("ContentKeyword", back_populates="keyword_ref")


class ContentKeyword(Base):
    __tablename__ = "content_keywords"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("user_contents.content_id"), nullable=False)
    keyword_id = Column(Integer, ForeignKey("keywords.keyword_id"), nullable=False)
    score = Column(Float, nullable=False, default=0.0)

    content = relationship("UserContent", back_populates="content_keywords")
    keyword_ref = relationship("Keyword", back_populates="content_keywords")


class Cluster(Base):
    __tablename__ = "clusters"

    cluster_id = Column(Integer, primary_key=True)
    cluster_name = Column(String(150), nullable=False, unique=True)
    description = Column(Text)

    analysis_results = relationship("AnalysisResult", back_populates="cluster")
    memberships = relationship("ClusterMembership", back_populates="cluster", cascade="all, delete-orphan")


class TaxonomyNode(Base):
    __tablename__ = "taxonomy_nodes"
    __table_args__ = (
        UniqueConstraint("taxonomy_version", "node_key", name="uq_taxonomy_version_node_key"),
        Index("ix_taxonomy_nodes_version_level", "taxonomy_version", "level"),
    )

    taxonomy_node_id = Column(Integer, primary_key=True)
    taxonomy_version = Column(String(50), nullable=False, index=True)
    node_key = Column(String(100), nullable=False)
    display_name = Column(String(150), nullable=False)
    display_name_th = Column(String(150))
    level = Column(Integer, nullable=False)
    parent_key = Column(String(100))
    is_leaf = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_trainable = Column(Boolean, nullable=False, default=False)
    minimum_sample_count = Column(Integer, nullable=False, default=0)
    source_dataset = Column(String(100))
    source_category = Column(String(100))
    source_subcategory = Column(Text)
    mapping_rule = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DatasetCollectionRun(Base):
    __tablename__ = "dataset_collection_runs"

    collection_run_id = Column(Integer, primary_key=True)
    run_key = Column(String(64), nullable=False, unique=True, index=True)
    dataset_source = Column(
        String(100), nullable=False, default="youtube_public_research"
    )
    dataset_version = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default="running")
    region_code = Column(String(10), nullable=False, default="TH")
    languages_json = Column(Text, nullable=False)
    query_config_json = Column(Text, nullable=False)
    candidate_artifact_path = Column(String(1024))
    candidate_artifact_sha256 = Column(String(64))
    review_artifact_path = Column(String(1024))
    review_artifact_sha256 = Column(String(64))
    manifest_path = Column(String(1024))
    manifest_sha256 = Column(String(64))
    candidates_seen = Column(Integer, nullable=False, default=0)
    transcripts_collected = Column(Integer, nullable=False, default=0)
    duplicates_skipped = Column(Integer, nullable=False, default=0)
    errors_count = Column(Integer, nullable=False, default=0)
    resume_count = Column(Integer, nullable=False, default=0)
    last_resumed_at = Column(DateTime)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    contents = relationship("DatasetContent", back_populates="collection_run")
    review_events = relationship(
        "DatasetReviewEvent",
        back_populates="collection_run",
        cascade="all, delete-orphan",
    )


class DatasetContent(Base):
    __tablename__ = "dataset_contents"
    __table_args__ = (
        UniqueConstraint(
            "dataset_source",
            "dataset_version",
            "source_record_id",
            name="uq_dataset_source_version_record",
        ),
        UniqueConstraint("source_youtube_id", name="uq_dataset_source_youtube_id"),
        UniqueConstraint("transcript_sha256", name="uq_dataset_transcript_sha256"),
        Index("ix_dataset_taxonomy_leaf", "taxonomy_version", "taxonomy_leaf_key"),
        Index(
            "ix_dataset_training_eligibility",
            "is_training_eligible",
            "data_split",
            "taxonomy_leaf_key",
        ),
        Index(
            "ix_dataset_view_metric_leaf",
            "view_metric_version",
            "taxonomy_leaf_key",
        ),
    )

    dataset_id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    video_url = Column(String(1024))
    transcript = Column(TranscriptText)
    category = Column(String(100))
    source_platform = Column(String(50), nullable=False, default="youtube")
    dataset_source = Column(String(100), nullable=False, default="legacy")
    dataset_version = Column(String(100), nullable=False, default="legacy-v1")
    collection_run_id = Column(
        Integer,
        ForeignKey("dataset_collection_runs.collection_run_id", ondelete="SET NULL"),
        index=True,
    )
    source_record_id = Column(String(255))
    source_youtube_id = Column(String(32))
    source_creator = Column(String(255))
    source_channel_id = Column(String(64), index=True)
    source_category = Column(String(100))
    source_subcategory = Column(String(100))
    collection_query = Column(String(255))
    source_release_url = Column(String(1024))
    source_archive_sha256 = Column(String(64))
    source_annotation_path = Column(String(1024))
    source_annotation_sha256 = Column(String(64))
    import_batch_id = Column(String(64))
    taxonomy_version = Column(String(50), nullable=False, default="legacy-v1")
    taxonomy_leaf_key = Column(String(100), index=True)
    category_level_1 = Column(String(150))
    category_level_2 = Column(String(150))
    category_level_3 = Column(String(150))
    language = Column(String(20), nullable=False, default="und")
    verification_status = Column(String(30), nullable=False, default="unverified")
    label_source = Column(String(100), nullable=False, default="unverified")
    license_name = Column(String(100), nullable=False, default="unknown")
    license_url = Column(String(1024))
    data_split = Column(String(20), nullable=False, default="unassigned")
    split_strategy = Column(String(100))
    creator_group_key = Column(String(64), index=True)
    transcript_sha256 = Column(String(64))
    transcript_segment_count = Column(Integer, nullable=False, default=0)
    transcript_start_seconds = Column(Float)
    transcript_end_seconds = Column(Float)
    transcript_window_seconds = Column(Integer)
    transcript_source = Column(String(50))
    transcript_acquisition_method = Column(
        String(64), nullable=False, default="youtube_transcript_api"
    )
    transcript_scope = Column(String(32), nullable=False, default="first_window")
    transcript_timestamps_available = Column(Boolean, nullable=False, default=True)
    caption_type = Column(String(50))
    transcript_quality = Column(String(30))
    reviewed_by = Column(String(255))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    statistics_captured_at = Column(DateTime)
    view_metric_version = Column(
        String(64),
        nullable=False,
        default="unknown_v1",
    )
    license_verified_at = Column(DateTime)
    raw_metadata_json = Column(Text)
    collection_strategy = Column(String(50))
    average_views_per_day = Column(Float, nullable=False, default=0.0)
    engagement_rate = Column(Float, nullable=False, default=0.0)
    is_training_eligible = Column(Boolean, nullable=False, default=False)
    is_keyword_recommendation_eligible = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_duration_recommendation_eligible = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    views = Column(BigInteger, nullable=False, default=0)
    deleted_at = Column(DateTime)
    deletion_state_json = Column(Text)
    likes = Column(BigInteger, nullable=False, default=0)
    comments = Column(BigInteger, nullable=False, default=0)
    trend_score = Column(Float, nullable=False, default=0.0)
    duration_seconds = Column(Integer)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    analysis_results = relationship("AnalysisResult", back_populates="dataset")
    memberships = relationship("ClusterMembership", back_populates="dataset")
    collection_run = relationship("DatasetCollectionRun", back_populates="contents")
    review_events = relationship("DatasetReviewEvent", back_populates="dataset")


class DatasetReviewEvent(Base):
    __tablename__ = "dataset_review_events"
    __table_args__ = (
        Index("ix_dataset_review_source_video", "source_youtube_id", "reviewed_at"),
    )

    review_event_id = Column(Integer, primary_key=True)
    collection_run_id = Column(
        Integer,
        ForeignKey("dataset_collection_runs.collection_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id = Column(
        Integer,
        ForeignKey("dataset_contents.dataset_id", ondelete="SET NULL"),
        index=True,
    )
    source_youtube_id = Column(String(32), nullable=False)
    decision = Column(String(20), nullable=False)
    proposed_leaf_key = Column(String(100))
    reviewed_leaf_key = Column(String(100))
    transcript_quality = Column(String(30))
    reviewer = Column(String(255), nullable=False)
    notes = Column(Text)
    review_artifact_sha256 = Column(String(64), nullable=False)
    reviewed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    collection_run = relationship("DatasetCollectionRun", back_populates="review_events")
    dataset = relationship("DatasetContent", back_populates="review_events")


class ModelTrainingRun(Base):
    __tablename__ = "model_training_runs"

    run_id = Column(String(36), primary_key=True)
    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    status = Column(String(30), nullable=False, default="queued", index=True)
    # NULL permits completed history; slot 1 admits only one live training run.
    active_slot = Column(Integer, nullable=True, unique=True)
    stage = Column(String(40), nullable=False, default="queued")
    current_model_key = Column(String(100))
    parameters_json = Column(Text, nullable=False)
    result_json = Column(AnalysisPayloadText)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime)


class ClassificationModel(Base):
    __tablename__ = "classification_models"
    __table_args__ = (
        UniqueConstraint("model_key", "model_version", name="uq_classification_model_key_version"),
        Index("ix_classification_models_active", "is_active", "status"),
    )

    model_id = Column(Integer, primary_key=True)
    model_key = Column(String(100), nullable=False)
    model_version = Column(String(100), nullable=False)
    taxonomy_version = Column(String(50), nullable=False)
    model_type = Column(String(100), nullable=False)
    artifact_path = Column(String(1024))
    training_dataset_source = Column(String(100))
    training_dataset_version = Column(String(100))
    training_sample_count = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="draft")
    is_active = Column(Boolean, nullable=False, default=False)
    trained_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    evaluation_metrics = relationship(
        "ModelEvaluationMetric",
        back_populates="model",
        cascade="all, delete-orphan",
    )
    analysis_results = relationship("AnalysisResult", back_populates="classification_model")


class ModelEvaluationMetric(Base):
    __tablename__ = "model_evaluation_metrics"
    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "dataset_split",
            "language",
            "taxonomy_level",
            "taxonomy_leaf_key",
            "metric_name",
            name="uq_model_evaluation_metric",
        ),
    )

    metric_id = Column(Integer, primary_key=True)
    model_id = Column(
        Integer,
        ForeignKey("classification_models.model_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_split = Column(String(20), nullable=False, default="test")
    language = Column(String(20), nullable=False, default="und")
    taxonomy_level = Column(Integer, nullable=False)
    taxonomy_leaf_key = Column(String(100), nullable=False, default="__overall__")
    metric_name = Column(String(50), nullable=False)
    metric_value = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False, default=0)
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    model = relationship("ClassificationModel", back_populates="evaluation_metrics")


class TrendingItem(Base):
    __tablename__ = "trending_items"

    item_id = Column(Integer, primary_key=True)
    keyword = Column(String(255), nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    source = Column(String(100), nullable=False, default="unknown")
    domain = Column(String(100), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    meta = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    result_id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("user_contents.content_id"), nullable=False)
    cluster_id = Column(Integer, ForeignKey("clusters.cluster_id"))
    dataset_id = Column(Integer, ForeignKey("dataset_contents.dataset_id"))
    classification_model_id = Column(Integer, ForeignKey("classification_models.model_id"))
    taxonomy_version = Column(String(50))
    taxonomy_leaf_key = Column(String(100))
    category_level_1 = Column(String(150))
    category_level_2 = Column(String(150))
    category_level_3 = Column(String(150))
    classification_confidence = Column(Float)
    classification_is_unknown = Column(Boolean, nullable=False, default=False)
    summary = Column(AnalysisPayloadText)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    content = relationship("UserContent", back_populates="analysis_results")
    cluster = relationship("Cluster", back_populates="analysis_results")
    dataset = relationship("DatasetContent", back_populates="analysis_results")
    classification_model = relationship("ClassificationModel", back_populates="analysis_results")
    revision_plan = relationship("ClipRevisionPlan", back_populates="analysis", uselist=False, cascade="all, delete-orphan")


class ClipRevisionPlan(Base):
    __tablename__ = "clip_revision_plans"

    analysis_id = Column(Integer, ForeignKey("analysis_results.result_id", ondelete="CASCADE"), primary_key=True)
    recommendation_fingerprint = Column(String(64), nullable=False)
    selected_advice_ids = Column(Text, nullable=False, default="[]")
    notes = Column(Text, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    analysis = relationship("AnalysisResult", back_populates="revision_plan")


class ClipRevisionComparison(Base):
    __tablename__ = "clip_revision_comparisons"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_request_id",
            name="uq_clip_revision_comparison_user_request",
        ),
        Index("ix_clip_revision_comparison_job", "job_id"),
        Index("ix_clip_revision_comparison_child", "child_content_id"),
    )

    comparison_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    parent_content_id = Column(
        Integer,
        ForeignKey("user_contents.content_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_analysis_id = Column(
        Integer,
        ForeignKey("analysis_results.result_id", ondelete="CASCADE"),
        nullable=False,
    )
    child_content_id = Column(
        Integer,
        ForeignKey("user_contents.content_id", ondelete="SET NULL"),
    )
    child_analysis_id = Column(
        Integer,
        ForeignKey("analysis_results.result_id", ondelete="SET NULL"),
    )
    parent_recommendation_fingerprint = Column(String(64), nullable=False)
    plan_revision = Column(Integer, nullable=False)
    client_request_id = Column(String(100), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    file_path = Column(String(1024), nullable=False)
    original_filename = Column(String(255), nullable=False)
    job_id = Column(String(64), nullable=False, unique=True)
    job_backend = Column(String(20), nullable=False, default="inprocess")
    status = Column(String(30), nullable=False, default="queued")
    stage = Column(String(50), nullable=False, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    error_code = Column(String(100))
    error_message = Column(String(500))
    plan_snapshot_json = Column(AnalysisPayloadText, nullable=False)
    settings_snapshot_json = Column(AnalysisPayloadText, nullable=False)
    comparison_result_json = Column(AnalysisPayloadText)
    snapshot_sha256 = Column(String(64), nullable=False)
    captured_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ClusterRun(Base):
    __tablename__ = "cluster_runs"

    run_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    algorithm = Column(String(50), nullable=False, default="kmeans")
    n_clusters = Column(Integer, nullable=False)
    feature_dimension = Column(Integer, nullable=False, default=0)
    inertia = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    memberships = relationship("ClusterMembership", back_populates="run", cascade="all, delete-orphan")


class ClusterMembership(Base):
    __tablename__ = "cluster_memberships"

    membership_id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("cluster_runs.run_id"), nullable=False)
    cluster_id = Column(Integer, ForeignKey("clusters.cluster_id"), nullable=False)
    content_id = Column(Integer, ForeignKey("user_contents.content_id"))
    dataset_id = Column(Integer, ForeignKey("dataset_contents.dataset_id"))
    item_text = Column(Text, nullable=False)
    top_terms = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("ClusterRun", back_populates="memberships")
    cluster = relationship("Cluster", back_populates="memberships")
    dataset = relationship("DatasetContent", back_populates="memberships")


class Recommendation(Base):
    __tablename__ = "recommendations"

    rec_id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("user_contents.content_id"), nullable=False)
    recommended_keywords = Column(AnalysisPayloadText)
    recommended_duration = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    content = relationship("UserContent", back_populates="recommendations")


class DatasetSplitPlan(Base):
    __tablename__ = "dataset_split_plans"

    plan_version = Column(String(100), primary_key=True)
    plan_sha256 = Column(String(64), nullable=False)
    payload_json = Column(AnalysisPayloadText, nullable=False)
    created_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    config_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    max_keywords = Column(Integer, nullable=False, default=10)
    hook_duration = Column(Integer, nullable=False, default=60)
    process_interval = Column(Integer, nullable=False, default=24)
    notification_batch_size = Column(Integer, nullable=False, default=50)
    youtube_region = Column(String(2), nullable=False, default="TH")
    google_region = Column(String(2), nullable=False, default="TH")
    tiktok_region = Column(String(2), nullable=False, default="TH")
    enable_youtube_trending = Column(Boolean, nullable=False, default=True)
    enable_google_trends = Column(Boolean, nullable=False, default=True)
    enable_tiktok_trending = Column(Boolean, nullable=False, default=True)
    auto_scan_interval_hours = Column(Integer, nullable=False, default=6)
    trend_refresh_enabled = Column(Boolean, nullable=False, default=True)
    trend_refresh_seconds = Column(Integer)
    trend_schedule_mode = Column(String(20), nullable=False, default="interval")
    trend_window_start_hour = Column(Integer, nullable=False, default=14)
    trend_window_end_hour = Column(Integer, nullable=False, default=23)
    trend_worker_seen_at = Column(DateTime)
    trend_worker_status = Column(String(40))
    youtube_category_refresh_seconds = Column(Integer)
    trend_notification_mode = Column(String(20), nullable=False, default="all")
    # New runtime/admin-configurable fields
    asr_model_default = Column(String(20), nullable=False, default="small")
    upload_max_duration_seconds = Column(Integer, nullable=False, default=300)
    enable_model_toggle = Column(Boolean, nullable=False, default=True)
    job_backend = Column(String(20), nullable=False, default='inprocess')
    redis_url = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="configs")


class SystemLog(Base):
    __tablename__ = "system_logs"

    log_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    action = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)
    detail = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="logs")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "watch_session_id",
            "trend_key",
            name="uq_notification_user_session_trend",
        ),
    )

    notification_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    watch_session_id = Column(
        Integer,
        ForeignKey("user_trend_watch_sessions.watch_session_id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(String(50), nullable=False, default="new_live_trend")
    trend_key = Column(String(40), nullable=False)
    platform = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, default="general")
    detected_at = Column(DateTime, nullable=False)
    payload = Column(Text)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="notifications")
    watch_session = relationship("UserTrendWatchSession", back_populates="notifications")


class FollowedTopic(Base):
    __tablename__ = "followed_topics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    match_type = Column(String(20), nullable=False)
    platform = Column(String(20), nullable=False, default="all")
    value = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="followed_topics")


class UserTrendWatchSession(Base):
    __tablename__ = "user_trend_watch_sessions"

    watch_session_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    session_key = Column(String(64), nullable=False, unique=True, index=True)
    baseline_run_id = Column(
        Integer,
        ForeignKey("trend_snapshot_runs.run_id", ondelete="SET NULL"),
    )
    last_seen_run_id = Column(
        Integer,
        ForeignKey("trend_snapshot_runs.run_id", ondelete="SET NULL"),
    )
    last_seen_category_run_id = Column(Integer)
    is_active = Column(Boolean, nullable=False, default=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime)

    user = relationship("User", back_populates="trend_watch_sessions")
    notifications = relationship(
        "Notification",
        back_populates="watch_session",
        cascade="all, delete-orphan",
    )


class TrendSnapshotRun(Base):
    __tablename__ = "trend_snapshot_runs"

    run_id = Column(Integer, primary_key=True)
    region = Column(String(10), nullable=False, default="TH", index=True)
    snapshot_kind = Column(String(32), nullable=False, default="global", index=True)
    status = Column(String(20), nullable=False, default="running", index=True)
    provider_status = Column(Text, nullable=False, default="{}")
    total_items = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)

    items = relationship(
        "TrendSnapshotItem",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class TrendCollectionSlot(Base):
    __tablename__ = "trend_collection_slots"
    __table_args__ = (
        UniqueConstraint("region", "scheduled_for", name="uq_trend_collection_region_slot"),
    )

    id = Column(Integer, primary_key=True)
    region = Column(String(10), nullable=False)
    scheduled_for = Column(DateTime, nullable=False, index=True)
    actor = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)
    result_json = Column(Text, nullable=False, default="{}")


class TrendHistoryBucket(Base):
    __tablename__ = "trend_history_buckets"
    __table_args__ = (
        UniqueConstraint("region", "platform", "ranking_scope", "bucket_at",
                         name="uq_trend_history_scope_hour"),
    )

    id = Column(Integer, primary_key=True)
    region = Column(String(10), nullable=False)
    platform = Column(String(20), nullable=False)
    ranking_scope = Column(String(64), nullable=False)
    bucket_at = Column(DateTime, nullable=False, index=True)
    first_at = Column(DateTime, nullable=False)
    last_at = Column(DateTime, nullable=False)
    first_sample = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    last_sample = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)


class TrendSnapshotItem(Base):
    __tablename__ = "trend_snapshot_items"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "platform",
            "ranking_scope",
            "trend_key",
            name="uq_trend_snapshot_item_run_scope_key",
        ),
        Index(
            "ix_trend_snapshot_platform_metric",
            "platform",
            "view_metric_version",
        ),
    )

    item_id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("trend_snapshot_runs.run_id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    ranking_scope = Column(String(64), nullable=False, default="global", index=True)
    category_id = Column(String(32), index=True)
    provider_rank = Column(Integer, nullable=False, default=0)
    trend_key = Column(String(40), nullable=False)
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, default="general")
    source_platform = Column(String(100), nullable=False)
    video_url = Column(String(1024))
    channel_title = Column(String(255))
    thumbnail_url = Column(String(1024))
    description = Column(Text)
    duration_seconds = Column(Integer)
    views = Column(Integer, nullable=False, default=0)
    likes = Column(Integer, nullable=False, default=0)
    comments = Column(Integer, nullable=False, default=0)
    views_available = Column(Boolean)
    likes_available = Column(Boolean)
    comments_available = Column(Boolean)
    search_volume = Column(Integer)
    trend_score = Column(Float, nullable=False, default=0.0)
    engagement_signal = Column(Float, nullable=False, default=0.0)
    view_metric_version = Column(
        String(64),
        nullable=False,
        default="unknown_v1",
    )
    published_at = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("TrendSnapshotRun", back_populates="items")


class ReferenceStatisticsConfig(Base):
    __tablename__ = "reference_statistics_configs"
    config_id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    interval_seconds = Column(Integer, nullable=False, default=3600)
    daily_request_budget = Column(Integer, nullable=False, default=100)
    blocked_until = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReferenceStatisticsRun(Base):
    __tablename__ = "reference_statistics_runs"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_reference_stats_idempotency_key",
        ),
    )
    run_id = Column(Integer, primary_key=True)
    status = Column(String(32), nullable=False, default="running")
    actor = Column(String(32), nullable=False)
    purpose = Column(String(64), nullable=False, default="reference_refresh")
    manifest_sha256 = Column(String(64))
    idempotency_key = Column(String(64))
    split_protection = Column(String(64))
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)
    requests_used = Column(Integer, nullable=False, default=0)
    candidate_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String(64))


class ReferenceVideoStatistic(Base):
    __tablename__ = "reference_video_statistics"
    __table_args__ = (
        UniqueConstraint("run_id", "dataset_id", name="uq_reference_stats_run_dataset"),
        Index("ix_reference_stats_dataset_time", "dataset_id", "observed_at"),
    )
    observation_id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("reference_statistics_runs.run_id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("dataset_contents.dataset_id"), nullable=False)
    video_id = Column(String(32), nullable=False)
    source_url = Column(String(1024), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False)
    error_code = Column(String(64))
    views = Column(BigInteger)
    likes = Column(BigInteger)
    comments = Column(BigInteger)
    view_metric_version = Column(String(64), nullable=False)


class TrendHistoryAttempt(Base):
    __tablename__ = "trend_history_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "platform", "ranking_scope", name="uq_trend_history_attempt_scope"),
        Index("ix_trend_attempt_scope_time", "region", "platform", "ranking_scope", "observed_at"),
    )
    id = Column(Integer, primary_key=True)
    # No FK: this audit record must survive raw snapshot pruning.
    run_id = Column(Integer, nullable=False)
    region = Column(String(10), nullable=False)
    platform = Column(String(20), nullable=False)
    ranking_scope = Column(String(64), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False)
    sample_count = Column(Integer)


class TrendTopic(Base):
    __tablename__ = "trend_topics"
    topic_id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TrendTopicVersion(Base):
    __tablename__ = "trend_topic_versions"
    version_id = Column(String(64), primary_key=True)
    extractor_version = Column(String(100), nullable=False)
    alias_version = Column(String(100), nullable=False)
    catalog_json = Column(AnalysisPayloadText, nullable=False)
    manifest_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TrendTopicDefinition(Base):
    __tablename__ = "trend_topic_definitions"
    version_id = Column(String(64), ForeignKey("trend_topic_versions.version_id"), primary_key=True)
    topic_id = Column(String(64), ForeignKey("trend_topics.topic_id"), primary_key=True)
    label = Column(String(255), nullable=False)
    kind = Column(String(64), nullable=False)


class TrendTopicAlias(Base):
    __tablename__ = "trend_topic_aliases"
    __table_args__ = (UniqueConstraint("version_id", "alias_hash", name="uq_topic_version_alias"),)
    id = Column(Integer, primary_key=True)
    version_id = Column(String(64), ForeignKey("trend_topic_versions.version_id"), nullable=False)
    topic_id = Column(String(64), ForeignKey("trend_topics.topic_id"), nullable=False)
    alias_hash = Column(String(64), nullable=False)
    text = Column(String(255), nullable=False)
    rules_json = Column(Text, nullable=False)


class TrendTopicConfig(Base):
    __tablename__ = "trend_topic_configs"
    config_id = Column(Integer, primary_key=True)
    active_version_id = Column(String(64), ForeignKey("trend_topic_versions.version_id"), nullable=False)


class TrendTopicObservation(Base):
    __tablename__ = "trend_topic_observations"
    __table_args__ = (
        UniqueConstraint("region", "platform", "ranking_scope", "source_run_id", name="uq_topic_source_scope"),
        Index("ix_topic_observation_scope_time", "region", "platform", "ranking_scope", "observed_at"),
    )
    observation_id = Column(Integer, primary_key=True)
    # Deliberately not a FK: evidence survives deletion of raw snapshots.
    source_run_id = Column(Integer, nullable=False)
    region = Column(String(10), nullable=False)
    platform = Column(String(20), nullable=False)
    ranking_scope = Column(String(64), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    source_kind = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    input_sha256 = Column(String(64), nullable=False)
    payload_json = Column(AnalysisPayloadText, nullable=False)


class TrendTopicJob(Base):
    __tablename__ = "trend_topic_jobs"
    __table_args__ = (
        UniqueConstraint("observation_id", "version_id", name="uq_topic_job_observation_version"),
        Index("ix_topic_job_queue", "status", "available_at"),
    )
    job_id = Column(Integer, primary_key=True)
    observation_id = Column(Integer, ForeignKey("trend_topic_observations.observation_id"), nullable=False)
    version_id = Column(String(64), ForeignKey("trend_topic_versions.version_id"), nullable=False)
    status = Column(String(24), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    lease_until = Column(DateTime)
    claim_token = Column(String(36))
    error_code = Column(String(80))
    result_json = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)


class TrendTopicEvidence(Base):
    __tablename__ = "trend_topic_evidence"
    __table_args__ = (UniqueConstraint("job_id", "video_id", name="uq_topic_job_video"),)
    evidence_id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("trend_topic_jobs.job_id"), nullable=False, index=True)
    video_id = Column(String(11).with_variant(VARCHAR(11, charset="ascii", collation="ascii_bin"), "mysql"), nullable=False)
    title = Column(Text, nullable=False)
    video_url = Column(String(1024), nullable=False)
    rank = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False)
    matches_json = Column(AnalysisPayloadText, nullable=False)


class TrendTopicCount(Base):
    __tablename__ = "trend_topic_counts"
    job_id = Column(Integer, ForeignKey("trend_topic_jobs.job_id"), primary_key=True)
    topic_id = Column(String(64), ForeignKey("trend_topics.topic_id"), primary_key=True)
    video_count = Column(Integer, nullable=False)
    eligible_videos = Column(Integer, nullable=False)
