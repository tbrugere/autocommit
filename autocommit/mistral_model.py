from contextlib import contextmanager
import json
from logging import getLogger; log = getLogger(__name__)
import time
from typing import Any, Literal

from mistralai import Mistral, MessagesTypedDict
from mistralai import Messages, ToolMessage, UserMessage
from pygit2.repository import Repository

from autocommit.utils import BoundCommandRegister, RateLimiter
from autocommit.commands import commands

class ModelConversation():

    model: str
    messages: list[MessagesTypedDict|Messages] = []
    tool_register: BoundCommandRegister|None
    synced = False # keep track of whether messages added to the conversation have been sent to the model
    rate_limiter: RateLimiter


    def __init__(self, *, model, api_key, tool_register, rate_limit: float|RateLimiter=1.05):
        self.model = model
        self.client = Mistral(api_key = api_key)
        self.tool_register = tool_register
        self.synced = False
        match rate_limit:
            case RateLimiter(): self.rate_limiter = rate_limit
            case float(): self.rate_limiter = RateLimiter(rate_limit)

    def add_message(self, prompt):
        log.debug("------------------ user message ------------------")
        log.debug(prompt)
        with self.changes_sync_state(False):
            self.messages.append(UserMessage(content=prompt))


    def send(self,*, tool_choice: Literal["any", "auto", "none"] = "auto"):
        log.debug("sending messages")
        if self.synced:
            raise ValueError("Already synced, add messages before sending again")
        if self.tool_register is not None:
            tr_param = dict(
                    tools=self.tool_register.to_json(), 
                    tool_choice=tool_choice, )
        else: tr_param = {}
        response = self._inner_send(
                model=self.model,
                messages=self.messages,
                **tr_param
            )
        assert response is not None and response.choices is not None
        # for now, we always select the first choice
        response = response.choices[0]
        self.handle_response(response)
        return response

    def _inner_send(self, **send_params):
        with self.changes_sync_state(True), self.rate_limiter:
            return self.client.chat.complete(**send_params)


    def handle_response(self, response):
        response_message = response.message
        tool_calls = response_message.tool_calls or []
        self.messages.append(response_message)
        for tool_call in tool_calls:
            assert tool_call.type == "function"
            tool_name = tool_call.function.name
            tool_parameters = json.loads(tool_call.function.arguments)
            call_id = tool_call.id
            self.handle_tool_call(tool_name, tool_parameters, tool_call_id=call_id)


    def handle_tool_call(self, tool_name, tool_parameters, tool_call_id):
        log.info(f"Calling {tool_name} with {tool_parameters}")
        assert self.tool_register is not None, "tool_register is not set"
        tool_result = self.tool_register[tool_name](**tool_parameters)
        with self.changes_sync_state(False):
            self.messages.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=tool_result))

    @contextmanager
    def changes_sync_state(self, state: bool):
        """
        context manager that sets the synced state to the given state
        unless the content failed, in which case the sync state is assumed 
        to be false (ie failure -> not synced)"""
        try: yield
        except: 
            self.synced = False
            raise
        else: self.synced = state


def main(api_key, repo_path, max_tool_uses=10):
    agent = "ag:486412fc:20241118:untitled-agent:25c2b440"

    repo = Repository(str(repo_path))
    commands_bound = commands.bind(repo=repo)


    start_prompt = "Here is a list of files in the codebase, outlining which files had changes. Please issue tool calls to understand the changes made in the commit and their purpose"
    prompt = "Please issue tool calls, with explanations or write the final commit message. If you need more information, issue tool calls with explanations of why you are using these functions. If you need no more information, write the commit message. Do not forget to follow formatting instructions and use imperative mood."
    final_prompt = "Please write the commit message. Do not forget to follow formatting instructions and use imperative mood."

    # TODO possibliy prefix? to handle getting title and body

    conversation = ModelConversation(model=agent, api_key=api_key, tool_register=commands_bound)

    conversation.add_message(start_prompt)
    response = conversation.send(tool_choice="any")
    n_remaining_tool_uses = max_tool_uses - 1

    while n_remaining_tool_uses > 1:
        conversation.add_message(prompt)
        response = conversation.send(tool_choice="auto")
        n_remaining_tool_uses -= 1
        if not response.message.tool_calls:
            break
    else:
        conversation.add_message(final_prompt)
        response = conversation.send(tool_choice="none")

    return response.message.content





    




