from dataclasses import dataclass
import inspect
from inspect import signature
from typing import Callable
from warnings import warn

from pygit2.enums import ObjectType

"""
Error management (not raised, but returned, for interaction with the llm)
-------------------------------------------------------------------------
"""

@dataclass
class ReturnableError():
    """An error message that can be returned by a function, and coverted to a string
    (to be sent to the LLM)"""
    error_type: str
    message: str

    def __str__(self):
        return f"{self.error_type}: {self.message}"

class FileNotFoundReturnableError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("FileNotFound", f"File {file} not found in the repository")

class FileIsBinaryReturnableError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("FileIsBinary", f"File {file} is binary, cannot print")

class FileUnchangedError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("FileUnchanged", f"File {file} was not changed in this commit")

class FileNewError(ReturnableError):
    def __init__(self, file: str):
        super().__init__("NewFile", f"File {file} is new, cannot print diff")


"""
Git utils
---------

Miscellaneous utilities for working with git objects
"""

def walk_tree(tree, *, base_path=()):
    """Walk a tree recursively and yield all blobs in the tree,
    and their path relative to the root tree

    Args:
        tree (Tree): The tree to walk
        base_path (tuple, optional): The path to the current tree. Defaults to ().
    """
    for item in tree:
        match item.type:
            case ObjectType.BLOB:
                yield (*base_path, item.name), item
            case ObjectType.TREE:
                yield from walk_tree(item, base_path=(*base_path, item.name,))
            case _:
                warn(f"Unexpected object type {item.type_str} in tree")

"""
Registering and binding commands (tools)
----------------------------------------

The classes that follow are intendeded to automate usage of the 
Mistral tool/function calling api 
(see https://docs.mistral.ai/capabilities/function_calling/)

It includes 

- Automatic generation of the json representation of the tools
- Binding of parameters (to handle local state. 
    For example in this codebase, the git repository is passed as a bound parameter)

"""

@dataclass
class Parameter():
    """A parameter of a command"""
    name: str
    type: type
    description: str
    optional: bool

    def to_json(self):
        # TODO: handle more types as needed
        if self.type == str: type_str = "string"
        elif self.type == int: type_str = "integer"
        elif self.type == bool: type_str = "boolean"
        elif self.type == float: type_str = "number"
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
        return {
                "type": "object",
                "properties": {
                    name: parameter.to_json()
                    for name, parameter in self.parameters.items()
                }, 
                "required": [name for name, parameter in self.parameters.items() if not parameter.optional]
            }

    def to_json_inner(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_to_json(), 
        }

    def to_json(self):
        return {
            "type": "function",
            "function": self.to_json_inner()
        }

class CommandRegister():
    """The main class for registering commands / tools that can be called by the LLM

    To add a command, use the `register` decorator.

    To generate the json representation of the commands, use the `to_json` method. It will ignore the bindable parameters.

    Args:
        bindable_parameters (set[str]): The parameters that can be bound to a value locally (as opposed to being passed by the LLM)

    """

    commands: dict[str, Command]
    bindable_parameters: set[str]

    def __init__(self, bindable_parameters):
        self.commands = {}
        self.bindable_parameters = set(bindable_parameters)

    def register(self, description="", parameter_descriptions=None):
        """Decorator to register a command

        All parameters of the function should be decorated with a type among ``str``, ``int``, ``float``, ``bool`` (except for the bindable parameters). 
        This function will use the type annotations to generate the json representation of the command.

        Args:
            description (str, optional): The description of the command. Defaults to "".
            parameter_descriptions (dict[str, str], optional): The descriptions of the parameters. Defaults to "" for every command, but you should really change that.

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
                    parameters[param.name] = self.parameter_of_inspected(param, parameter_descriptions)

            command = Command(name, f, parameters, bindable_parameters, description)
            self.commands[name] = command
            return f
        return decorator

    @staticmethod
    def parameter_of_inspected(p: inspect.Parameter, descriptions: dict[str, str]) -> Parameter:
        if p.annotation == inspect.Parameter.empty:
            raise ValueError(f"Parameter {p.name} has no type annotation")
        return Parameter(p.name, 
                         p.annotation, 
                         descriptions.get(p.name, ""), 
                         optional=p.default != inspect.Parameter.empty)

    def to_json(self):
        """Generate the json representation of the commands. 
        This can be passed directly as the tools parameters to :func:`Mistral.chat.complete`"""
        return  [ command.to_json() for command in self.commands.values() ]   

    def bind(self, **bound_parameters):
        """Bind the parameters to the commands.

        Args:
            **bound_parameters: The parameters to bind
        Returns:
            BoundCommandRegister: A bound version of the command register.
        """
        return BoundCommandRegister(self, bound_parameters)

@dataclass
class BoundCommandRegister():
    """A command register with bound parameters.

    This object behaves like the BoundCommandRegister, except bound commands can be accessed with the getitem operator like so:

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
            bound_parameters = self.bind(command.bindable_parameters, kwargs)
            result = command.function(**bound_parameters)
            # potentially handle returnable errors here
            if isinstance(result, ReturnableError):
                return self.handle_returnable_error(result)
            return result
        return bound_command

    def to_json(self):
        """Generate the json representation of the commands.

        This command simply calls the to_json method of the underlying command register.
        """
        return self.command_register.to_json()

    def handle_returnable_error(self, error: ReturnableError):
        """Convert a returnable error to a string. 
        This can be overriden in a subclass to handle the errors differently"""
        return str(error)


