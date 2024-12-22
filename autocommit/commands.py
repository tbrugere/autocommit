from io import StringIO, TextIOWrapper
from textwrap import dedent

from pygit2 import Blob, Commit, Patch, Oid, Tree
from pygit2.blob import BlobIO
from pygit2.enums import FileStatus, ObjectType
from pygit2.index import Index
from pygit2.repository import Repository

from .utils import ( FileIsBinaryReturnableError, FileNotFoundReturnableError, 
                    FileUnchangedError, FileNewError, walk_tree, compute_truncation)

from mistral_tools.tool_register import CommandRegister

commands = CommandRegister(bindable_parameters=("repository",))


@commands.register(
        description="Print the contents of the file", 
        parameter_descriptions={
           "file": "The file to print",
           "start_line": "print from this line",
           "num_lines": "the maximum number of lines to print (set to 0 to print all)",
           "staged": "whether to print the new version of the file is available"
})
def print_file(file: str, start_line: int=0, num_lines: int=200, staged:bool=True, *,
               repository: Repository):
    """Print the contents of the file.

    .. warning::

        this command does not actually read anything from the working directory, 
        only from git objects and the staging area.
        This is mainly for security reasons (we do not want to give the LLM access 
        to the filesystem).

    Args:
        file (str): The file to print
        start_line (int, optional): The starting line. Defaults to 0.
        num_lines (int, optional): The number of lines to print. Defaults to 20.
        staged (bool, optional): Whether to print the staged version of the file 
        if available. Defaults to True. If False, or if the file 
        is not in the staging area, the latest tracked version is used.
        repository (Repository): The current git repository
    """
    object_id: Oid|None= None # git object id for the file we are looking for

    if staged:
        index: Index = repository.index
        index.read()
        if file in index:
            object_id = index[file].id

    if object_id is None:
        head_commit: Commit= repository.head.peel(ObjectType.COMMIT)
        tree: Tree = head_commit.tree
        if file in tree:
            object_id = tree[file].id

    if object_id is None:
        return FileNotFoundReturnableError(file)

    blob = repository[object_id]
    assert isinstance(blob, Blob)
    if blob.is_binary:
        return FileIsBinaryReturnableError(file)

    end_line = start_line + num_lines if num_lines > 0 else None
    return_data = StringIO()
    with BlobIO(blob, as_path="file") as f:
        # decode the binary output to text (using default system encoding)
        f_text = TextIOWrapper(f)
        for i, line in enumerate(f_text):
            if i >= start_line:
                return_data.write(line)
            if end_line is None or i >= end_line:
                break

    return return_data.getvalue()

@commands.register(description="List files in the repository",
                   parameter_descriptions={
                       "indicate_changes": "Whether to indicate changes in the files",
                       "only_changed": "Whether to only list files that have changes",
                       })
def ls_files(indicate_changes: bool=True, only_changed: bool=False, *, 
             repository: Repository):
    """List all files in the repository

    Args:
        indicate_changes (bool, optional): Whether to indicate changes in the files. 
        only_changed (bool, optional): Whether to only list files that have changes.
        repository (Repository): The current git repository

    Returns:
        list[str]: A list of all files in the repository
    """
    status = repository.status(untracked_files="no")
    status_files = set(status.keys())

    tree = repository.head.peel(ObjectType.COMMIT).tree
    tree_files: set[str] = {"/".join(path) for path, _ in walk_tree(tree)}

    all_files = status_files | tree_files

    return_data = StringIO()

    for file in all_files:
        if only_changed and file not in status: continue
        return_data.write(file)
        if indicate_changes and file in status:
            # libgit2 does not provide a way to say which file was renamed from which
            # (from the status, although one could use diff to find out)
            # (and generally denotes renames as a deletion and an addition)
            # TODO: we could match up the SHA1s of the blobs to find renames, 
            # or use Diff.find_similar()
            stat = status[file]
            if stat & FileStatus.INDEX_NEW:
                return_data.write(" (NEW)")
            if stat & FileStatus.INDEX_MODIFIED:
                return_data.write(" (MODIFIED)")
            if stat & FileStatus.INDEX_DELETED:
                return_data.write(" (DELETED)")
            if stat & FileStatus.INDEX_RENAMED:
                return_data.write(" (RENAMED)")
        return_data.write("\n")

    return return_data.getvalue()

@commands.register(
    description="Print the diff between the staged version of the file and the head",
    parameter_descriptions={
       "file": "The file to print the diff of",
       "context": "The number of lines of context to print",
})
def diff_file(file: str, context: int = 5, *, repository: Repository):
    """Print the diff between the staged version of the file and the head

    Args:
        file (str): The file to print the diff of
        context (int, optional): The number of lines of context to print. Defaults to 5.
        repository (Repository): The current git repository
    """
    #TODO: smart context using tree-sitter
    # to be able to say "in function x, in class y, ..."


    index: Index = repository.index
    tree = repository.head.peel(ObjectType.COMMIT).tree

    if file not in index and file not in tree:
        return FileNotFoundReturnableError(file)
    if file not in index:
        return FileUnchangedError(file)
    if file not in tree:
        return FileNewError(file)

    blob_old = tree[file]
    blob_new = repository[index[file].id]
    assert isinstance(blob_old, Blob) and isinstance(blob_new, Blob)
    if blob_old.is_binary or blob_new.is_binary:
        return FileIsBinaryReturnableError(file)

    patch = repository.diff(
            blob_old,
            blob_new.id, 
            context_lines=context, interhunk_lines=2)
    assert isinstance(patch, Patch)

    ##### for some reason, libgit2 loses the file name when doing the diff
    ##### so we have to manually add it back in
    patch_text = patch.text
    assert isinstance(patch_text, str)
    patch_text_lines = iter(patch_text.splitlines())
    edited_text = StringIO()
    _ = next(patch_text_lines) # skip the first line
    edited_text.write(f"diff --git a/{file} b/{file}\n")
    edited_text.write(next(patch_text_lines) + "\n") # write the line with "index ..."
    next(patch_text_lines) # skip the line with "---"
    next(patch_text_lines) # skip the line with "+++"
    edited_text.write(dedent(f"""\
        --- a/{file}
        +++ b/{file}
        """))
    for line in patch_text_lines: edited_text.write(line + "\n")

    return edited_text.getvalue()

def diff_all_files(context: int = 5, *, repository: Repository, max_content_size=-1, 
                   max_total_size=90_000):
    """Print the diff between the staged version and the head for all modified files

    Args:
        context (int, optional): The number of lines of context to print. Defaults to 5.
        repository (Repository): The current git repository
        max_content_size (int, optional): The maximum size of the content to print 
            for one file
        max_total_size (int, optional): The maximum total size of the content to print
            if True, we automatically cut off the largest files to fit in this size
    """
    status = repository.status(untracked_files="no")
    status_files = set(status.keys())


    tree = repository.head.peel(ObjectType.COMMIT).tree
    tree_files: set[str] = {"/".join(path) for path, _ in walk_tree(tree)}
    index = repository.index
    index.read()

    all_files = status_files | tree_files


    all_file_info = []

    for file in all_files:
        if file not in status: continue
        stat = status[file]
        content = None
        status_text = ""
        if stat & FileStatus.INDEX_NEW:
            status_text = " (NEW)"
            try: content = repository[index[file].id].data.decode()
            except UnicodeDecodeError: continue # skip binary files
        if stat & FileStatus.INDEX_MODIFIED:
            status_text = " (MODIFIED)"
            content = diff_file(file, context=context, repository=repository)
            if content is None: content = "Binary file, cannot display diff\n"
        if stat & FileStatus.INDEX_DELETED:
            status_text = " (DELETED)"
        if stat & FileStatus.INDEX_RENAMED:
            status_text = " (RENAMED)"
        if not status_text: continue

        file_info = StringIO()

        file_info.write(f"------------ {file} {status_text}------------\n")
        if content: 
            content = str(content)
            if max_content_size > 0 and  len(content) > max_content_size: 
                content = content[:max_content_size] + "\n[...]\n"
            file_info.write(content)
        file_info.write("\n")
        all_file_info.append(file_info.getvalue())

    all_file_info_len = [len(i) for i in all_file_info]
    truncation = compute_truncation(all_file_info_len, max_total_size)
    def truncate(s, t):
        if t is None: return s
        if len(s) <= t: return s
        truncated_str = "\n[...]\n"
        return s[:t - len(truncated_str)] + truncated_str
    if truncation is not None:
        all_file_info = [truncate(i, truncation) for i in all_file_info]

    return_data = StringIO()
    for file_info in all_file_info:
        return_data.write(file_info)

    return return_data.getvalue()
