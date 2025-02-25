from ospo_tools.artifact_management.python_env_manager import PythonEnvManager
from ospo_tools.artifact_management.source_code_manager import SourceCodeManager
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.project_scope import ProjectScope
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
import requests
from typing import Any, Dict, Optional


class PypiMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        python_env_manager: PythonEnvManager,
        project_scope: ProjectScope,
    ) -> None:
        self.top_package = top_package
        self.source_code_manager = source_code_manager
        self.python_env_manager = python_env_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = metadata.copy()

        # setup pyenv
        top_package_path = self._find_top_metadata_path(updated_metadata)
        if top_package_path is None:
            return updated_metadata

        top_package_env = self.python_env_manager.get_environment(top_package_path)
        if top_package_env is None:
            return updated_metadata

        # get the list of dependencies
        dependencies = PythonEnvManager.get_dependencies(top_package_env)
        if dependencies is None:
            return updated_metadata
        for dependency, version in dependencies:
            # get the metadata from pypi API
            pypi_metadata = self._get_metadata_from_pypi(dependency, version)
            if pypi_metadata is None:
                continue
            if "info" in pypi_metadata:
                pypi_info = pypi_metadata["info"]
            else:
                pypi_info = {"name": dependency}

            origin = "pypi:" + dependency
            if "project_urls" in pypi_info:
                if "Source" in pypi_info["project_urls"]:
                    origin = pypi_info["project_urls"]["Source"]

            dep_metadata = Metadata(
                name=pypi_info["name"],
                origin=origin,
                local_src_path=None,
                license=[pypi_info["license"]] if "license" in pypi_info else [],
                version=pypi_info["version"] if "version" in pypi_info else None,
                copyright=[pypi_info["author"]] if "author" in pypi_info else [],
            )
            updated_metadata.append(dep_metadata)
        return updated_metadata

    def _get_metadata_from_pypi(
        self, package: str, version: str
    ) -> Optional[Dict[str, Any]]:
        # get metadata from pypi API
        request_uri = f"https://pypi.org/pypi/{package}/{version}/json"
        response = requests.get(request_uri)
        if response.status_code == 404:
            return None
        return response.json()  # type: ignore

    def _translate_name_gh_to_pypi_sbom(self, name: str) -> str:
        ret = name.replace("https://", "")
        ret = ret.replace("http://", "")
        ret = ret.replace("github.com/", "com.github.")
        return ret

    def _find_top_metadata_path(self, metadata: list[Metadata]) -> str | None:
        translated_top_pkg_name = self._translate_name_gh_to_pypi_sbom(self.top_package)
        for package in metadata:
            if (
                package.name == self.top_package
                or package.name == translated_top_pkg_name
            ):
                if package.local_src_path is not None:
                    return package.local_src_path
                if package.origin is not None:
                    pkg_source = self.source_code_manager.get_code(package.origin)
                    if pkg_source is not None:
                        package.local_src_path = pkg_source.local_full_path
                        return pkg_source.local_full_path
            if package.origin is not None and package.origin.endswith(self.top_package):
                pkg_source = self.source_code_manager.get_code(package.origin)
                if pkg_source is not None:
                    package.local_src_path = pkg_source.local_full_path
                    return pkg_source.local_full_path
        return None
