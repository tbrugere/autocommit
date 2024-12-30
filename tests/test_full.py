"""Test that autocommit works on a test repo"""

import subprocess
from autocommit.config import AutocommitDir, Config

from utils import chdir, commit
import os


def test_autocommit(test_repository, api_key):
    repo, repo_path = test_repository

    with chdir(repo_path):
        _test_autocommit_inner(repo, repo_path, api_key)
    
def _test_autocommit_inner(repo, repo_path, api_key):
    api_key_env = dict(MISTRAL_API_KEY=api_key, **os.environ)
    # 1. install autocommit to the repo
    process_1 = subprocess.run(("python", "-m", "autocommit", "setup"), 
                               env=api_key_env, 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process_1.returncode != 0:
        raise RuntimeError("Failed to install autocommit, \n"
                           f"stdout: {process_1.stdout}\nstderr: {process_1.stderr}")
    # 1.1 checks that the autocommit directory was created
    dir = AutocommitDir.from_repo(repo_path)
    # 1.2 checks that the rag database is accessible
    # TODO

    # 2. try running autocommit (there are unstaged changes in the repo)
    process_2 = subprocess.run(("python", "-m", "autocommit", "run"), env=api_key_env)
    if process_2.returncode != 0:
        raise RuntimeError("Failed to run autocommit, \n"
                           f"stdout: {process_2.stdout}\nstderr: {process_2.stderr}")












