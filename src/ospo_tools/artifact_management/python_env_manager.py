from datetime import datetime
import json
import pytz
from ospo_tools.artifact_management.artifact_manager import ArtifactManager

from ospo_tools.adaptors.os import (
    list_dir,
    change_directory,
    run_command,
    path_exists,
    output_from_command,
)


class PyEnvRuntimeError(Exception):
    pass


class PythonEnvManager(ArtifactManager):
    def get_environment(
        self, resource_path: str, force_update: bool = False
    ) -> str | None:
        files = list_dir(resource_path)
        is_python_project = False
        python_project_files = [
            "requirements.txt",
            "setup.py",
            "setup.cfg",
            "pyproject.toml",
            "Pipfile",
            "Pipfile.lock",
        ]
        if any(x in files for x in python_project_files):
            is_python_project = True
        if not is_python_project:
            return None
        normalized_rsc_path = resource_path.replace("/", "_")
        cached_env = self._get_cached(normalized_rsc_path)
        if cached_env is None or force_update:
            cached_env = self._create_python_env(resource_path, normalized_rsc_path)
        self._install_pip_dependencies(resource_path, cached_env)
        return cached_env

    def _create_python_env(self, resource_path: str, normalized_rsc_path: str) -> str:
        venv_path = f"{self.local_cache_dir}/{self.timestamped_dir}/{normalized_rsc_path}_virtualenv"
        change_directory(resource_path)
        if run_command(f"python -m venv {venv_path}") != 0:
            raise PyEnvRuntimeError("Failed to create Python virtualenv")
        return venv_path

    def _install_pip_dependencies(self, resource_path: str, venv_path: str) -> None:
        change_directory(resource_path)
        if run_command(f"{venv_path}/bin/python -m pip install .") != 0:
            raise PyEnvRuntimeError(
                "Failed to install dependencies when creating Python virtualenv cache"
            )

    def _get_cached(self, normalized_rsc_path: str) -> str | None:
        threshold = self.setup_time.timestamp() - self.local_cache_ttl
        potential_caches = list_dir(self.local_cache_dir)
        for cache in potential_caches:
            cache_time = datetime.strptime(cache, "%Y%m%d_%H%M%SZ").replace(
                tzinfo=pytz.UTC
            )
            if cache_time.timestamp() < threshold:
                continue
            venv_path = (
                f"{self.local_cache_dir}/{cache}/{normalized_rsc_path}_virtualenv"
            )
            if path_exists(venv_path):
                return venv_path
        return None

    @staticmethod
    def get_dependencies(venv_path: str) -> list[tuple[str, str]] | None:
        out = output_from_command(f"{venv_path}/bin/pip list --format=json")
        json_out = json.loads(out)
        return [(x["name"], x["version"]) for x in json_out]
