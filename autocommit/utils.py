"""Miscellaneous utilities for autocommit"""
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


"""
Algorithms
----------
"""

def compute_truncation(lengths, max_total_length):
    r"""Figure out the truncation of the lengths to fit in max_total_length

    Given a list of lengths ``[l_1...l_n]``, and a maximum total length ``L``,
    figure out the maximum truncation index ``t``, such that the sum of the lengths
    truncated at ``t`` is less than ``L``, ie

    .. math::

        \sum_{i=1}^n min(l_i, t) < L

    Args:
        lengths (list[int]): The list of lengths
        max_total_length (int): The maximum total length
    """
    import numpy as np

    # we add a dummy length of 0 
    # which will make sure that there is one length smaller than the cutoff
    lengths = np.array((*lengths, 0.) )

    n, = lengths.shape
    total_len = lengths.sum()
    if total_len <= max_total_length:
        return None

    lengths.sort()

    # the total length function is piecewise affine, with cuts at the lengths
    # we first compte the total length at each value of li
    # which is l0 + ... + li + li * (n - i + 1)
    total_lengths: np.ndarray= (np.cumsum(lengths) 
                           + lengths * np.arange(n-1, -1, -1))

    first_working_index: int = np.searchsorted(total_lengths, 
                                               max_total_length, 
                                               side="left")

    # must be >0 because of the dummy length
    # must be <n because otherwise no need to cut
    assert  0 < first_working_index < n

    # we need to find the exact value of the cutoff
    total_length_li = total_lengths[first_working_index]
    total_length_li_1 = total_lengths[first_working_index - 1]
    li = lengths[first_working_index]
    li_1 = lengths[first_working_index - 1]

    inverse_slope = (li - li_1) / (total_length_li - total_length_li_1)

    t = li_1 + (max_total_length - total_length_li_1) * inverse_slope
    t = int(np.floor(t))
    return t

    

