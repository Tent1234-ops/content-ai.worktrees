from __future__ import annotations

import hashlib


YOUTUBE_CC_DATASET_SOURCE = "youtube_cc"
YOUTUBE_PUBLIC_DATASET_SOURCE = "youtube_public_research"
SUPPORTED_YOUTUBE_DATASET_SOURCES = (
    YOUTUBE_PUBLIC_DATASET_SOURCE,
    YOUTUBE_CC_DATASET_SOURCE,
)
DEFAULT_YOUTUBE_CC_DATASET_VERSION = "youtube-cc-th-v1"
DEFAULT_YOUTUBE_PUBLIC_DATASET_VERSION = "youtube-public-research-th-v1"
YOUTUBE_CC_LABEL_SOURCE = "human_review"
YOUTUBE_CC_VERIFICATION_STATUS = "human_verified"
YOUTUBE_CC_LICENSE_NAME = "YouTube Creative Commons Attribution"
YOUTUBE_CC_LICENSE_URL = "https://support.google.com/youtube/answer/2797468"
YOUTUBE_STANDARD_LICENSE_NAME = "YouTube Standard License"
YOUTUBE_LICENSE_INFO_URL = "https://support.google.com/youtube/answer/2797468"
SUPPORTED_YOUTUBE_LICENSE_CODES = ("creativeCommon", "youtube")
YOUTUBE_CC_TRANSCRIPT_SOURCE = "youtube_public_caption"
NOTEBOOKLM_TRANSCRIPT_SOURCE = "notebooklm_source_transcript"
SUPPORTED_TRANSCRIPT_SOURCES = (
    YOUTUBE_CC_TRANSCRIPT_SOURCE,
    NOTEBOOKLM_TRANSCRIPT_SOURCE,
)
YOUTUBE_TRANSCRIPT_API_ACQUISITION = "youtube_transcript_api"
NOTEBOOKLM_TRANSCRIPT_ACQUISITION = "notebooklm_manual_source"
SUPPORTED_TRANSCRIPT_ACQUISITION_METHODS = (
    YOUTUBE_TRANSCRIPT_API_ACQUISITION,
    NOTEBOOKLM_TRANSCRIPT_ACQUISITION,
)
TRANSCRIPT_SCOPE_FIRST_WINDOW = "first_window"
TRANSCRIPT_SCOPE_FULL_VIDEO = "full_video"
SUPPORTED_TRANSCRIPT_SCOPES = (
    TRANSCRIPT_SCOPE_FIRST_WINDOW,
    TRANSCRIPT_SCOPE_FULL_VIDEO,
)

SUPPORTED_TRANSCRIPT_LANGUAGES = ("th", "en")
PRIMARY_CONTENT_LANGUAGE = "th"
DEFAULT_COLLECTION_LANGUAGES = (PRIMARY_CONTENT_LANGUAGE,)
SUPPORTED_CAPTION_TYPES = ("manual", "auto_generated", "unspecified")
ACCEPTED_TRANSCRIPT_QUALITIES = ("good", "acceptable")
PRODUCTION_SPLITS = ("train", "validation", "test")
TRANSCRIPT_WINDOW_SECONDS = 300
USER_UPLOAD_MAX_DURATION_SECONDS = 300
RECOMMENDATION_DURATION_MAX_SECONDS = 300
SPLIT_STRATEGY = "channel_sha256_bucket_v2_70_15_15"
SPLIT_HASH_SALT = "content-ai-split-v2:1974"


def youtube_license_metadata(license_code: str) -> tuple[str, str]:
    """Return the recorded YouTube license label without treating it as reuse permission."""
    normalized = str(license_code or "").strip()
    if normalized == "creativeCommon":
        return YOUTUBE_CC_LICENSE_NAME, YOUTUBE_CC_LICENSE_URL
    if normalized == "youtube":
        return YOUTUBE_STANDARD_LICENSE_NAME, YOUTUBE_LICENSE_INFO_URL
    return "Unknown YouTube License", YOUTUBE_LICENSE_INFO_URL


def channel_dataset_split(channel_id: str) -> tuple[str, str]:
    """Return a stable split and anonymized group key for one YouTube channel."""
    normalized_channel_id = str(channel_id or "").strip()
    if not normalized_channel_id:
        raise ValueError("channel_id is required for channel-grouped dataset splits")
    creator_group_key = hashlib.sha256(normalized_channel_id.encode("utf-8")).hexdigest()
    # The versioned salt freezes a balanced pilot split without exposing channel IDs.
    # Every video from one channel still lands in exactly one split.
    split_digest = hashlib.sha256(
        f"{SPLIT_HASH_SALT}:{normalized_channel_id}".encode("utf-8")
    ).hexdigest()
    bucket = int(split_digest[:8], 16) % 100
    if bucket < 70:
        split = "train"
    elif bucket < 85:
        split = "validation"
    else:
        split = "test"
    return split, creator_group_key
