from argparse import ArgumentParser
import functools as ft
from logging import getLogger
import os
from pathlib import Path
from typing import Any, Callable, Iterator, ParamSpec, Protocol, TypeVar
from warnings import warn

from pygit2 import Blob
from pygit2.enums import ObjectType

from mistral_tools.tool_register import ReturnableError
log = getLogger(__name__)

def get_api_key(key_file: Path|None = None, storage_dir: Path|None =None) -> str:
    """Get the Mistral API key"""
    if key_file is not None:
        return key_file.read_text().strip()
    if "MISTRAL_API_KEY" in os.environ:
        return os.environ["MISTRAL_API_KEY"]
    if storage_dir is not None:
        api_key_file = storage_dir / "api_key"
        if api_key_file.exists():
            return api_key_file.read_text().strip()
    raise ValueError("No api key found. "
                    "Please specify a key file or set the $MISTRAL_API_KEY "
                    "environment variable")

"""
Error management (not raised, but returned, for interaction with the llm)
-------------------------------------------------------------------------
"""


class FileNotFoundReturnableError(ReturnableError):
    """Returned by the tool calls if a file is not found in the repository"""

    def __init__(self, file: str):
        super().__init__("FileNotFound", f"File {file} not found in the repository")

class FileIsBinaryReturnableError(ReturnableError):
    """Returned by the tool calls if a file cannot be printed"""

    def __init__(self, file: str):
        super().__init__("FileIsBinary", f"File {file} is binary, cannot print")

class FileUnchangedError(ReturnableError):
    """Returned by the tool calls if a file has no diff because it did not change"""

    def __init__(self, file: str):
        super().__init__("FileUnchanged", f"File {file} was not changed in this commit")

class FileNewError(ReturnableError):
    """Returned by the tool calls if a file has no diff because it is new"""

    def __init__(self, file: str):
        super().__init__("NewFile", f"File {file} is new, cannot print diff")

class ParameterError(ReturnableError):
    """Returned by the tool calls if a parameter is incorrect"""

    def __init__(self, message: str):
        super().__init__("ParameterError", message)

"""
Git utils
---------

Miscellaneous utilities for working with git objects
"""

def walk_tree(tree, *, base_path=()) -> Iterator[tuple[tuple[str, ...], Blob]]:
    """Walk a tree recursively

    Yield all blobs in the tree, and their path relative to the root tree

    Args:
        tree (Tree): The tree to walk
        base_path (tuple, optional): The path to the current tree. Defaults to ().

    """
    for item in tree:
        match item.type:
            case ObjectType.BLOB:
                yield (*base_path, item.name), item
            case ObjectType.TREE:
                yield from walk_tree(item, base_path=(*base_path, item.name,))
            case _:
                warn(f"Unexpected object type {item.type_str} in tree")


"""
Miscellaneous utilities
"""

P = ParamSpec("P")
T = TypeVar("T")

def take_argument_annotation_from(this: Callable[P, Any]) \
        -> Callable[[Callable[..., T]], Callable[P, T]]:
    """Take the argument annotations from another function

    Decorator stating that the function it decorates 
    should have the same annotations as the function passed as argument.

    Inspired from https://stackoverflow.com/a/71262408/4948719

    """
    def decorator(real_function: Callable) -> Callable[P, T]:
        return_type ={"return": real_function.__annotations__["return"]} if "return" in real_function.__annotations__ else {}
        real_function.__annotations__ = {**this.__annotations__, **return_type}
        return real_function #type: ignore 
    return decorator

class CreateArgumentParserReturnSignature(Protocol): #noqa: D101
    def __call__(self, parser: ArgumentParser|None = None) -> ArgumentParser: ... #noqa: D102

@take_argument_annotation_from(ArgumentParser)
def create_argument_parser(**argparse_kwargs) \
        -> Callable[[Callable[[ArgumentParser], None]], 
                    CreateArgumentParserReturnSignature]:
    """Decorator that potentially creates an argument parser and passes it down

    This is a helper function that allows to have a function that either
    - populates an already existing parser 
        (if passed as argument, generally for use with subparsers)
    - creates an all new parser

    It decorates a function that takes a single argument, an ArgumentParser, 
    and populates it.

    usage:

    .. code-block:: python

        # @create_argument_parser
        # accepts all the arguments of ArgumentParser. 
        # They will be passed to the ArgumentParser constructor 
        # if a new parser is created
        @create_argument_parser(description="This is the description") 
        def my_argument_parser(parser: ArgumentParser):
            parser.add_argument("--my-arg", help="This is the help")

        specific_parser = my_argument_parser()
        # or
        parser = ArgumentParser()
        subparsers = parser.add_subparsers()
        my_argument_parser(subparsers.add_parser("my_subcommand"))

    .. note:: 

        The input function should only take a single argument parser, 
        and does not need to return anything. 
        The output function will return the parser.

    """

    def decorator(func: Callable[[ArgumentParser], None]) \
            -> CreateArgumentParserReturnSignature:
        @ft.wraps(func)
        def wrapper(parser: ArgumentParser|None = None) -> ArgumentParser:
            if parser is None:
                parser = ArgumentParser(**argparse_kwargs)
            func(parser)
            return parser
        return wrapper
    return decorator
