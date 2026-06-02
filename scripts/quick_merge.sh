#!/usr/bin/env bash
#
# quick_merge.sh — 「跳 PR 直推」工作流（僅限 CLAUDE.md §4 白名單的純文件／非邏輯改動）
#
# 用法：
#   ./scripts/quick_merge.sh "commit message"
#
# 行為：
#   1. 確認當前不在預設分支（main / master）且 working tree 乾淨
#   2. 切到預設分支並 pull 最新
#   3. git merge --squash <原分支> → commit + push origin <預設分支>
#   4. 刪除本地 + 遠端的原分支
#
set -euo pipefail

# ---- 參數檢查 -------------------------------------------------------------
if [ "$#" -ne 1 ] || [ -z "${1// }" ]; then
  echo "用法：$0 \"commit message\"" >&2
  exit 1
fi
MSG="$1"

# ---- 偵測預設分支（兼容 main / master）-----------------------------------
DEFAULT_BRANCH=""
if git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
  DEFAULT_BRANCH="$(git symbolic-ref --short refs/remotes/origin/HEAD | sed 's@^origin/@@')"
fi
if [ -z "$DEFAULT_BRANCH" ]; then
  if git show-ref --verify --quiet refs/remotes/origin/main; then
    DEFAULT_BRANCH="main"
  elif git show-ref --verify --quiet refs/remotes/origin/master; then
    DEFAULT_BRANCH="master"
  elif git show-ref --verify --quiet refs/heads/main; then
    DEFAULT_BRANCH="main"
  elif git show-ref --verify --quiet refs/heads/master; then
    DEFAULT_BRANCH="master"
  else
    echo "❌ 找不到預設分支（main / master）" >&2
    exit 1
  fi
fi

# ---- 前置守門 -------------------------------------------------------------
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ "$CURRENT_BRANCH" = "$DEFAULT_BRANCH" ]; then
  echo "❌ 你已在預設分支「$DEFAULT_BRANCH」上，無分支可合併。請在功能分支上執行。" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "❌ working tree 不乾淨，請先 commit 或 stash 後再執行。" >&2
  git status --short >&2
  exit 1
fi

FEATURE_BRANCH="$CURRENT_BRANCH"
echo "▶ 預設分支：$DEFAULT_BRANCH ｜ 原分支：$FEATURE_BRANCH"

# ---- 切換並更新預設分支 ---------------------------------------------------
git checkout "$DEFAULT_BRANCH"
git pull origin "$DEFAULT_BRANCH"

# ---- squash 合併 ----------------------------------------------------------
git merge --squash "$FEATURE_BRANCH"
git commit -m "$MSG"

# ---- 推送 -----------------------------------------------------------------
git push origin "$DEFAULT_BRANCH"

# ---- 清理分支 -------------------------------------------------------------
git branch -D "$FEATURE_BRANCH"
git push origin --delete "$FEATURE_BRANCH" || echo "⚠ 遠端分支 $FEATURE_BRANCH 不存在或已刪除，略過。"

echo "✅ 已 squash 合併 $FEATURE_BRANCH → $DEFAULT_BRANCH 並推送，分支已清理。"
