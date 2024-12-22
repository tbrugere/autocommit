Adding context to commit messages
=================================

Generating the commit message with just the content of the diff generally
yields poor results. 
The model needs more context to generate a meaningful commit message.

Autocommit provides two ways to give context to the model:

- By using a Retriaval-Augmented Generation (RAG) approach described in `The RAG database`_ section.
- By using Mistral's `function calling <https://docs.mistral.ai/capabilities/function_calling/>`_ capability to let the model pull in additional context from the codebase. This is described in the `Function calling`_ section.

By default, ``autocommit`` uses the RAG approach to generate commit messages. The function calling approach has several limitations outlined in the `Function calling`_ section, so it is not recommended for general use.

The RAG database
----------------

The RAG approach consists of keeping a database of code snippets from the codebase, 
with `sentence embeddings <https://en.wikipedia.org/wiki/Sentence_embedding>`_, 
and to use a vector similarity search to find code snippets relevant to 
the code in the commit.  Those code snippets are then used to generate the system prompt.

A more detailed introduction to RAG can be found in the `Wikipedia article <https://en.wikipedia.org/wiki/Retrieval-augmented_generation>`_ and a good overview of the state of the art can be found in this `review paper <https://arxiv.org/abs/2312.10997>`_.

This is **enabled by default**. The database is first built from the codebase when 
running ``autocommit setup``. It is stored in the ``.autocommit_storage_dir`` directory (which is always untracked). 
It is then updated in the background everytime a commit is made (through a post-commit git hook).

The RAG database is implemented in the :mod:`basic_rag` module.

.. note::

   Using the RAG approach has a performance cost: 

   - every update to the database will make calls to the Mistral API to generate embeddings for the new code snippets (which is invisible to the user unless they are trying to do another commit immediately since it runs in the background).
   - to generate the commit message, the model now has to first generate an embedding to query the database, and then send the generated prompt to the model. This will take at least 1 second because of the 1 request / second rate limit on the Mistral API.


Function calling
----------------

The function calling approach consists of letting the model call functions from the codebase to get additional context. This uses Mistral's `function calling <https://docs.mistral.ai/capabilities/function_calling/>`_ capability. 

This approach is **not enabled by default** because it has several limitations:

- It requires that the program and the api exchange messages several times, which can be slow because of the rate limiting.

- It generally yields worse results than the RAG approach: the model is less efficient at querying the right files than the embedding approach is. 

- It raises security concerns by giving some kind of disk access to the model (although this is mitigated by the fact that the functions only have access to git objects, not the filesystem).

The functions made available to the model are defined in the :mod:`autocommit.commands` module.
