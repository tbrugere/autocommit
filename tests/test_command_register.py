from typing import TypeAlias

import pytest

from mistral_tools.tool_register import Parameter, Command, CommandRegister
data: TypeAlias = str # I don't want to import pandas here, these functions are not getting called anyway

@pytest.fixture
def command_register():
    commands = CommandRegister(bindable_parameters=("df",))

    @commands.register(
            description="Get payment status of a transaction", 
            parameter_descriptions={"transaction_id": "The transaction id.",})
    def retrieve_payment_status(df: data, transaction_id: str) -> str:
        return f"called retrieve_payment_status with {df} and {transaction_id}"

    @commands.register(
            description="Get payment date of a transaction", 
            parameter_descriptions={"transaction_id": "The transaction id.",})
    def retrieve_payment_date(df: data, transaction_id: str) -> str:
        return f"called retrieve_payment_date with {df} and {transaction_id}"
    
    return commands

# example from https://docs.mistral.ai/capabilities/function_calling/
expected_tools= [
    {
        "type": "function",
        "function": {
            "name": "retrieve_payment_status",
            "description": "Get payment status of a transaction",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "The transaction id.",
                    }
                },
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_payment_date",
            "description": "Get payment date of a transaction",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "The transaction id.",
                    }
                },
                "required": ["transaction_id"],
            },
        },
    }
]


def test_command_register_to_json(command_register):
    tools = command_register.to_json()
    assert tools == expected_tools

def test_command_register_bind(command_register):
    bound = command_register.bind(df="DATA")
    assert bound["retrieve_payment_status"](transaction_id="123") == "called retrieve_payment_status with DATA and 123"
    assert bound["retrieve_payment_date"](transaction_id="123") == "called retrieve_payment_date with DATA and 123"
