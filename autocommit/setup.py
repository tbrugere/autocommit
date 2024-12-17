from pathlib import Path

from autocommit.config import Config

autocommit_storage_dir = Path(".autocommit_storage_dir")

def add_storage_dir_to_exclude(gitdir: Path):
    """adds .autocommit_storage_dir/ to the .git/info/exclude file

    unless it is already there. This serves to avoid tracking the storage directory,
    which contains the api key.
    """
    pattern = f"{autocommit_storage_dir}/"

    exclude_path = gitdir / "info" / "exclude"

    pattern_already_there = pattern in [line.strip() for line in exclude_path.read_text().splitlines()]
    if pattern_already_there:
        return

    with exclude_path.open("a") as f:
        f.write(pattern + "\n")


def add_key_to_tree(key, worktree):
    """Adds the api key to the worktree"""
    storage_dir = worktree / autocommit_storage_dir
    storage_dir.mkdir(exist_ok=True)
    storage_dir.chmod(0o700)
    key_file = storage_dir / "api_key"
    key_file.write_text(key)
    key_file.chmod(0o600)
    return key_file

def check_repo_bare(repo: Path):
    """Checks if the repo is bare"""
    return not (repo / ".git").is_dir()

def add_commit_hook(repo: Path, *, hook_name="prepare-commit-msg", hook_content):
    """Adds the commit hook to the repository"""
    hook_path = repo / "hooks" / "prepare-commit-msg"


    if not hook_path.exists():
        hook_path.write_text(f"#!/bin/sh\n{autocommit_line}\n")
        hook_path.chmod(0o755)
    else:
        lines = hook_path.read_text().splitlines()
        if hook_content in lines:
            return
        with hook_path.open("a") as f:
            f.write("\n" + hook_content + "\n")


def run_setup(repo, isolation: bool, key=None, worktree: Path|None =None, 
              enable_rag: bool = True, enable_function_calls: bool = False):
    """Runs the setup for the repository"""
    config = Config(
        enable_rag=enable_rag,
        isolation=isolation,
        enable_function_calls=enable_function_calls,
        debug=False, # must be manually enabled by editing the config file
    )

    if isolation:
        raise NotImplementedError("Isolation is not implemented yet")

    if worktree is not None and not check_repo_bare(repo):
        raise ValueError("Cannot specify a worktree for a non-bare repository")

    if worktree is None:
        if check_repo_bare(repo):
            raise ValueError("Cannot run setup on a bare repository"
                             " without specifying a worktree")
        worktree = repo
        repo = repo / ".git"
    assert worktree is not None

    config.to_json_file(worktree / autocommit_storage_dir / "config.json")

    add_storage_dir_to_exclude(repo)
    key_file = add_key_to_tree(key, worktree)

    # git hooks
    autocommit_line = 'exec autocommit git_prepare_commit_msg \"$@\"'
    add_commit_hook(repo, hook_name="prepare-commit-msg",
                    hook_content=autocommit_line)

    # build ragdb
    if enable_rag:
        from autocommit.build_ragdb import build_ragdb
        add_commit_hook(repo, hook_name="post-commit", hook_content="exec autocommit post_commit")
        build_ragdb(key, str(worktree), update=False)


