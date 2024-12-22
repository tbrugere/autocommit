"""Git Hooks

This module contains the git hooks that are called by git
when certain actions are performed.

They actually spawn a subprocess that runs the autocommit command. 
The reason I designed it this way is to allow for the command to 
later be run with isolation (with bubblewrap)
"""
from pathlib import Path
import subprocess
from sys import exit, argv
from logging import getLogger

from autocommit.config import AutocommitDir
log = getLogger(__name__)

def git_prepare_commit_msg(message_file: Path, commit_type: str, sha: str):
    """Hook for prepare-commit-msg

    This hook is called by git-commit when preparing the default commit message.
    """
    # 0. get the autocommit storage directory
    # cwd should be the repository root
    dir = AutocommitDir.from_repo(Path.cwd())

    # 1. check that the commit message is empty
    if message_file.exists():
        with message_file.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    log.info(f"Commit message file {message_file} is not empty. "
                             "Exiting.")
                    exit(0)

    # 2. run autocommit
    autocommit_cmd = argv[0]
    log.info(f"Running autocommit with commit type {commit_type} and sha {sha}")
    if dir.config.isolation: 
        raise NotImplementedError("Isolation is not implemented yet")

    eventually_debug = ["--debug"] if dir.config.debug else []
    eventually_rag = ["--rag"] if dir.config.enable_rag else []
    eventually_function_calls = ["--function-calls"] \
                                if dir.config.enable_function_calls else []

    with open(message_file, "w") as out_file:
        process = subprocess.run((autocommit_cmd, 
                      *eventually_debug,
                      "--logfile", str(dir.logfile), 
                      "run", 
                      "--key-file", str(dir.api_key_file), 
                      *eventually_rag,
                      *eventually_function_calls,
                                  ), stdout=out_file)
        if process.returncode != 0:
            log.error(f"Autocommit failed with return code {process.returncode}, "
                      "see {logfile} for details")
            out_file.write(f"# Autocommit failed with return code {process.returncode}"
                           f", see {dir.logfile} for details")
            exit(0)

    log.info(f"Autocommit ran successfully, see {dir.logfile} for details")


def git_post_commit():
    """Update the RAG database after a commit"""
    # 0. get the autocommit storage directory
    # cwd should be the repository root
    dir = AutocommitDir.from_repo(Path.cwd())

    if dir.config.isolation: 
        raise NotImplementedError("Isolation is not implemented yet")

    # 1. run autocommit
    autocommit_cmd = argv[0]
    process = subprocess.Popen((autocommit_cmd,
                    "--logfile", str(dir.logfile), 
                    "build-ragdb", 
                    "--key-file", str(dir.api_key_file), 
                    "--update",
                ), 
                start_new_session=True) 
    # runs in the background to not block the commit
    # will not get killed even if the terminal is closed
    del process



