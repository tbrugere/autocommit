from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser

def argument_parser(parser: "ArgumentParser|None" = None):
    # the import call is deliberately inside the function
    # to avoid importing the argparse module if not running the package from cli
    from argparse import ArgumentParser, BooleanOptionalAction

    parser = ArgumentParser(description="Automatically generate commit messages from changes")
    parser.add_argument("--isolation", action=BooleanOptionalAction, help="Run the program in isolation mode", default=True)
    parser.add_argument("repo", help="Path to the repository", type=str)
    parser.add_argument()



    
