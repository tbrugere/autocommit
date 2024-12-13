from dataclasses import dataclass
from typing import Sequence
from hashlib import sha1
from io import BytesIO
import numpy as np
from pathlib import Path

import faiss
import sqlite3

from mistral_tools.utils import RateLimiter
from mistral_tools.embeddings import EmbeddingModel

@dataclass
class TextChunk():
    text_chunk: str
    file_path: Path
    start_line: int
    end_line: int

    def to_str(self):
        return f"----{self.file_path}:l{self.start_line} to l{self.end_line}-----\n{self.text_chunk}"

class RAGDatabase():
    """Simple RAG database implemented as 
    1. a sqlite database with a single table with columns
        id, text_chunk, embedding, file_path, start_line, end_line, file_sha
    2. a faiss index

    I ended up re-coding this because I was not able to find a RAG database that was both simple enough (no server needed, no huge framework) and flexible enough.
    """

    db_path: Path
    index_path: Path

    index: faiss.Index
    db: sqlite3.Connection

    rate_limit: RateLimiter

    max_id: int

    model: str
    max_n_tokens: int

    def __init__(self, db_path: Path, index_path: Path, rate_limit: RateLimiter|float = 1.1, model="mistral-embed", max_n_tokens=16384):
        self.db_path = db_path
        self.index_path = index_path

        self.db = sqlite3.connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS rag (id INTEGER PRIMARY KEY, text_chunk TEXT, embedding NULLABLE BLOB, file_path TEXT, start_line INTEGER, end_line INTEGER, file_sha BLOB)")
        self.db.commit()

        self.model = model
        self.max_n_tokens = max_n_tokens

        max_id, = self.db.execute("SELECT MAX(id) FROM rag").fetchone()
        max_id = max_id if max_id is not None else 0
        self.max_id = max_id

        self.rate_limit = rate_limit if isinstance(rate_limit, RateLimiter) else RateLimiter(rate_limit)

        if index_path.exists():
            self.index = faiss.read_index(str(index_path))
        else:
            inner_index = faiss.IndexFlatL2(1024)
            # ivf_index = faiss.IndexIVFFlat(inner_index, 1024, n_cells)
            self.index = faiss.IndexIDMap(inner_index)


    def insert_db(self,*,  id=None, text_chunk, embedding, file_path, start_line, end_line, file_sha , do_commit=True, add_to_index=False):
        cursor = self.db.cursor()
        if id is None: 
            id = self.max_id + 1
            self.max_id = id
        cursor.execute("INSERT INTO rag VALUES(?, ?, ?, ?, ?, ?, ?)", 
                (id, text_chunk, embedding, str(file_path), start_line, 
                                end_line, file_sha.digest()))

        if embedding is not None and add_to_index:
            self.index.add_with_ids(embedding, id)

        if do_commit: self.commit()

        return id

    @staticmethod
    def get_chunks(file, chunk_size=25, overlap=5):
        chunk_limits = chunk_size - overlap
        if isinstance(file, Path): lines = file.read_text().splitlines()
        else: lines = file.decode().splitlines()
        n_lines = len(lines)
        
        chunk_starts = list(range(0, n_lines, chunk_limits))
        chunk_ends = [min(n_lines, s + chunk_size) for s in chunk_starts]
        assert len(chunk_starts) == len(chunk_ends)
        chunks = (lines[s:e] for s, e in zip(chunk_starts, chunk_ends) )
        chunks = ["\n".join(c) for c in chunks]

        return chunks, chunk_starts, chunk_ends

    def generate_index(self, files: Sequence[Path|bytes], *, api_key, chunk_size=25, overlap=5, file_paths: Sequence[str]|None = None):
        all_chunks = []
        all_chunk_starts = []
        all_chunk_ends = []
        all_hashes = []
        all_file_paths = []
        file_paths = file_paths or [str(file) for file in files]
        for file, file_path in zip(files, file_paths):
            if isinstance(file, Path): hash = sha1(file.read_bytes())
            else: hash = sha1(file)
            chunks, chunk_starts, chunk_ends = self.get_chunks(file, chunk_size=chunk_size, overlap=overlap)
            all_chunks += chunks
            all_chunk_starts += chunk_starts
            all_chunk_ends += chunk_ends
            all_hashes += [hash] * len(all_chunks)
            all_file_paths += [file_path] * len(all_chunks)

        embedding_model = EmbeddingModel(api_key=api_key, model=self.model, max_n_tokens=self.max_n_tokens)
        embeddings, embeddings_too_long_filter = embedding_model.get_embeddings_batched(all_chunks)

        ids = []

        for chunk, start, end, hash, file_path, embedding, embedding_filter in zip(all_chunks, all_chunk_starts, all_chunk_ends, all_hashes, all_file_paths, embeddings, embeddings_too_long_filter):
            id = self.insert_db(text_chunk=chunk, embedding=embedding if not embedding_filter else None, file_path=file_path, start_line=start, end_line=end, file_sha=hash, do_commit=False)
            ids.append(id)
        ids = np.array(ids)

        if not self.index.is_trained:
            self.index.train(embeddings[~embeddings_too_long_filter])

        self.index.add_with_ids(embeddings[~embeddings_too_long_filter], ids[~embeddings_too_long_filter])

        self.commit()

    def commit(self):
        self.db.commit()
        faiss.write_index(self.index, str(self.index_path))

    def get_chunk_by_id(self, id):
        if not isinstance(id, int): id = int(id)
        res = self.db.execute("SELECT text_chunk, file_path, start_line, end_line FROM rag WHERE id = ?", (id,)).fetchone()
        if res is None: return None
        return TextChunk(*res)

    def query(self, query, n_results=5, *, api_key):
        embedding_model = EmbeddingModel(api_key=api_key, model=self.model, max_n_tokens=self.max_n_tokens, rate_limit=self.rate_limit)
        query_embedding, _ = embedding_model.get_embeddings_batched([query])
        scores, ids = self.index.search(query_embedding, k=n_results)
        chunks = [self.get_chunk_by_id(id) for id in ids[0]]
        return chunks, scores[0]

        

