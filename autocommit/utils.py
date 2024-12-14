from logging import getLogger; log = getLogger(__name__)
from warnings import warn

from pygit2.enums import ObjectType

from mistral_tools.tool_register import ReturnableError


"""
Error management (not raised, but returned, for interaction with the llm)
-------------------------------------------------------------------------
"""


class FileNotFoundReturnableError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("FileNotFound", f"File {file} not found in the repository")

class FileIsBinaryReturnableError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("FileIsBinary", f"File {file} is binary, cannot print")

class FileUnchangedError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("FileUnchanged", f"File {file} was not changed in this commit")

class FileNewError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("NewFile", f"File {file} is new, cannot print diff")

class ParameterError(ReturnableError):
    def __init__(self, message: str):
        super().__init__("ParameterError", message)

"""
Git utils
---------

Miscellaneous utilities for working with git objects
"""

def walk_tree(tree, *, base_path=()):
    """Walk a tree recursively and yield all blobs in the tree,
    and their path relative to the root tree

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



