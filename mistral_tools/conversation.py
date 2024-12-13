from contextlib import contextmanager
import json
from logging import getLogger; log = getLogger(__name__)
import random

from typing import Literal
from mistralai import (FunctionCall, Mistral, MessagesTypedDict, Messages, 
                       ToolCall, UserMessage, SystemMessage, AssistantMessage, ToolMessage)

from mistral_tools.tool_register import BoundCommandRegister
from mistral_tools.utils import RateLimiter

class ModelConversation():
    """High-level interface to the Mistral completion API

    Handles keeping track of a conversation with a model, 
    and sending messages to the model,
    as well as automatically handling tool calls.
    """

    model: str|None
    agent_id: str|None
    messages: list[MessagesTypedDict|Messages] = []
    tool_register: BoundCommandRegister|None
    synced = False # keep track of whether messages added to the conversation have been sent to the model
    rate_limiter: RateLimiter


    def __init__(self, *,  api_key, tool_register, model, rate_limit: float|RateLimiter=1.1, system_prompt: str|None = None):
        self.model = model
        self.client = Mistral(api_key = api_key)
        self.tool_register = tool_register
        self.synced = False
        match rate_limit:
            case RateLimiter(): self.rate_limiter = rate_limit
            case float(): self.rate_limiter = RateLimiter(rate_limit)
        if system_prompt is not None: self.add_system_prompt(system_prompt)

    def add_system_prompt(self, prompt):
        log.debug("------------------ system prompt")
        log.debug(prompt)
        with self.changes_sync_state(False):
            self.messages.append(SystemMessage(content=prompt))

    def add_message(self, prompt):
        log.debug("------------------ user message")
        log.debug(prompt)
        with self.changes_sync_state(False):
            self.messages.append(UserMessage(content=prompt))

    def add_prefix(self, prefix):
        with self.changes_sync_state(False):
            self.messages.append(SystemMessage(content=prefix, prefix=True))

    def simulate_assistant_message(self, content, *, tool_calls=None):
        log.debug("------------------ simulated assistant message")

        tool_calls_with_id = []

        for tool_name, tool_parameters in tool_calls.items():
            tool_call = ToolCall(
                    function=FunctionCall(name=tool_name, arguments=json.dumps(tool_parameters)), 
                    id=f"{random.randint(0, 1_000_000):06}")
            tool_calls_with_id.append(tool_calls_with_id)

        message = AssistantMessage(content=content, 
                                   tool_calls=tool_calls_with_id)
        

        log.debug(message)
        with self.changes_sync_state(False):
            self.messages.append(Messages(content=message, tool_calls=tool_calls))



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
        response_message = response.message
        self.handle_response(response_message)
        return response

    def _inner_send(self, **send_params):
        log.debug(f"Making client.chat.complete api call")
        with self.changes_sync_state(True), self.rate_limiter:
            return self.client.chat.complete(**send_params)


    def handle_response(self, response_message):
        log.debug("------------------ response ")
        log.debug(response_message.content)
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
