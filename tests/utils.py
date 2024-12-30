from contextlib import contextmanager
import os
from pathlib import Path
import pygit2
from textwrap import dedent

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

file1_unstaged_content = dedent("""\
    THIS SHOULD NEVER BE READ""")

file2_content = dedent("""\
    THIS FILE IS UNTRACKED, IT SHOULD NEVER BE READ""")

file3_staged_content = dedent("""\
    this is the staged content
    more staged content""")

@contextmanager
def chdir(path):
    old_dir = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old_dir)
