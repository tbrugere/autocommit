"""Registering and binding commands (tools)

The classes that follow are intended to automate usage of the 
Mistral tool/function calling api 
(see https://docs.mistral.ai/capabilities/function_calling/)

It includes 

- Automatic generation of the json representation of the tools
- Binding of parameters (to handle local state. 
    For example in this codebase, the git repository is passed as a bound parameter)

"""
from typing import Callable
from dataclasses import dataclass
import inspect
from inspect import signature
from logging import getLogger; log = getLogger(__name__)

from mistralai import ToolTypedDict

@dataclass
class ReturnableError():
    """An error message that can be returned by a function

    and converted to a string (to be sent to the LLM)
    """
    error_type: str
    message: str

    def __str__(self):
        """Convert the error to a string"""
        return f"{self.error_type}: {self.message}"

class ParameterError(ReturnableError):
    """Returned by the tool calls if a parameter is incorrect"""

    def __init__(self, message: str):
        super().__init__("ParameterError", message)


@dataclass
class Parameter():
    """A parameter of a command"""
    name: str
    type: type
    description: str
    optional: bool

    def to_json(self):
        """Convert the parameter to Mistral api json representation"""
        # TODO: handle more types as needed
        if self.type is str: type_str = "string"
        elif self.type is int: type_str = "integer"
        elif self.type is bool: type_str = "boolean"
        elif self.type is float: type_str = "number"
        else: raise ValueError(f"Unsupported type {self.type}")
        return {"type": type_str, "description": self.description}

@dataclass
class Command():
    """A command that can be called by the LLM"""
    name: str
    function: Callable
    parameters: dict[str, Parameter]
    bindable_parameters: set[str]
    description: str

    def parameters_to_json(self):
        """Convert the parameters to Mistral api json representation"""
        return {
                "type": "object",
                "properties": {
                    name: parameter.to_json()
                    for name, parameter in self.parameters.items()
                }, 
                "required": [name for name, parameter in self.parameters.items() 
                             if not parameter.optional]
            }

    def _to_json_inner(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_to_json(), 
        }

    def to_json(self):
        """Convert the command to Mistral api json representation"""
        return {
            "type": "function",
            "function": self._to_json_inner()
        }

class CommandRegister():
    """The main class for registering commands / tools that can be called by the LLM

    To add a command, use the `register` decorator.

    To generate the json representation of the commands, use the `to_json` method. 
    It will ignore the bindable parameters.

    Args:
        bindable_parameters (set[str]): The parameters that can be bound to a value 
            locally (as opposed to being passed by the LLM)
    """

    commands: dict[str, Command]
    bindable_parameters: set[str]

    def __init__(self, bindable_parameters):
        self.commands = {}
        self.bindable_parameters = set(bindable_parameters)

    def register(self, description="", parameter_descriptions=None):
        """Decorator to register a command

        All parameters of the function should be decorated with a type among 
        ``str``, ``int``, ``float``, ``bool`` (except for the bindable parameters). 
        This function will use the type annotations to generate the 
        json representation of the command.

        Args:
            description (str, optional): The description of the command. Defaults to "".
            parameter_descriptions (dict[str, str], optional): The descriptions of 
            the parameters. Defaults to "" for every command, 
            but you should really change that.

        """
        if parameter_descriptions is None: parameter_descriptions = {}
        def decorator(f):
            nonlocal description
            nonlocal parameter_descriptions
            name = f.__name__
            signature_f = signature(f)
            parameters = {}
            bindable_parameters = set()
            for param in signature_f.parameters.values():
                if param.name in self.bindable_parameters:
                    bindable_parameters.add(param.name)
                else: 
                    parameters[param.name] = self.parameter_of_inspected(
                            param, parameter_descriptions)

            command = Command(name, f, parameters, bindable_parameters, description)
            self.commands[name] = command
            return f
        return decorator

    @staticmethod
    def parameter_of_inspected(p: inspect.Parameter, descriptions: dict[str, str]) -> Parameter:
        """Generate a :class:`parameter` from inspecting a functions's parameters"""
        if p.annotation == inspect.Parameter.empty:
            raise ValueError(f"Parameter {p.name} has no type annotation")
        return Parameter(p.name, 
                         p.annotation, 
                         descriptions.get(p.name, ""), 
                         optional=p.default != inspect.Parameter.empty)

    def to_json(self) -> ToolTypedDict:
        """Generate the json representation of the commands. 

        This can be passed directly as the tools parameters to 
        :func:`Mistral.chat.complete`
        """
        return  [ command.to_json() for command in self.commands.values() ]   

    def bind(self, **bound_parameters):
        """Bind the parameters to the commands.

        Args:
            **bound_parameters: The parameters to bind
        Returns:
            BoundCommandRegister: A bound version of the command register.
        """
        for param in bound_parameters:
            if param not in self.bindable_parameters:
                raise ValueError(f"Parameter {param} is not bindable")

        return BoundCommandRegister(self, bound_parameters)

@dataclass
class BoundCommandRegister():
    """A command register with bound parameters.

    This object behaves like the BoundCommandRegister, 
    except bound commands can be accessed with the getitem operator like so:

    .. code-block:: python

        commands = CommandRegister(bindable_parameters=("df",))

        @commands.register(
                description="Get payment status of a transaction", 
                parameter_descriptions={"transaction_id": "The transaction id.",})
        def retrieve_payment_status(*, df: data, transaction_id: str) -> str:
            ...

        bound_commands = commands.bind(df=df)

        bound_commands["retrieve_payment_status"](transaction_id="1234")

    """
    command_register: CommandRegister
    bound_parameters: dict[str, object]

    def __getitem__(self, name):
        """Get a bound command by name"""
        if name in self.command_register.commands:
            command = self.command_register.commands[name]
            return self.bind_command(command)
        raise AttributeError(f"Command {name} not found")

    def bind_command(self, command: Command):
        """Returns the bound version of the command
        
        Returns the underlying function of the command, with 
        - the bound parameters already filled in
        - ensuring that the returnable errors are changed into strings

        In general, this is called by the :func:``__getitem__`` method, 
        you should not have to call it directly.
        """
        def bound_command(**kwargs):
            bound_parameters = self.bind_parameters(command.bindable_parameters, kwargs)
            if isinstance(bound_parameters, ReturnableError):
                return self.handle_returnable_error(bound_parameters)
            check_result = self.check_parameters(command, bound_parameters)
            if check_result is not None: return self.handle_returnable_error(check_result)

            result = command.function(**bound_parameters)
            # potentially handle returnable errors here
            if isinstance(result, ReturnableError):
                return self.handle_returnable_error(result)
            return result
        return bound_command

    def bind_parameters(self, bindable_parameters, kwargs):
        """Bind the parameters to the command, and return the bound parameters"""
        for param in bindable_parameters:
            if param in kwargs: 
                log.error(f"Parameter {param} is bindable, it should not be passed")
                return ParameterError(f"No such parameter: {param}")
            kwargs[param] = self.bound_parameters[param]
        return kwargs

    def check_parameters(self, command: Command, kwargs):
        """Check that the parameters are correct for the command"""
        # 1. check that the given parameters are correct and the right typ
        for name, value in kwargs.items():
            if name in command.bindable_parameters: continue
            if name not in command.parameters:
                return ParameterError(f"No such parameter: {name}")
            if not isinstance(value, command.parameters[name].type):
                return ParameterError(f"Parameter {name} is not of the right type")

        # 2. check that there are no missing parameters
        for name, parameter in command.parameters.items():
            if not parameter.optional and name not in kwargs:
                return ParameterError(f"Missing parameter {name}")


    def to_json(self):
        """Generate the json representation of the commands.

        This command simply calls the to_json method of the underlying command register.
        """
        return self.command_register.to_json()

    def handle_returnable_error(self, error: ReturnableError):
        """Convert a returnable error to a string

        This can be overriden in a subclass to handle the errors differently"""
        return str(error)


