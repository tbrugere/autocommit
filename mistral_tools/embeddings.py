"""A wrapper around the Mistral API for getting embeddings"""
from logging import getLogger

from mistralai import Mistral
from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
from mistralai.models.sdkerror import SDKError
import numpy as np

from mistral_tools.utils import RateLimiter

log = getLogger(__name__)

def get_n_tokens(input, model, tokenizer=None):
    """Compute the number of tokens in the input"""
    from mistral_common.protocol.instruct.messages import UserMessage
    from mistral_common.protocol.instruct.request import ChatCompletionRequest
    if tokenizer is None:
        tokenizer = MistralTokenizer.from_model(model, strict=True)
    tokenized = tokenizer.encode_chat_completion(ChatCompletionRequest(
      messages=[UserMessage(content=input)],
      model=model
    ), )
    return len(tokenized.tokens)

class EmbeddingModel():
    """A wrapper around the Mistral API for getting embeddings"""

    client: Mistral
    model: str
    rate_limiter: RateLimiter
    tokenizer: MistralTokenizer
    max_retries: int = 5

    max_n_tokens: int = 16384


    def __init__(self, *, api_key, model, rate_limit: float|RateLimiter=1.1, 
                 max_n_tokens: int = 16384):
        self.model = model
        self.client = Mistral(api_key = api_key)
        self.rate_limiter = rate_limit if isinstance(rate_limit, RateLimiter)\
                else RateLimiter(rate_limit)
        self.tokenizer = MistralTokenizer.from_model(model, strict=True)
        self.max_n_tokens = max_n_tokens

    def get_n_tokens(self, input):
        """Compute the number of tokens in the input"""
        return get_n_tokens(input, self.model, self.tokenizer)

    def get_embeddings_batched(self, inputs):
        """Get the embeddings for a batch of inputs"""
        input_lengths = np.array([self.get_n_tokens(i) for i in inputs])
        filtered_mask = input_lengths >= self.max_n_tokens
        filtered = np.array(inputs, dtype=object)[~filtered_mask]
        embeddings_filtered = self.get_embeddings_batched_filtered(filtered,)
        if embeddings_filtered is None:
            return None, filtered_mask
        _, embed_size = embeddings_filtered.shape
        embeddings = np.zeros((len(inputs), embed_size))
        embeddings[~filtered_mask, :] = embeddings_filtered
        return embeddings, filtered_mask


    def get_embeddings_batched_filtered(self, inputs_filtered,):
        """Get the embeddings for a batch of inputs without checks

        assumes all inputs are smaller than the max n tokens
        """
        batch_results = []
        if len(inputs_filtered) == 0:
            return None
        inputs_it = iter(inputs_filtered)
        current_batch = []
        current_batch_size = 0
        next_in = next(inputs_it)

        while True: 
            next_in_size = self.get_n_tokens(next_in)
            if current_batch_size + next_in_size >= self.max_n_tokens:
                batch_results.append(self.get_batch_embeddings(current_batch))
                current_batch = []
                current_batch_size = 0
            else:
                current_batch.append(next_in)
                current_batch_size += next_in_size

                try: next_in = next(inputs_it)
                except StopIteration:
                    batch_results.append(self.get_batch_embeddings(current_batch))
                    break

        return np.concatenate(batch_results, axis=0)

    
    def get_batch_embeddings(self, batch):
        """Get the embeddings for a batch of inputs smaller than the max n tokens

        retries on rate limit errors
        """
        for _ in range(self.max_retries):
            try:
                return self._get_batch_embeddings(batch)
            except SDKError as e:
                if e.status_code != 429:
                    raise
                log.warning("Rate limit error, retrying "
                            f"(error {e.status_code}: {e.message})")
                # sleep twice the rate limit to be safe
                with self.rate_limiter: pass
                with self.rate_limiter: pass
        else:
            raise RuntimeError(f"Rate limit error after {self.max_retries} retries")


    def _get_batch_embeddings(self, batch):
        """Get the embeddings for a batch of inputs smaller than the max n tokens"""
        with self.rate_limiter: 
            embeddings_batch_response = self.client.embeddings.create(
                model="mistral-embed",
                inputs=batch
            )
        return np.array([d.embedding for d in  embeddings_batch_response.data])


    # TODO: add a method to use https://docs.mistral.ai/capabilities/batch/ 
    # for high volumes


