#!/usr/bin/env bash
set -e

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ACCESS_TOKEN="${ACCESS_TOKEN:-}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
UPLOAD_FILE="${UPLOAD_FILE:-}"
CONTENT_ID="${CONTENT_ID:-1}"

echo "Base URL: ${BASE_URL}"

echo "\n1) Register user"
curl -s -X POST "${BASE_URL}/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"creator_demo\", \"email\": \"creator_demo@example.com\", \"password\": \"password123\"}"

printf "\n---\n"

echo "2) Login user and capture access token"
ACCESS_TOKEN=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"creator_demo@example.com\", \"password\": \"password123\"}" | python -c "import sys, json; print(json.load(sys.stdin).get(\"access_token\", \"\"))")

if [ -z "${ACCESS_TOKEN}" ]; then
  echo "Failed to retrieve access token"
  exit 1
fi

echo "ACCESS_TOKEN=${ACCESS_TOKEN}"
printf "\n---\n"

echo "3) Get profile"
curl -s -X GET "${BASE_URL}/auth/me" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/json"
printf "\n---\n"

echo "4) Dashboard overview"
curl -s -X GET "${BASE_URL}/dashboard/overview?region=TH&trend_mode=live&trend_limit=5" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/json"
printf "\n---\n"

echo "5) Dashboard emerging topics"
curl -s -X GET "${BASE_URL}/dashboard/emerging-topics?region=TH&trend_mode=live&trend_limit=5" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/json"
printf "\n---\n"

echo "6) Analyze and save upload"
if [ -z "${UPLOAD_FILE}" ]; then
  echo "UPLOAD_FILE is not set. Set UPLOAD_FILE to a valid video path. Skipping upload test."
else
  curl -s -X POST "${BASE_URL}/analyze/save" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -F "file=@${UPLOAD_FILE}" \
    -H "Accept: application/json"
  printf "\n---\n"
fi

echo "7) Get user content history (My Ideas)"
curl -s -X GET "${BASE_URL}/contents/my?limit=10&offset=0" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Accept: application/json"
printf "\n---\n"

echo "8) Get saved content detail"
curl -s -X GET "${BASE_URL}/contents/${CONTENT_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Accept: application/json"
printf "\n---\n"

echo "9) Recommendation from saved content"
curl -s -X GET "${BASE_URL}/recommendations/from-content/${CONTENT_ID}?source=youtube&profile_limit=150" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Accept: application/json"
printf "\n---\n"

echo "10) Register admin"
curl -s -X POST "${BASE_URL}/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"admin_demo\", \"email\": \"admin_demo@example.com\", \"password\": \"password123\", \"role\": \"admin\", \"admin_invite_code\": \"MyAdminInvite2026!\"}"
printf "\n---\n"

echo "11) Login admin and capture admin token"
ADMIN_TOKEN=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"admin_demo@example.com\", \"password\": \"password123\"}" | python -c "import sys, json; print(json.load(sys.stdin).get(\"access_token\", \"\"))")

if [ -z "${ADMIN_TOKEN}" ]; then
  echo "Failed to retrieve admin token"
  exit 1
fi

echo "ADMIN_TOKEN=${ADMIN_TOKEN}"
printf "\n---\n"

echo "12) Read admin settings"
curl -s -X GET "${BASE_URL}/admin/settings" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Accept: application/json"
printf "\n---\n"

echo "13) Update admin settings"
curl -s -X PUT "${BASE_URL}/admin/settings" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"max_keywords_display\": 15, \"hook_analysis_duration\": 90, \"analysis_time_range_days\": 120, \"youtube_region\": \"TH\", \"google_region\": \"TH\", \"tiktok_region\": \"TH\", \"enable_youtube_trending\": true, \"enable_google_trends\": true, \"enable_tiktok_trending\": true, \"auto_scan_interval_hours\": 6}"
printf "\n---\n"

echo "14) Admin reports overview"
curl -s -X GET "${BASE_URL}/admin/reports/overview" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Accept: application/json"
printf "\n---\n"