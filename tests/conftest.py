import os
from pathlib import Path
import pytest

import pygit2
from utils import (commit, 
                   file1_commited_content, file1_staged_content,
                   file1_unstaged_content, file2_content, file3_staged_content)
from textwrap import dedent

@pytest.fixture
def api_key():
    if os.environ.get("MISTRAL_API_KEY"):
        return os.environ["MISTRAL_API_KEY"]
    api_key_path = Path(".mistral-api-key")
    if api_key_path.exists():
        return api_key_path.read_text().strip()
    raise ValueError("No api key found, please fill the MISTRAL_API_KEY "
                     " environment variable or create a .mistral-api-key file")



@pytest.fixture
def test_repository(tmp_path: Path):
    base_repo_url = "https://github.com/octocat/Hello-World"
    repo_path = tmp_path / "repo1"
    repo = pygit2.clone_repository(base_repo_url, str(repo_path))

    ############ file1.txt
    # in a sub-directory
    # has commited content
    # has staged content
    # has unstaged content
    (repo_path / "directory").mkdir()
    file1 = repo_path / "directory" / "file1.txt"

    ############ file2.txt
    # is completely untracked
    file2 = repo_path / "file2.txt"

    ############ file3.txt
    # is a new file, only in the staging area
    file3 = repo_path / "file3.txt"

    ############ handle the commited
    file1.write_text(file1_commited_content)

    repo.index.add("directory/file1.txt")
    commit(repo, "Add file1.txt")

    ############ handle the staged
    file1.write_text(file1_staged_content)
    file3.write_text(file3_staged_content)
    repo.index.add("directory/file1.txt")
    repo.index.add("file3.txt")
    repo.index.write()

    ############ handle the unstaged
    file1.write_text(file1_unstaged_content)
    file2.write_text(file2_content)
    
    return repo, repo_path
