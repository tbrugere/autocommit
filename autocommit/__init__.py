# Notice that in this file, most imports are done inside functions. 
# This is to make the import / runs as snappy as possible
# in particular
# if this is imported as a library, there is no real need to have argparse imported
# if this is run from command line, the command should be as responsive as possible (and in particular if the arguments are invalid, we should not wait for imports before warning the user)
import logging
from logging import getLogger; log = getLogger(__name__)
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser

def main_argument_parser(parser: "ArgumentParser|None" = None):
    from argparse import ArgumentParser
    if parser is None:
        parser = ArgumentParser(description="Automatically generate commit messages from changes, and print it to stdout")

    parser.add_argument("repo", help="Path to the repository", type=str, default=".", nargs='?')
    parser.add_argument("--key-file" , help="File containing a Mistral api key", type=Path, default=None)

    return parser

def setup_argument_parser(parser: "ArgumentParser|None" = None):
    from argparse import ArgumentParser, BooleanOptionalAction

    if parser is None:
        parser = ArgumentParser(description="Activate autocommit on the current git repository")
    parser.add_argument("--isolation", action=BooleanOptionalAction, help="Run the program in isolation mode", default=True)
    parser.add_argument("repo", help="Path to the repository", type=str, default=".")

    return parser

def build_ragdb_argument_parser(parser: "ArgumentParser|None" = None):
    from argparse import ArgumentParser
    if parser is None:
        parser = ArgumentParser(description="Generate a RAG database from a set of files")
    parser.add_argument("--api-key", help="Mistral API key", type=str, required=False)
    parser.add_argument("repo", nargs="?", help="Path to the repository", type=str, default=".")


def argument_parser(parser: "ArgumentParser|None" = None):
    # the import call is deliberately inside the function
    # to avoid importing the argparse module if not running the package from cli
    from argparse import ArgumentParser

    if parser is None:
        parser = ArgumentParser(description="Automatically generate commit messages from changes")
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
    subparsers = parser.add_subparsers(title="action", help="whether to install or run", dest="action")

    run_parser = subparsers.add_parser("run")
    main_argument_parser(run_parser)

    setup_parser = subparsers.add_parser("setup")
    setup_argument_parser(setup_parser)

    build_ragdb_parser = subparsers.add_parser("build-ragdb")
    build_ragdb_argument_parser(build_ragdb_parser)

    return parser

def configure_logging(loglevel): 
    log.setLevel(loglevel)
    formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s', datefmt='%H:%M:%S')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    log.addHandler(handler)

    mistral_tools_logger = getLogger("mistral_tools")
    mistral_tools_logger.setLevel(loglevel)
    mistral_tools_logger.addHandler(handler)

    basic_rag_logger = getLogger("basic_rag")
    basic_rag_logger.setLevel(loglevel)
    basic_rag_logger.addHandler(handler)

def main():
    parser = argument_parser()
    args = parser.parse_args()
    # logging.basicConfig(level=args.loglevel)
    configure_logging(args.loglevel)

    match args.action:
        case "run":
            generate_commit_message(args.repo, args.key_file)
        case "setup":
            from autocommit.setup import run_setup
            run_setup(args.repo, args.isolation)
        case "build-ragdb":
            from autocommit.build_ragdb import build_ragdb
            build_ragdb(args.api_key, args.repo)
        case _:
            raise ValueError(f"Unknown action {args.action}")


def generate_commit_message(repo, key_file):
    from autocommit.mistral_model import main
    if key_file is not None: 
        key_file = Path(key_file)
        if not key_file.exists():
            raise FileNotFoundError(f"Key file {key_file} does not exist")
        if not key_file.is_file():
            raise ValueError(f"Key file {key_file} is not a file")
        api_key = key_file.read_text().strip()
    elif "MISTRAL_API_KEY" in os.environ:
        api_key = os.environ["MISTRAL_API_KEY"]
    else:
        raise ValueError("No api key found. Please specify a key file or set the MISTRAL_API_KEY environment variable")
    commit_message = main(api_key, repo)
    sys.stdout.write(str(commit_message))


    
