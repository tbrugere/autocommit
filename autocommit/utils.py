from dataclasses import dataclass
import inspect
from inspect import signature
from typing import Callable
from warnings import warn

from pygit2.enums import ObjectType


#############################################################################
### Error management (not raised, but returned, for interaction with the llm)
#############################################################################

@dataclass
class ReturnableError():
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


#############################################################################
### Git utils
#############################################################################

def walk_tree(tree, *, base_path=()):
    """Walk a tree recursively and yield all blobs in the tree,
    and their path relative to the root tree"""
    for item in tree:
        match item.type:
            case ObjectType.BLOB:
                yield (*base_path, item.name), item
            case ObjectType.TREE:
                yield from walk_tree(item, base_path=(*base_path, item.name,))
            case _:
                warn(f"Unexpected object type {item.type_str} in tree")

###########################################################################$
### Registering and binding commands
### For use with the mistral tool api
#############################################################################

@dataclass
class Parameter():
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

    commands: dict[str, Command]
    bindable_parameters: set[str]

    def __init__(self, bindable_parameters):
        self.commands = {}
        self.bindable_parameters = set(bindable_parameters)

    def register(self, description="", parameter_descriptions=None):
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
        return  [ command.to_json() for command in self.commands.values() ]   

    def bind(self, **bound_parameters):
        return BoundCommandRegister(self, bound_parameters)

@dataclass
class BoundCommandRegister():
    command_register: CommandRegister
    bound_parameters: dict[str, object]

    def bind(self, bindable_parameters, kwargs):
        new_kwargs = {**kwargs}
        for param in bindable_parameters:
            if param not in self.bound_parameters:
                raise ValueError(f"Parameter {param} not bound")
            new_kwargs[param] = self.bound_parameters[param]
        return new_kwargs

    def __getitem__(self, name):
        if name in self.command_register.commands:
            command = self.command_register.commands[name]
            return self.bind_command(command)
        raise AttributeError(f"Command {name} not found")

    def bind_command(self, command: Command):
        def bound_command(**kwargs):
            bound_parameters = self.bind(command.bindable_parameters, kwargs)
            result = command.function(**bound_parameters)
            # potentially handle returnable errors here
            if isinstance(result, ReturnableError):
                return self.handle_returnable_error(result)
            return result
        return bound_command

    def handle_returnable_error(self, error: ReturnableError):
        return str(error)


