"""
R-C-002 自动存档脚本 — 由 Stop Hook 触发。

会话结束前自动执行：
1. 更新 progress.md 时间戳
2. git add -A && git commit（如果当前目录是 git 仓库）
"""
import os
import sys
from datetime import datetime, timezone


def get_repo_root():
    """返回当前脚本所在的仓库根目录（harness-engineer/ 或工作目录）。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 脚本在 harness-engineer/persistence/，往上两级到 harness-engineer/
    return os.path.normpath(os.path.join(script_dir, ".."))


def update_progress(repo_root: str):
    """更新 progress.md 的最后更新时间。"""
    progress_path = os.path.join(repo_root, "progress.md")
    if not os.path.exists(progress_path):
        print(f"[auto_save] progress.md not found at {progress_path}, skip")
        return False

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    date_line = f"> 最后更新: {timestamp}"

    with open(progress_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 替换第二行的最后更新时间
    if len(lines) >= 2 and "最后更新" in lines[1]:
        lines[1] = date_line + "\n"
    else:
        # 如果格式不对，在标题后插入
        lines.insert(1, date_line + "\n")

    with open(progress_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"[auto_save] progress.md updated: {timestamp}")
    return True


def git_commit(repo_root: str):
    """尝试 git commit。非 git 仓库则静默跳过。"""
    import subprocess

    git_dir = os.path.join(repo_root, ".git")
    if not os.path.isdir(git_dir):
        print("[auto_save] Not a git repo, skip commit")
        return False

    try:
        subprocess.run(
            ["git", "-C", repo_root, "add", "-A"],
            check=True, capture_output=True,
        )
        result = subprocess.run(
            ["git", "-C", repo_root, "commit", "-m", f"auto-save: R-C-002 checkpoint"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("[auto_save] git commit successful")
            return True
        elif "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            print("[auto_save] Nothing to commit, skip")
            return False
        else:
            print(f"[auto_save] git commit failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"[auto_save] git error: {e}")
        return False


def main():
    repo_root = get_repo_root()
    print(f"[auto_save] Running R-C-002 checkpoint at {repo_root}")

    progress_ok = update_progress(repo_root)
    git_ok = git_commit(repo_root)

    if progress_ok or git_ok:
        print("[auto_save] R-C-002 checkpoint complete")
    else:
        print("[auto_save] Nothing to do")

    return 0


if __name__ == "__main__":
    sys.exit(main())
