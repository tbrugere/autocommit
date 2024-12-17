import io
import functools as ft
from pydantic import BaseModel, ConfigDict

class Config(BaseModel):
    """Configuration for autocommit"""

    enable_rag: bool = True
    enable_function_calls: bool = True
    isolation: bool = False
    debug: bool = False

    model_config = ConfigDict(
        ignored_types = (ft.cached_property,), 
        protected_namespaces = (), 
        extra = "forbid", 
    )

    @classmethod
    def from_json_file(cls, file):
        """Read the configuration from a json file"""
        if not isinstance(file, io.IOBase):
            with open(file) as f: cls.from_json_file(f)
        json = file.read()
        return cls.model_validate_json(json)

    def to_json_file(self, file):
        """Write the configuration to a json file"""
        if not isinstance(file, io.IOBase):
            with open(file, "w") as f: self.to_json_file(f)
        file.write(self.model_dump_json())

