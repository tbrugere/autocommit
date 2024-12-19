"""A simple RAG database

A very simple RAG database that combines a faiss index and a SQLite database 
to store chunks of text with embeddings.
Embeddings are computed using the mistral API.

This is adapted for storing a relatively low amount of chunks, in an on-disk store.
"""

from .basic_rag import RAGDatabase


__all__ = ['RAGDatabase']
