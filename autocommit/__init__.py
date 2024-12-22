"""Main module for autocommit

The toplevel module for autocommit mainly contains the command line interface.
"""
# Notice that in this file, most imports are done inside functions. 
# This is to make the import / runs as snappy as possible
# in particular
# if this is imported as a library, there is no real need to have argparse imported
# if this is run from command line, the command should be as responsive as possible.
# In particular, if the arguments are invalid, we should not 
# wait for imports before warning the user
import logging
from logging import getLogger
from pathlib import Path
import sys
from argparse import ArgumentParser, BooleanOptionalAction

from autocommit.utils import get_api_key, create_argument_parser
log = getLogger(__name__)

...
"""
Argument parsers for the command line
-------------------------------------
"""

@create_argument_parser(description="Automatically generate commit messages"
                        " from changes, and print it to stdout")
def run_argument_parser(parser: ArgumentParser): # noqa: D103
    """Argument parser for the ``autocommit run`` command"""
    parser.add_argument("repo", help="Path to the repository", type=str, default=".", 
                        nargs='?')
    parser.add_argument("--key-file" , help="File containing a Mistral api key", 
                        type=Path, default=None)
    parser.add_argument("--rag", action=BooleanOptionalAction,
                        help="Enable the RAG database", default=True)
    parser.add_argument("--function-calls", action=BooleanOptionalAction,
                        help="Enable function calls", default=False)

@create_argument_parser(description="Setup autocommit in the current repository")
def setup_argument_parser(parser: ArgumentParser): # noqa: D103
    """Argument parser for the ``autocommit setup`` command"""
    parser.add_argument("--isolation", action=BooleanOptionalAction,
                        help="Run the program in isolation mode", default=False)
    parser.add_argument("repo", help="Path to the repository", 
                        type=Path, default=".", nargs="?")
    parser.add_argument("--rag", action=BooleanOptionalAction, 
                        help="Enable the RAG database", default=True)
    parser.add_argument("--function-calls", action=BooleanOptionalAction,
                        help="Enable function calls", default=False)
    parser.add_argument("--key-file", help="Mistral API key "
                    " (can also be set with the MISTRAL_API_KEY environment variable)"
                    " (WILL BE WRITTEN TO THE .autocommit_storage_dir/api_key FILE) "
                    , 
                    type=Path, default=None)

@create_argument_parser(description="Clenaup autocommit setup")
def cleanup_argument_parser(parser: ArgumentParser):
    """Argument parser for the ``autocommit cleanup`` command"""
    parser.add_argument("repo", help="Path to the repository", 
                        type=Path, default=".", nargs="?")

@create_argument_parser(description="Build or update the RAG database "
                        "from the repository")
def build_ragdb_argument_parser(parser: ArgumentParser): # noqa: D103
    """Argument parser for the ``autocommit build-ragdb`` command"""
    parser.add_argument("--key-file", help="Mistral API key", type=Path, required=False)
    parser.add_argument("repo", nargs="?", help="Path to the repository", 
                        type=str, default=".")
    parser.add_argument("--update", help="Update the RAG database",
                        action=BooleanOptionalAction, default=True)

@create_argument_parser(description="handle the git prepare-commit-msg hook")
def git_prepare_commit_msg_argument_parser(parser: ArgumentParser): # noqa: D103
    """Argument parser for the ``autocommit git_prepare_commit_msg`` command"""
    parser.add_argument("message_file", type=Path)
    parser.add_argument("commit_type", type=str, nargs="?")
    parser.add_argument("sha", type=str, nargs="?")

@create_argument_parser(description="handle the git post-commit hook")
def git_post_commit_argument_parser(parser: ArgumentParser): # noqa: D103
    """Argument parser for the ``autocommit git_post_commit`` command"""
    del parser # takes no arguments

@create_argument_parser(
        description="Automatically generate commit messages from changes")
def argument_parser(parser: ArgumentParser): # noqa: D103
    """The main argument parser for the autocommit command line interface"""
    ############### logging (mostly stolen from https://stackoverflow.com/a/20663028/4948719)
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements",
        action="store_const", dest="loglevel", const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        '-v', '--verbose',
        help="Be verbose",
        action="store_const", dest="loglevel", const=logging.INFO,
    )
    parser.add_argument(
        '--logfile',
        type=Path, help="Log file to write to (implies --verbose)",
        default=None
    )
    subparsers = parser.add_subparsers(title="action", dest="action")

    run_parser = subparsers.add_parser("run")
    run_argument_parser(run_parser)

    setup_parser = subparsers.add_parser("setup")
    setup_argument_parser(setup_parser)

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_argument_parser(cleanup_parser)

    build_ragdb_parser = subparsers.add_parser("build-ragdb")
    build_ragdb_argument_parser(build_ragdb_parser)

    git_prepare_commit_msg_parser = subparsers.add_parser("git_prepare_commit_msg")
    git_prepare_commit_msg_argument_parser(git_prepare_commit_msg_parser)

    git_post_commit_parser = subparsers.add_parser("git_post_commit")
    git_post_commit_argument_parser(git_post_commit_parser)

def configure_logging(loglevel, logfile=None): 
    """Configures the logging for the program

    Enables logging (either to stderr or to a file) for the following packages:

    - autocommit
    - basic_rag
    - mistral_tools

    with the specified log level

    Args:
        loglevel (int): The log level
        logfile (Path, optional): The file to log to. Defaults to None.
    """
    if logfile is not None:
        logfile = Path(logfile)
        logfile.parent.mkdir(exist_ok=True, parents=True)
        if loglevel > logging.INFO:
            loglevel = logging.INFO
    log.setLevel(loglevel)
    formatter = logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s:%(message)s', 
            datefmt='%H:%M:%S')
    if logfile is not None:
        handler = logging.FileHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    log.addHandler(handler)

    mistral_tools_logger = getLogger("mistral_tools")
    mistral_tools_logger.setLevel(loglevel)
    mistral_tools_logger.addHandler(handler)

    basic_rag_logger = getLogger("basic_rag")
    basic_rag_logger.setLevel(loglevel)
    basic_rag_logger.addHandler(handler)

"""
Running autocommit
------------------
"""

def main():
    """Chooses the action to take based on the command line arguments"""
    parser = argument_parser()
    args = parser.parse_args()
    # logging.basicConfig(level=args.loglevel)
    configure_logging(args.loglevel, logfile=args.logfile)

    match args.action:
        case "run":
            generate_commit_message(args.repo, args.key_file, 
                                    use_rag=args.rag, 
                                    use_tools=args.function_calls)
        case "setup":
            from autocommit.setup import run_setup
            run_setup(args.repo, args.isolation, key=args.key_file, 
                      enable_rag=args.rag, enable_function_calls=args.function_calls)
        case "build-ragdb":
            from autocommit.build_ragdb import build_ragdb
            api_key = get_api_key(args.key_file)
            build_ragdb(api_key, args.repo, update=args.update)
        case "git_prepare_commit_msg":
            from autocommit.git_hooks import git_prepare_commit_msg
            git_prepare_commit_msg(args.message_file, args.commit_type, args.sha)
        case "git_post_commit":
            from autocommit.git_hooks import git_post_commit
            git_post_commit()
        case "cleanup":
            from autocommit.setup import run_cleanup
            run_cleanup(args.repo)
        case _:
            raise ValueError(f"Unknown action {args.action}")


def generate_commit_message(repo, key_file, use_rag=True, use_tools=False):
    """The main function for autocommit,

    called when runninng ``autocommit run`` from the command line.

    This is a wrapper around :func:`autocommit.mistral_model.main` 
    that loads the api key, and prints the commit message to stdout.
    """
    from autocommit.mistral_model import main
    api_key = get_api_key(key_file)
    commit_message = main(api_key, repo, use_rag=use_rag, use_tools=use_tools)
    sys.stdout.write(str(commit_message))


    
