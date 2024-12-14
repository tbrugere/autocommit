from pathlib import Path

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

def add_commit_hook(repo: Path, key_file: Path):
    raise NotImplementedError("Not implemented yet")

def run_setup(repo, isolation: bool, key=None, worktree: Path|None =None):
    """Runs the setup for the repository"""

    if worktree is not None and not check_repo_bare(repo):
        raise ValueError("Cannot specify a worktree for a non-bare repository")

    if worktree is None:
        if check_repo_bare(repo):
            raise ValueError("Cannot run setup on a bare repository without specifying a worktree")
        worktree = repo
        repo = repo / ".git"

    add_storage_dir_to_exclude(repo)
    key_file = add_key_to_tree(key, worktree)
    add_commit_hook(repo, key_file)
