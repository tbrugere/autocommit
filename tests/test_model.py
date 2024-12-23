"""
Tests in this file should all be marked as flaky, 
since they rely on an LLM's response, which is not deterministic.
"""
import os
from pathlib import Path
from textwrap import dedent

import pytest

from mistral_tools.conversation import ModelConversation
from mistral_tools.tool_register import CommandRegister
from mistral_tools.utils import RateLimiter

rate_limit = RateLimiter(1.05)


@pytest.mark.flaky(retries=3)
def test_conversation(api_key):
    model = "mistral-large-latest"
    tool_register = None
    conversation = ModelConversation(model=model, api_key=api_key, tool_register=tool_register, rate_limit=rate_limit)
    basic_prompt = dedent("""
        You are a computer test program.
        Please say "hello world". Do not capitalize. Do not add punctuation.
        Do not say anything else than "hello world". 
        Only print the letters of the phrase "hello world", in lowercase""")

    conversation.add_message(basic_prompt)
    response = conversation.send()

    assert response.message.content == "hello world"

@pytest.mark.flaky(retries=3)
def test_tool_calling(api_key):
    commands = CommandRegister(bindable_parameters=("df",))

    called_retrieve_payment_date = False
    call_arguments = None
    data = "this is the data"

    @commands.register(
            description="Get payment status of a transaction", 
            parameter_descriptions={"transaction_id": "The transaction id.",})
    def retrieve_payment_status(df: str, transaction_id: str) -> str:
        assert False, "this function should not be called"

    @commands.register(
            description="Get payment date of a transaction", 
            parameter_descriptions={"transaction_id": "The transaction id.",})
    def retrieve_payment_date(df: str, transaction_id: str) -> str:
        nonlocal called_retrieve_payment_date
        nonlocal call_arguments
        called_retrieve_payment_date = True
        call_arguments = (df, transaction_id)
        return "2022-10-03"

    tool_register = commands.bind(df=data)

    date_prompt = dedent("""
        Please print the date of the transaction with id 1234. 
        Print the date in ISO 8601 format.
        Do not print anything else, only the date in iso format, no text or punctuation.
        """)

    model = "mistral-large-latest"

    conversation = ModelConversation(
            model=model, api_key=api_key, tool_register=tool_register, 
            rate_limit=rate_limit)
    
    conversation.add_message(date_prompt)
    conversation.add_prefix("date: ")
    response_1 = conversation.send(tool_choice="auto")
    assert response_1.message.content == ""
    response_2 = conversation.send(tool_choice="none")
    assert called_retrieve_payment_date
    assert call_arguments == (data, "1234")
    assert response_2.message.content.strip() == "2022-10-03"
