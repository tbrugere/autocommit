from pathlib import Path
import random

import pytest

from basic_rag import RAGDatabase

# mistral_api_key = Path(".mistral-api-key").read_text().strip()
#
# files = [Path("./basic_rag/__init__.py")]
#
# ragdb = RAGDatabase(Path("/tmp/test.sqlite"), Path("/tmp/test.index"))
# ragdb.generate_index(files, api_key=mistral_api_key)

@pytest.fixture()
def rag_test_directory(tmp_path: Path):
    dir = tmp_path / "rag_test_directory"
    dir.mkdir(exist_ok=True)

    files = [
        dir / "file1.txt",
        dir / "file2.txt",
        dir / "subdir" / "file3.txt",
    ]

    file_lengths = [
        10, 
        17, 
        23
    ]

    for file, length in zip(files, file_lengths):
        file.parent.mkdir(exist_ok=True, parents=True)
        with file.open("w") as f:
            for lineno in range(length):
                f.write(f"{file.name} - line {lineno}\n")
    
    return dir

@pytest.fixture()
def tmp_rag_db(tmp_path: Path):
    return RAGDatabase(tmp_path / "test.sqlite", tmp_path / "test.index")


def test_chunks(rag_test_directory, tmp_rag_db, chunk_size = 7, overlap = 2):
    files = list(rag_test_directory.glob("**/*.txt"))
    chunks = list(tmp_rag_db.get_all_chunks(files, 
                                            chunk_size=chunk_size, overlap=overlap))

    # 1. test that chunks are the right size, 
    # and that they correspond to the right lines in files
    for chunk in chunks:
        file = (rag_test_directory /  chunk.file_path).read_text().splitlines()
        assert chunk.text_chunk == "\n".join(file[chunk.start_line:chunk.end_line])
        assert chunk.end_line - chunk.start_line <= chunk_size
        assert (chunk.end_line - chunk.start_line == chunk_size 
                or chunk.end_line == len(file))

    # 2. test that chunks are unique
    chunk_texts = set(chunk.text_chunk for chunk in chunks)
    assert len(chunk_texts) == len(chunks)

    # 3. test that overlap is correct
    for file in files:
        chunks_file = [chunk for chunk in chunks if chunk.file_path == str(file)]
        chunks_file.sort(key=lambda chunk: chunk.start_line)
        for i in range(1, len(chunks_file)):
            assert  chunks_file[i-1].end_line - chunks_file[i].start_line == overlap

def test_retrieval(tmp_rag_db, rag_test_directory, api_key):
    """Check that if we look for the 1-nn of a chunk, we get the same chunk"""
    files = list(rag_test_directory.glob("**/*.txt"))
    rag_test_directory = rag_test_directory
    chunk_size = 7
    overlap = 2
    chunks = list(tmp_rag_db.get_all_chunks(files, 
                                            chunk_size=chunk_size, overlap=overlap))
    tmp_rag_db.generate_index(files, overlap=overlap, chunk_size=chunk_size, 
                              api_key=api_key)

    random_chunk = chunks[random.randint(0, len(chunks)-1)]
    nearest_chunk, score = tmp_rag_db.query(random_chunk.text_chunk, n_results=1, 
                                     api_key=api_key)
    assert nearest_chunk[0].text_chunk == random_chunk.text_chunk

