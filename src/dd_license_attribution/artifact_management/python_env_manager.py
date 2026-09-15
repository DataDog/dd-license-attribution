# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import hashlib
import json
import logging
import re
import tomllib
from datetime import datetime

import packaging.markers
import pytz

from dd_license_attribution.adaptors.os import (
    change_directory,
    list_dir,
    open_file,
    output_from_command,
    path_exists,
    path_join,
    remove_file,
    run_command,
    write_file,
)
from dd_license_attribution.artifact_management.artifact_manager import ArtifactManager

logger = logging.getLogger("dd_license_attribution")


def _normalize_package_name(name: str) -> str:
    """Apply PEP 503 package name normalization.

    Distribution names are equivalent across ``-``, ``_`` and ``.``
    separators (``typing-extensions`` == ``typing_extensions``), so both
    sides of the installed-vs-lockfile name intersection must use the
    canonical form. The transformation is the one PEP 503 defines.

    Args:
        name: The package name to normalize.

    Returns:
        The normalized (canonical) package name.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


# Marker file dropped into a scan virtualenv after its packages were synced
# to a repository's pylock.toml. Its content is the sync semantics version
# plus the sha256 of the lockfile that was installed, so a changed lockfile
# re-triggers the sync. The version identifies the generation of the sync
# logic: bump it whenever the sync semantics change in a way that means
# environments synced by the previous generation no longer hold exactly the
# pinned closure (e.g. when the seeded-setuptools prune was introduced).
# A marker carrying a different version is not accepted, so such cached
# environments are re-synced once under the current semantics.
LOCK_SYNC_MARKER_FILENAME = ".ddla-pylock-synced"
LOCK_SYNC_MARKER_VERSION = "v3"
# File dropped next to the marker holding the pinned (name, version) pairs
# enumerated from the lockfile: the venv's bootstrap pip is not among them,
# so enumeration from it excludes the toolchain copy - while a pip the
# project genuinely declares as a runtime dependency stays included.
LOCK_SYNC_DEPS_FILENAME = ".ddla-pylock-deps"
# Snippet run with the virtualenv's python to collect its marker-evaluation
# environment (the keys packaging's default_environment defines). Markers
# must be evaluated against the interpreter the venv was created from -
# the `python` on PATH - which is not necessarily the running interpreter.
MARKER_ENVIRONMENT_SNIPPET = """import json, os, platform, sys
print(json.dumps({
    "implementation_name": sys.implementation.name,
    "implementation_version": ".".join(map(str, sys.implementation.version[:3])),
    "os_name": os.name,
    "platform_machine": platform.machine(),
    "platform_release": platform.release(),
    "platform_system": platform.system(),
    "platform_version": platform.version(),
    "python_full_version": platform.python_version(),
    "platform_python_implementation": platform.python_implementation(),
    "python_version": ".".join(platform.python_version_tuple()[:2]),
    "sys_platform": sys.platform,
}))
"""


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
            "pylock.toml",
            "Pipfile",
            "Pipfile.lock",
        ]
        if any(x in files for x in python_project_files):
            is_python_project = True
        if not is_python_project:
            return None
        has_lockfile = "pylock.toml" in files
        # `pip install .` needs a build manifest; a lock-only project (just a
        # pylock.toml) has none, so the unpinned fallback does not apply to it.
        has_build_manifest = "pyproject.toml" in files or "setup.py" in files
        normalized_rsc_path = resource_path.replace("/", "_")
        cached_env = self._get_cached(normalized_rsc_path)
        if cached_env is None or force_update:
            cached_env = self._create_python_env(resource_path, normalized_rsc_path)
        self._install_pip_dependencies(
            resource_path, cached_env, has_lockfile, has_build_manifest
        )
        return cached_env

    def _create_python_env(self, resource_path: str, normalized_rsc_path: str) -> str:
        venv_path = f"{self.local_cache_dir}/{self.timestamped_dir}/{normalized_rsc_path}_virtualenv"
        change_directory(resource_path)
        if run_command(["python", "-m", "venv", venv_path]) != 0:
            raise PyEnvRuntimeError("Failed to create Python virtualenv")
        return venv_path

    def _install_pip_dependencies(
        self,
        resource_path: str,
        venv_path: str,
        has_lockfile: bool,
        has_build_manifest: bool,
    ) -> None:
        change_directory(resource_path)
        if has_lockfile and self._sync_locked_dependencies(venv_path):
            return
        if not has_build_manifest:
            # A lock-only project has no build backend for `pip install .`;
            # degrade gracefully instead of raising.
            logger.warning(
                "Could not install the pinned dependencies from pylock.toml "
                "for %s and the project has no build manifest "
                "(pyproject.toml/setup.py) for an unpinned install; "
                "dependency enumeration may be incomplete",
                resource_path,
            )
            return
        if run_command([f"{venv_path}/bin/python", "-m", "pip", "install", "."]) != 0:
            raise PyEnvRuntimeError(
                "Failed to install dependencies when creating Python virtualenv cache"
            )

    @staticmethod
    def _invalidate_stale_deps(deps_path: str) -> None:
        """Remove a stale pinned-enumeration sidecar after a failed sync.

        A leftover sidecar from a previous successful sync would hijack the
        enumeration with the OLD lockfile's packages while the environment
        actually holds an unpinned install. Removal failures propagate: a
        stale sidecar must never be trusted, so the scan fails loudly
        rather than emit stale SBOM data.
        """
        if path_exists(deps_path):
            remove_file(deps_path)

    @staticmethod
    def _venv_marker_environment(python: str) -> dict[str, str] | None:
        """Collect the marker-evaluation environment of the venv's interpreter.

        Markers must be evaluated against the interpreter the scan
        virtualenv was created from - the `python` on PATH - which is not
        necessarily the interpreter running this process.

        Args:
            python: The virtualenv's python executable.

        Returns:
            The marker environment (the keys packaging's
            default_environment defines), or None when it cannot be
            collected (callers fall back to the running interpreter).
        """
        try:
            environment = json.loads(
                output_from_command([python, "-c", MARKER_ENVIRONMENT_SNIPPET])
            )
        except (OSError, ValueError):
            logger.debug("Could not collect the marker environment of %s", python)
            return None
        if not isinstance(environment, dict):
            return None
        return environment

    @classmethod
    def _pinned_pip_version(cls, lock_content: str, python: str) -> str | None:
        """Return the pip version the lockfile pins for the venv environment.

        pip is always present in a scan venv as toolchain, so presence
        alone cannot distinguish a dependency from the bootstrap copy.
        The lockfile's pip entry applies to the scanned environment only
        when its marker (if any) evaluates true for the interpreter the
        venv was created from; a marker-gated pip entry that does not apply
        never pins a version here, so the toolchain pip stays excluded.

        Args:
            lock_content: The raw content of the PEP 751 lockfile.
            python: The virtualenv's python executable.

        Returns:
            The pinned pip version when a pip entry applies to the venv
            environment, None otherwise (including unparseable markers).
        """
        try:
            lock_data = tomllib.loads(lock_content)
        except tomllib.TOMLDecodeError:
            return None
        for package in lock_data.get("packages", []):
            name = package.get("name")
            version = package.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            if _normalize_package_name(name) != "pip":
                continue
            marker = package.get("marker")
            if not isinstance(marker, str):
                return version
            environment = cls._venv_marker_environment(python)
            try:
                if packaging.markers.Marker(marker).evaluate(environment=environment):
                    return version
            except packaging.markers.InvalidMarker:
                logger.debug("Unparseable marker on a pip entry: %s", marker)
                return None
        return None

    @staticmethod
    def _prune_environment(python: str, venv_path: str) -> None:
        """Remove everything a previous install left in the environment.

        pip freeze --all is used because plain freeze skips
        pip/setuptools/wheel by default, but the venv bootstrap seeds
        setuptools on some Python versions and it must not survive into
        the enumeration. pip itself is kept (it cannot be removed from its
        own environment). When the uninstall fails, the virtualenv is
        recreated so the next install starts from a clean environment.

        Args:
            python: The virtualenv's python executable.
            venv_path: The path of the scan virtualenv.

        Raises:
            PyEnvRuntimeError: when the environment cannot be cleaned - a
                dirty environment must not feed stale packages into the
                enumeration.
        """
        frozen = output_from_command([python, "-m", "pip", "freeze", "--all"])
        pinned_names = []
        for line in frozen.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-e")):
                continue
            name: str | None = None
            if "==" in line:
                name = line.split("==")[0]
            elif " @ " in line:
                # Direct references (PEP 610), e.g. the project root left by
                # a previous `pip install .` of the scanned project itself.
                name = line.split(" @ ")[0]
            if name is not None and name.lower() != "pip":
                pinned_names.append(name)
        if not pinned_names:
            return
        if run_command([python, "-m", "pip", "uninstall", "-y", *pinned_names]) == 0:
            return
        logger.warning(
            "Failed to prune existing packages from %s; recreating the "
            "virtualenv so the next install starts from a clean environment",
            venv_path,
        )
        if run_command(["python", "-m", "venv", "--clear", venv_path]) != 0:
            raise PyEnvRuntimeError(
                f"Failed to clean or recreate the Python virtualenv at {venv_path}"
            )

    def _sync_locked_dependencies(self, venv_path: str) -> bool:
        """Install the pinned dependency closure from the pylock.toml in the
        current working directory (the scanned project).

        A PEP 751 lockfile pins the full runtime closure with hashes:
        installing from it makes dependency enumeration reproducible instead
        of resolving whatever happens to be the latest version on PyPI at
        scan time. --no-deps keeps pip from resolving anything outside the
        lockfile (the lockfile is the complete closure, and hash-checking
        mode forbids unhashed extras).

        Anything a previous unpinned install (or an older lockfile) left in
        a cached virtualenv is pruned first, so `pip list` reports exactly
        the pinned closure. A marker file holding the installed lockfile's
        sha256 short-circuits the sync for repeated scans with an unchanged
        lockfile.

        Args:
            venv_path: The path of the scan virtualenv.

        Returns:
            True when the environment holds the lockfile's pinned closure,
            False when the lockfile could not be installed (the caller
            falls back to an unpinned install).
        """
        python = f"{venv_path}/bin/python"
        lock_content = open_file("pylock.toml")
        expected_marker = (
            f"{LOCK_SYNC_MARKER_VERSION}:"
            f"{hashlib.sha256(lock_content.encode('utf-8')).hexdigest()}"
        )
        marker_path = path_join(venv_path, LOCK_SYNC_MARKER_FILENAME)
        deps_path = path_join(venv_path, LOCK_SYNC_DEPS_FILENAME)
        try:
            if (
                path_exists(marker_path)
                and path_exists(deps_path)
                and open_file(marker_path) == expected_marker
            ):
                logger.debug(
                    "Virtualenv at %s already synced to pylock.toml", venv_path
                )
                return True
        except OSError:
            logger.debug("Could not read lock sync marker at %s", marker_path)
        # Parse the pinned pairs up front: a lockfile that cannot be parsed
        # cannot drive the enumeration, so the sync degrades to the unpinned
        # fallback instead of installing into an environment that would
        # enumerate an unfiltered `pip list`.
        try:
            locked_versions = self._parse_locked_versions(lock_content)
        except tomllib.TOMLDecodeError:
            logger.warning(
                "Failed to parse pylock.toml; falling back to an unpinned "
                "install, so dependency enumeration may not be reproducible"
            )
            # The environment still holds the previously synced closure: it
            # must be pruned or the unpinned fallback enumeration (pip
            # list) would report stale packages.
            self._prune_environment(python, venv_path)
            self._invalidate_stale_deps(deps_path)
            return False
        self._prune_environment(python, venv_path)
        # PEP 751 lockfile consumption requires a pip with (experimental)
        # pylock.toml support; fresh virtualenvs (including one just
        # recreated above) may bundle an older pip that would turn every
        # lock install into a failed one.
        if run_command([python, "-m", "pip", "install", "--upgrade", "pip>=26.1"]) != 0:
            logger.warning(
                "Failed to upgrade pip to a PEP 751 capable version in %s; "
                "attempting the pylock.toml install anyway",
                venv_path,
            )
        if (
            run_command(
                [python, "-m", "pip", "install", "--no-deps", "-r", "pylock.toml"]
            )
            != 0
        ):
            logger.warning(
                "Failed to install dependencies from pylock.toml (requires a "
                "pip with PEP 751 lockfile support and wheels matching this "
                "platform); falling back to an unpinned install, so "
                "dependency enumeration may not be reproducible"
            )
            self._invalidate_stale_deps(deps_path)
            return False
        # The sidecar enumerates what pip ACTUALLY installed, intersected
        # with the lockfile's names: marker-gated entries pip filtered out
        # (e.g. a py-version-conditional tomli) are not installed and are
        # excluded, while the venv's bootstrap pip - not in the lockfile -
        # does not leak into the SBOM. A pip the project genuinely declares
        # IS in the lockfile and stays included.
        pinned_pip_version = self._pinned_pip_version(lock_content, python)
        installed = json.loads(
            output_from_command([f"{venv_path}/bin/pip", "list", "--format=json"])
        )
        pinned_packages = []
        for package in installed:
            normalized = _normalize_package_name(package["name"])
            if normalized == "pip":
                # pip is always present as the venv's toolchain. It is a
                # dependency of the scanned project only when a pip entry
                # in the lockfile applies to this environment (its marker,
                # if any, evaluates true) and pins the version that got
                # installed - a marker-gated pip entry leaves the toolchain
                # copy behind, which never matches, even when versions
                # coincide.
                if pinned_pip_version == package["version"]:
                    pinned_packages.append((package["name"], package["version"]))
                continue
            if normalized in locked_versions:
                pinned_packages.append((package["name"], package["version"]))
        write_file(deps_path, json.dumps(pinned_packages))
        # The marker is the commit point: it is only written after the
        # environment holds the pinned closure AND its enumeration is
        # recorded, so a crash mid-sync can never leave a falsely-synced
        # environment behind.
        write_file(marker_path, expected_marker)
        return True

    @staticmethod
    def _parse_locked_versions(lock_content: str) -> dict[str, str]:
        """Collect the pinned package versions from a pylock.toml.

        Args:
            lock_content: The raw content of the PEP 751 lockfile.

        Returns:
            A mapping of normalized package name to pinned version.
            Marker-gated entries are included: pip filters those at
            install time, and the sync intersects the names with what pip
            actually installed.
        """
        lock_data = tomllib.loads(lock_content)
        versions: dict[str, str] = {}
        for package in lock_data.get("packages", []):
            name = package.get("name")
            version = package.get("version")
            if isinstance(name, str) and isinstance(version, str):
                versions[_normalize_package_name(name)] = version
        return versions

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
        """Enumerate the dependency (name, version) pairs of a scan venv.

        For virtualenvs synced to a pylock.toml, the enumeration comes from
        the lockfile (via the .ddla-pylock-deps file written at sync time):
        exactly the pinned closure, with the venv's bootstrap pip excluded
        unless the project declares pip as a runtime dependency. Otherwise
        (unpinned installs) the enumeration is whatever `pip list` reports.

        Args:
            venv_path: The path of the scan virtualenv.

        Returns:
            The (name, version) pairs, or None when they cannot be read.
        """
        deps_path = path_join(venv_path, LOCK_SYNC_DEPS_FILENAME)
        if path_exists(deps_path):
            try:
                raw_deps = json.loads(open_file(deps_path))
                if not isinstance(raw_deps, list):
                    raise ValueError("sidecar is not a list of [name, version] pairs")
                deps: list[tuple[str, str]] = []
                for entry in raw_deps:
                    if not isinstance(entry, list) or len(entry) != 2:
                        raise ValueError("sidecar entry is not a [name, version] pair")
                    deps.append((str(entry[0]), str(entry[1])))
                return deps
            except (OSError, ValueError, TypeError):
                logger.debug("Could not read %s", deps_path)
        out = output_from_command([f"{venv_path}/bin/pip", "list", "--format=json"])
        json_out = json.loads(out)
        return [(x["name"], x["version"]) for x in json_out]
