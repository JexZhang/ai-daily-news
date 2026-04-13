#!/usr/bin/env bash
# 将日报 JSON 提交到 main 分支。
# 本地分支为 main 时直接 push；在 Claude Code 云端定时任务中（运行于 claude/* 工作分支、
# 对 main 只读）会自动改走 PR + 自动合并，从而最终落到 main。
#
# 用法: commit-log.sh <json_path>

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <json_path>" >&2
  exit 2
fi

JSON_PATH="$1"
if [ ! -f "$JSON_PATH" ]; then
  echo "file not found: $JSON_PATH" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

BASENAME="$(basename "$JSON_PATH" .json)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COMMIT_MSG="日报记录 ${BASENAME}"

git add "$JSON_PATH"

if git diff --cached --quiet; then
  echo "no staged changes for $JSON_PATH, skip commit" >&2
  exit 0
fi

git commit -m "$COMMIT_MSG"

push_with_retry() {
  local remote_ref="$1"
  local delay=2
  local i
  for i in 1 2 3 4; do
    if git push "$@"; then
      return 0
    fi
    echo "push failed (attempt $i), retrying in ${delay}s..." >&2
    sleep "$delay"
    delay=$((delay * 2))
  done
  return 1
}

if [ "$BRANCH" = "main" ]; then
  push_with_retry origin main
  exit 0
fi

# 云端定时任务场景：当前在 claude/* 工作分支，对 main 只读。
# 推工作分支，然后用 gh 开 PR 并自动合并。
push_with_retry -u origin "$BRANCH"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not available; pushed branch $BRANCH but cannot auto-merge to main" >&2
  exit 1
fi

PR_URL="$(gh pr create \
  --base main \
  --head "$BRANCH" \
  --title "$COMMIT_MSG" \
  --body "自动生成：每日 AI 日报推送日志" 2>/dev/null || true)"

if [ -z "$PR_URL" ]; then
  # 可能 PR 已存在，尝试取当前分支的 PR
  PR_URL="$(gh pr view --json url -q .url 2>/dev/null || true)"
fi

if [ -z "$PR_URL" ]; then
  echo "failed to create or find PR for branch $BRANCH" >&2
  exit 1
fi

echo "PR: $PR_URL"
gh pr merge "$PR_URL" --squash --auto --delete-branch
