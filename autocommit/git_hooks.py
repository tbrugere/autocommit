"""
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

from autocommit.config import Config
log = getLogger(__name__)

def git_prepare_commit_msg(message_file: Path, commit_type: str, sha: str):
    """Hook for prepare-commit-msg

    This hook is called by git-commit when preparing the default commit message.
    """
    
    # 0. get the autocommit storage directory
    # cwd should be the repository root
    data_path = Path().cwd() / ".autocommit_storage_dir" 
    assert data_path.exists(), f"{data_path} does not exist"
    logfile = data_path / "autocommit.log"
    api_key_file = data_path / "api_key"
    config_file = data_path / "config.json"
    config = Config.from_json_file(config_file)

    # 1. check that the commit message is empty
    if message_file.exists():
        with message_file.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    log.info(f"Commit message file {message_file} is not empty. Exiting.")
                    exit(0)

    # 2. run autocommit
    autocommit_cmd = argv[0]
    log.info(f"Running autocommit with commit type {commit_type} and sha {sha}")
    if config.isolation: 
        raise NotImplementedError("Isolation is not implemented yet")

    eventually_debug = ["--debug"] if config.debug else []
    eventually_rag = ["--rag"] if config.enable_rag else []
    eventually_function_calls = ["--function-calls"] if config.enable_function_calls else []

    with open(message_file, "w") as out_file:
        process = subprocess.run((autocommit_cmd, 
                      *eventually_debug,
                      "--logfile", str(logfile), 
                      "run", 
                      "--key-file", str(api_key_file), 
                      *eventually_rag,
                      *eventually_function_calls,
                                  ), stdout=out_file)
        if process.returncode != 0:
            log.error(f"Autocommit failed with return code {process.returncode}, see {logfile} for details")
            out_file.write(f"# Autocommit failed with return code {process.returncode}, see {logfile} for details")
            exit(process.returncode)

    log.info(f"Autocommit ran successfully, see {logfile} for details")


def post_commit():
# updates the rag database with the new commit
    


