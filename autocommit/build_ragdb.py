from pathlib import Path

from pygit2.enums import ObjectType
from pygit2.repository import Repository

from basic_rag import RAGDatabase
from autocommit.utils import get_api_key, walk_tree

def get_project_ragdb(repo_path, rate_limit=1.1, delete_if_exists=False):
    """Get the RAG database from the ``.autocommit_storage_dir`` directory"""
    storage_dir = repo_path / ".autocommit_storage_dir"
    storage_dir.mkdir(exist_ok=True)
    sqlite_file = storage_dir / "rag.sqlite"
    index_file = storage_dir / "rag.index"
    if delete_if_exists:
        sqlite_file.unlink(missing_ok=True)
        index_file.unlink(missing_ok=True)
    return RAGDatabase(storage_dir / "rag.sqlite", storage_dir / "rag.index", 
                       rate_limit=rate_limit)


def build_ragdb(api_key, repo_path_str, update=True):
    """Build or update the RAG database for the repository"""
    repo_path = Path(repo_path_str)
    repo = Repository(repo_path_str)
    tree = repo.head.peel(ObjectType.COMMIT).tree

    ragdb = get_project_ragdb(repo_path, delete_if_exists=not update)

    file_paths = []
    file_objects = []

    for path, blob in walk_tree(tree):
        file_paths.append("/".join(path))
        file_objects.append(blob.data)

    
    if update:
        ragdb.update_index(file_objects, file_paths=file_paths, api_key=api_key)
    else:
        ragdb.generate_index(file_objects, file_paths=file_paths, api_key=api_key)

