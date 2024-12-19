from pathlib import Path
import sys
from textwrap import dedent

import pygit2
import pytest

from autocommit.commands import print_file, ls_files, diff_file
from autocommit.utils import FileNotFoundReturnableError, FileIsBinaryReturnableError, FileUnchangedError, FileNewError


def commit(repo, message):
    repo.index.write()
    ref = repo.head.name
    author = pygit2.Signature("Test Author", "alice@example.com")
    committer = pygit2.Signature("Test Committer", "bob@example.com")
    tree = repo.index.write_tree()
    return repo.create_commit(ref, author, committer, message, tree, [repo.head.target])

file1_commited_content = dedent("""\
    Hello World
    This is a test file
    It has lines already in it

    And some more lines
    And even more lines
    Lines are good
    """)

file1_staged_content =f"""\
Added stuff
{file1_commited_content}
More stuff
"""

file1_unstaged_content = dedent(f"""\
    THIS SHOULD NEVER BE READ""")

file2_content = dedent("""\
    THIS FILE IS UNTRACKED, IT SHOULD NEVER BE READ""")

file3_staged_content = dedent(f"""\
    this is the staged content
    more staged content""")

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
    
    return repo


def test_cat_staged_untracked_and_commited(test_repository):
    repo = test_repository
    assert print_file("directory/file1.txt", staged=True, repository=repo) == file1_staged_content
    assert print_file("directory/file1.txt", staged=False, repository=repo) == file1_commited_content

def test_cat_untracked(test_repository):
    repo = test_repository
    assert isinstance(print_file("file2.txt", staged=True, repository=repo), FileNotFoundReturnableError)

def test_cat_newfile(test_repository):
    repo = test_repository
    assert isinstance(print_file("file3.txt", staged=False, repository=repo), FileNotFoundReturnableError)
    assert print_file("file3.txt", staged=True, repository=repo) == file3_staged_content


def test_ls_all(test_repository):
    repo = test_repository
    all_files = ls_files(only_changed=False, indicate_changes=False, repository=repo)
    files_set = set(all_files.splitlines())
    assert files_set == {"README", "directory/file1.txt", "file3.txt"} #file2.txt should not be there as it is untracked

def test_ls_changed(test_repository):
    repo = test_repository
    all_files = ls_files(only_changed=True, indicate_changes=False, repository=repo)
    files_set = set(all_files.splitlines())
    # README (the file originally in the repo) should not be there as it was not changed
    assert files_set == {"directory/file1.txt", "file3.txt"}

def test_ls_show_changes(test_repository):
    repo = test_repository
    all_files = ls_files(only_changed=False, indicate_changes=True, repository=repo)
    files_set = set(all_files.splitlines())
    assert files_set == {"README", "directory/file1.txt (MODIFIED)", "file3.txt (NEW)"} #file2.txt should not be there as it is untracked

def test_diff_file(test_repository):
    repo = test_repository
    diff = diff_file("directory/file1.txt", context=2, repository=repo)
    assert isinstance(diff, str)
    diff_lines = diff.splitlines()
    assert diff_lines[0] == "diff --git a/directory/file1.txt b/directory/file1.txt"
    assert diff_lines[2] == "--- a/directory/file1.txt"
    assert diff_lines[3] == "+++ b/directory/file1.txt"

    rest = "\n".join(diff_lines[4:])

    assert  rest == dedent(f"""\
        @@ -1,3 +1,4 @@
        +Added stuff
         Hello World
         This is a test file
         It has lines already in it
        @@ -5,3 +6,5 @@ It has lines already in it
         And some more lines
         And even more lines
         Lines are good
        +
        +More stuff""")



