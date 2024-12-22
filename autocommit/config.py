"""Configuration for autocommit"""
from dataclasses import dataclass
from pathlib import Path
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
            with open(file) as f: return cls.from_json_file(f)
        json = file.read()
        return cls.model_validate_json(json)

    def to_json_file(self, file):
        """Write the configuration to a json file"""
        if not isinstance(file, io.IOBase):
            with open(file, "w") as f: self.to_json_file(f)
            return
        file.write(self.model_dump_json())

@dataclass
class AutocommitDir():
    """Loads data from the autocommit storage directory"""
    data_path: Path
    logfile: Path
    api_key_file: Path
    config_file: Path
    config: Config

    def __post_init__(self):
        """Resolve all paths to absolute paths"""
        for var_name, path in vars(self).items():
            if isinstance(path, Path):
                setattr(self, var_name, path.resolve())

    @classmethod
    def from_dir(cls, data_path: Path):
        """Load the autocommit directory"""
        if not data_path.exists():
            raise FileNotFoundError(f"{data_path} does not exist")
        if not data_path.is_dir():
            raise NotADirectoryError(f"{data_path} is not a directory")
        logfile = data_path / "autocommit.log"
        api_key_file = data_path / "api_key"
        config_file = data_path / "config.json"
        config = Config.from_json_file(config_file)
        return cls(data_path, logfile, api_key_file, config_file, config)

    @classmethod
    def from_repo(cls, repo_path: Path):
        """Load the autocommit directory from the repository"""
        return cls.from_dir(repo_path / ".autocommit_storage_dir")
