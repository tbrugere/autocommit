import os
from pathlib import Path

from pygit2.enums import FileStatus, ObjectType
from pygit2.repository import Repository

from basic_rag import RAGDatabase
from autocommit.utils import walk_tree

def get_project_ragdb(repo_path, rate_limit=1.1):
    storage_dir = repo_path / ".autocommit_storage_dir"
    storage_dir.mkdir(exist_ok=True)
    return RAGDatabase(storage_dir / "rag.sqlite", storage_dir / "rag.index", rate_limit=rate_limit)


def build_ragdb(api_key, repo_path_str, update=True):
    repo_path = Path(repo_path_str)
    repo = Repository(repo_path_str)
    tree = repo.head.peel(ObjectType.COMMIT).tree

    if api_key is None:
        api_key_file = storage_dir / "api_key"
        if "MISTRAL_API_KEY" in os.environ:
            api_key = os.environ["MISTRAL_API_KEY"]
        elif api_key_file.exists():
            api_key = api_key_file.read_text().strip()
        else: raise ValueError("No api key found. Please specify a key file or set the MISTRAL_API_KEY environment variable")

    ragdb = get_project_ragdb(repo_path)

    file_paths = []
    file_objects = []

    for path, blob in walk_tree(tree):
        file_paths.append("/".join(path))
        file_objects.append(blob.data)

    
    if update:
        ragdb.update_index(file_objects, file_paths=file_paths, api_key=api_key)
    else:
        ragdb.generate_index(file_objects, file_paths=file_paths, api_key=api_key)



