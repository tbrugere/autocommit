"""Basic RAG database"""
from dataclasses import dataclass
from typing import Sequence, Optional
from hashlib import sha1
import numpy as np
from pathlib import Path
import warnings

import sqlite3

from mistral_tools.utils import RateLimiter
from mistral_tools.embeddings import EmbeddingModel

warnings.filterwarnings("ignore", category=DeprecationWarning, module="faiss")
import faiss # noqa: E402

@dataclass
class TextChunk():
    """A text chunk with metadata"""
    text_chunk: str
    file_path: str
    start_line: int
    end_line: int
    file_hash: Optional[bytes] = None # the hash of the file. 
        #Mainly used for checking if the file has changed for updates


    def to_str(self):
        """Pretty print the text chunk"""
        return (f"----{self.file_path}: l.{self.start_line} "
                f"to l.{self.end_line}-----\n{self.text_chunk}")

class RAGDatabase():
    """Simple RAG database

    implemented as

    1. a sqlite database with a single table with columns
        id, text_chunk, embedding, file_path, start_line, end_line, file_sha
    2. a faiss index

    I ended up re-coding this because I was not able to find a RAG database
    that was both simple enough (no server needed, no huge framework) 
    and flexible enough.
    """

    db_path: Path
    index_path: Path

    index: faiss.Index
    db: sqlite3.Connection

    rate_limit: RateLimiter

    max_id: int

    model: str
    max_n_tokens: int

    def __init__(self, db_path: Path, index_path: Path, 
                 rate_limit: RateLimiter|float = 1.1, model="mistral-embed", 
                 max_n_tokens=16384):
        self.db_path = db_path
        self.index_path = index_path

        self.db = sqlite3.connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS rag "
            "(id INTEGER PRIMARY KEY, text_chunk TEXT, embedding NULLABLE BLOB, "
            "file_path TEXT, start_line INTEGER, end_line INTEGER, file_sha BLOB)")
        self.db.commit()

        self.model = model
        self.max_n_tokens = max_n_tokens

        max_id, = self.db.execute("SELECT MAX(id) FROM rag").fetchone()
        max_id = max_id if max_id is not None else 0
        self.max_id = max_id

        self.rate_limit = (
                rate_limit if isinstance(rate_limit, RateLimiter) 
                else RateLimiter(rate_limit))

        if index_path.exists():
            self.index = faiss.read_index(str(index_path))
        else:
            inner_index = faiss.IndexFlatL2(1024)
            # ivf_index = faiss.IndexIVFFlat(inner_index, 1024, n_cells)
            # ^^^ TODO: implement switching to ivf when the index gets large
            self.index = faiss.IndexIDMap(inner_index)


    def insert_db(self, chunk: TextChunk, *,  id=None,  embedding,
                  do_commit=True, add_to_index=False):
        """Insert a text chunk into the sqlite database and the index"""
        cursor = self.db.cursor()
        if id is None: 
            id = self.max_id + 1
            self.max_id = id
        cursor.execute("INSERT INTO rag VALUES(?, ?, ?, ?, ?, ?, ?)", 
                (id, chunk.text_chunk, 
                 embedding, str(chunk.file_path), chunk.start_line, 
                                chunk.end_line, chunk.file_hash))

        if embedding is not None and add_to_index:
            self.index.add_with_ids(embedding, id) #type: ignore

        if do_commit: self.commit()

        return id

    @staticmethod
    def get_chunks(file, *, chunk_size=25, overlap=5, filename, hash=None):
        """Cut a file into chunks

        Args:
            file: a Path or bytes object
            chunk_size: the size of the chunks
            overlap: the overlap between the chunks
            filename: the filename
            hash: the hash of the file (optional)
        """
        chunk_limits = chunk_size - overlap
        try: 
            if isinstance(file, Path): lines = file.read_text().splitlines()
            else: lines = file.decode().splitlines()
        except UnicodeDecodeError:
            return [] # skip non-text files
        n_lines = len(lines)
        
        chunk_starts = range(0, n_lines, chunk_limits)
        for start in chunk_starts:
            end = min(n_lines, start + chunk_size)
            yield TextChunk("\n".join(lines[start:end]), filename, start, end, 
                            file_hash=hash)

    @classmethod
    def get_all_chunks(cls, files: Sequence[Path|bytes], *, chunk_size=25, 
                       overlap=5, file_paths: Sequence[str]|None = None, 
                       file_shas_to_skip = None):
        """Cut a list of files into chunks

        Args:
            files: the files
            chunk_size: the size of the chunks
            overlap: the overlap between the chunks
            file_paths: the filenames (Optional: if not provided, 
                                       and the files are Path objects
                                       the filenames will be the paths)
            file_shas_to_skip: the file hashes to skip
        """
        file_paths = file_paths or [str(file) for file in files]
        if file_shas_to_skip is None: file_shas_to_skip = set()
        else: file_shas_to_skip = set(file_shas_to_skip)
        for file, file_path in zip(files, file_paths):
            if isinstance(file, Path): hash = sha1(file.read_bytes()).digest()
            else: hash = sha1(file).digest()
            if hash in file_shas_to_skip: continue
            new_chunks = list(cls.get_chunks(file, chunk_size=chunk_size, 
                                overlap=overlap, filename=file_path, hash=hash))
            yield from new_chunks 

    def generate_index(self, files: Sequence[Path|bytes], *, api_key, chunk_size=25,
                       overlap=5, file_paths: Sequence[str]|None = None, 
                       file_shas_to_skip = None):
        """Generate the index from a list of files"""
        all_chunks = list(self.get_all_chunks(files, chunk_size=chunk_size, 
                                              overlap=overlap, file_paths=file_paths, 
                                              file_shas_to_skip=file_shas_to_skip))

        embedding_model = EmbeddingModel(api_key=api_key, model=self.model,
                                         max_n_tokens=self.max_n_tokens)
        embeddings, embeddings_too_long_filter = \
            embedding_model.get_embeddings_batched([c.text_chunk for c in all_chunks])
        if embeddings is None:
            return # no embedddings to add

        ids = []

        for chunk, embedding, embedding_filter in zip(
                all_chunks, embeddings, embeddings_too_long_filter):
            id = self.insert_db(chunk=chunk, 
                                embedding=embedding if not embedding_filter else None,
                                do_commit=False)
            ids.append(id)
        ids = np.array(ids)

        if not self.index.is_trained:
            self.index.train(embeddings[~embeddings_too_long_filter]) # type: ignore

        self.index.add_with_ids(embeddings[~embeddings_too_long_filter], 
                                ids[~embeddings_too_long_filter]) # type: ignore

        self.commit()

    def commit(self):
        """Write changes to disk

        do a database commit, and write the index
        """
        self.db.commit()
        faiss.write_index(self.index, str(self.index_path))

    def get_chunk_by_id(self, id):
        """Get a chunk from database by its id"""
        if not isinstance(id, int): id = int(id)
        res = self.db.execute("SELECT text_chunk, file_path, start_line, "
                              "end_line, file_sha FROM rag WHERE id = ?", 
                              (id,)).fetchone()
        if res is None: return None
        return TextChunk(*res)

    def query(self, query, n_results=5, *, api_key):
        """Do a Knn search on the index"""
        embedding_model = EmbeddingModel(
                api_key=api_key, model=self.model, max_n_tokens=self.max_n_tokens, 
                rate_limit=self.rate_limit)
        query_embedding, _ = embedding_model.get_embeddings_batched([query])
        if query_embedding is None:
            raise RuntimeError("Query too long")
        scores, ids = self.index.search(query_embedding, k=n_results) # type: ignore
        chunks = [self.get_chunk_by_id(id) for id in ids[0]]
        return chunks, scores[0]

        
    def update_index(self, files: Sequence[Path|bytes], *, api_key, chunk_size=25, 
                     overlap=5, file_paths: Sequence[str]|None = None):
        """Update the index from a list of files.

        Like generate_index, but preemptively checks which files have changed, 
        and only updates those.
        """
        files_shas_in_db = self.db\
                .execute("SELECT DISTINCT file_sha FROM rag")\
                .fetchall()
        files_shas_in_db  = set([sha for sha, in files_shas_in_db])
        new_shas = []
        for file in files:
            if isinstance(file, Path): hash = sha1(file.read_bytes()).digest()
            else: hash = sha1(file).digest()
            new_shas.append(hash)
        new_shas = set(new_shas)


        deleted_shas = tuple(new_shas - files_shas_in_db)

        self.db.execute("CREATE TEMP TABLE deleted_shas (sha BLOB)")
        self.db.executemany("INSERT INTO deleted_shas VALUES (?)", 
                            [(sha,) for sha in deleted_shas] )
        self.db.commit()

        deleted_shas_ids = self.db.execute(
                "SELECT id FROM rag INNER JOIN deleted_shas "
                "ON rag.file_sha = deleted_shas.sha").fetchall()
        self.db.execute("DELETE FROM rag WHERE file_sha IN deleted_shas")
        self.db.execute("DROP TABLE deleted_shas")
        self.index.remove_ids(np.array([id for id, in deleted_shas_ids]))
        # self.commit() # only commit after the full update is done
        # to avoid failing with a transient state on disk

        self.generate_index(files, api_key=api_key, chunk_size=chunk_size, 
                            overlap=overlap, file_paths=file_paths, 
                            file_shas_to_skip=files_shas_in_db)
