# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import ipaddress
import json
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from dd_license_attribution.adaptors.os import (
    open_file,
    output_from_command,
    path_exists,
    path_join,
    walk_directory,
)
from dd_license_attribution.artifact_management.go_package_resolver import (
    SYNTHETIC_MODULE_NAME,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.utils.bounded_download import fetch_bounded_validated

logger = logging.getLogger("dd_license_attribution")

_VANITY_MAX_RESPONSE_BYTES = 64 * 1024
_NAT64_WELL_KNOWN_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


class _GoImportMetaParser(HTMLParser):
    """Extract `<meta name="go-import" content="...">` values from HTML head."""

    def __init__(self) -> None:
        super().__init__()
        self.go_imports: list[str] = []
        self._in_body = False

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self._in_body = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "body":
            self._in_body = True
            return
        if self._in_body or tag != "meta":
            return
        attr_map = {k: v for k, v in attrs if v is not None}
        name = attr_map.get("name")
        if name is not None and name.lower() == "go-import":
            content = attr_map.get("content")
            if content:
                self.go_imports.append(content)


def _validate_vanity_url(url: str) -> None:
    """Ensure a vanity fetch or redirect URL is HTTPS to a public-looking DNS name without credentials or ports."""
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise ValueError(
            f"Disallowed whitespace or control character in vanity URL: {url}"
        )
    parsed = urlparse(url)
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or "%" in hostname
        or parsed.username is not None
    ):
        raise ValueError(f"Disallowed vanity URL: {url}")
    if parsed.port is not None:
        raise ValueError(f"Explicit port disallowed in vanity URL: {url}")
    normalized_host = hostname.removesuffix(".")
    labels = normalized_host.split(".")
    if len(labels) < 2 or not all(labels) or normalized_host.endswith(".localhost"):
        raise ValueError(f"Disallowed vanity URL: {url}")
    try:
        ipaddress.ip_address(normalized_host)
    except ValueError:
        pass
    else:
        raise ValueError(f"IP literal disallowed in vanity URL: {url}")
    tld = labels[-1]
    if not (tld.isascii() and (tld.isalpha() or tld.startswith("xn--"))):
        raise ValueError(f"Numeric or non-public host disallowed in vanity URL: {url}")


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.scope_id is not None:
            return False
        if addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        elif addr in _NAT64_WELL_KNOWN_PREFIX:
            addr = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return addr.is_global and not addr.is_multicast and not addr.is_reserved


def _is_resolvable_vanity_path(module_path: str) -> bool:
    """Return True if module_path looks like a public remote Go vanity import path."""
    url = f"https://{module_path}"
    try:
        _validate_vanity_url(url)
        parsed = urlparse(url)
    except ValueError:
        return False
    return not parsed.query and not parsed.fragment


def _validate_github_repo_root(repo_root: str) -> str | None:
    """Validate and normalize a GitHub HTTPS repository root URL from a go-import tag."""
    try:
        parsed = urlparse(repo_root)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        if parsed.port is not None:
            return None
    except ValueError:
        return None
    repo_path = parsed.path.strip("/").removesuffix(".git")
    segments = repo_path.split("/")
    if len(segments) != 2:
        return None
    owner, repo = segments
    if not repo or any(
        part.startswith("-") or part in (".", "..") for part in (owner, repo)
    ):
        return None
    return f"https://github.com/{owner}/{repo}"


def _extract_github_repo_from_go_import(
    html: str, module_path: str
) -> tuple[str, str] | None:
    """Parse go-import meta tags and return (prefix, github_repo_url) for the longest match."""
    parser = _GoImportMetaParser()
    parser.feed(html)
    best_match: tuple[str, str] | None = None
    for content in parser.go_imports:
        tokens = content.split()
        if len(tokens) != 3:
            continue
        import_prefix, vcs, repo_root = tokens
        if vcs != "git":
            continue
        if module_path != import_prefix and not module_path.startswith(
            import_prefix + "/"
        ):
            continue
        github_url = _validate_github_repo_root(repo_root)
        if github_url is None:
            continue
        if best_match is None or len(import_prefix) > len(best_match[0]):
            best_match = (import_prefix, github_url)
    return best_match


class GoPkgMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        project_scope: ProjectScope,
        local_project_path: str | None = None,
        single_module: bool = False,
    ) -> None:
        self.local_project_path = local_project_path
        self.source_code_manager = source_code_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT
        self.only_transitive_dependencies = (
            project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
        )
        self.single_module = single_module
        self._head_branch_cache: dict[str, str] = {}
        self._vanity_import_cache: dict[str, str | None] = {}
        self._vanity_prefix_cache: dict[str, str | None] = {}

        if local_project_path is not None:
            # In go-package mode, top_package is a Go import path, not a URL
            self.top_package = top_package
        else:
            # Resolve canonical URL if this is a GitHub repository
            canonical_url, _ = source_code_manager.get_canonical_urls(top_package)
            self.top_package = canonical_url if canonical_url else top_package

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        if self.local_project_path is not None:
            return self._augment_metadata_from_local_path(metadata)

        # Get the source code directory
        source_code_ref = self.source_code_manager.get_code(self.top_package)

        # Walk through the directory to find go.mod files
        if not source_code_ref:
            return metadata
        if self.single_module:
            return self._augment_metadata_from_single_module(
                metadata, source_code_ref.local_full_path
            )
        for root, _, files in walk_directory(source_code_ref.local_full_path):
            if "go.mod" in files:
                if self._is_example_package(root):
                    continue
                module_data_list = self._run_go_list_modules(root)
                for module_data in module_data_list:
                    module_path = module_data["Path"]

                    if self.only_root_project:
                        if not any(meta.name == module_path for meta in metadata):
                            continue

                    self._upsert_metadata(metadata, module_data)

        return metadata

    def _augment_metadata_from_single_module(
        self, metadata: list[Metadata], module_dir: str
    ) -> list[Metadata]:
        """Collect only the Go module whose go.mod is in module_dir.

        Nested modules are not walked and any enclosing go.work is ignored:
        consumers of the published module resolve its own go.mod only.
        """
        if not path_exists(path_join(module_dir, "go.mod")):
            logger.warning(
                "Single Go module mode: no go.mod in %s, skipping Go module collection.",
                module_dir,
            )
            return metadata
        for module_data in self._run_go_list_modules(
            module_dir, disable_workspace=True
        ):
            if self.only_transitive_dependencies and module_data.get("Main"):
                continue
            if self.only_root_project and not any(
                meta.name == module_data["Path"] for meta in metadata
            ):
                continue
            self._upsert_metadata(metadata, module_data)
        return metadata

    def _augment_metadata_from_local_path(
        self, metadata: list[Metadata]
    ) -> list[Metadata]:
        """Handle augment_metadata when local_project_path is set (go-package mode).

        In this mode, the local_project_path contains a synthetic Go project with
        go.mod generated by GoPackageResolver. We skip get_code() and run
        go list -json all directly in the local project directory to enumerate
        all modules in the dependency graph (including transitive dependencies).
        """
        # Capture root package names before removing the seed entry, so that
        # only_root_project filtering still includes the root package.
        # Strip @version suffixes (e.g. "github.com/foo/bar@v1.0" -> "github.com/foo/bar")
        # so that module paths from go list (which never include @version) can be matched.
        root_package_names = {
            m.name.split("@")[0] for m in metadata if m.name is not None
        }

        # Remove the seed entry created by the collector
        metadata = [
            m
            for m in metadata
            if not (m.name == self.top_package and m.version is None)
        ]
        project_path = self.local_project_path
        if project_path is None:
            raise ValueError(
                "local_project_path must be set before calling this method"
            )

        module_data_list = self._run_go_list_modules(project_path)
        if module_data_list and all(
            module_data["Path"] == SYNTHETIC_MODULE_NAME
            for module_data in module_data_list
        ):
            # The resolver fell back to module-graph resolution (the resolved
            # import path is a module without an importable root package), so
            # there are no imported dependency packages to walk. Enumerate the
            # transitive dependency closure at the module level instead.
            # An empty listing is not a fallback signal: it means `go list`
            # itself failed, which is handled by the early return below.
            module_data_list = self._run_go_module_graph(project_path)
        if not module_data_list:
            return metadata

        for module_data in module_data_list:
            module_path = module_data["Path"]

            # Filter out the synthetic module (Main module)
            if module_path == SYNTHETIC_MODULE_NAME:
                continue

            if self.only_root_project:
                # Include the module if it is an exact match OR if the requested
                # spec is a subpackage path within the module (e.g. the seed name
                # "github.com/foo/bar/assert" maps to module "github.com/foo/bar").
                # The prefix check must not cross major-version boundaries: for a
                # seed like "github.com/org/lib/v2/foo", "github.com/org/lib" is
                # a different module and must NOT match even though it is a prefix.
                if not any(
                    name == module_path
                    or (
                        name.startswith(module_path + "/")
                        and not re.match(r"v\d+(/|$)", name[len(module_path) + 1 :])
                    )
                    for name in root_package_names
                ):
                    continue

            self._upsert_metadata(metadata, module_data)

        return metadata

    def _run_go_list_modules(
        self, project_path: str, disable_workspace: bool = False
    ) -> list[dict[str, Any]]:
        """Run go list -json all and return deduplicated module dicts.

        Parses package-level output and extracts unique modules from the
        nested Module key, skipping stdlib packages (no Module key).
        When disable_workspace is set, any enclosing go.work is ignored.
        """
        env = {"GOTOOLCHAIN": "auto"}
        if disable_workspace:
            env["GOWORK"] = "off"
        output = output_from_command(
            ["go", "list", "-json", "all"],
            cwd=project_path,
            env=env,
        )
        if not output.strip():
            logger.warning("go list produced no output in %s", project_path)
            return []

        corrected_output = "[{}]".format(output.replace("}\n{", "},\n{"))
        package_data_list: list[dict[str, Any]] = json.loads(corrected_output)

        seen_modules: dict[str, dict[str, Any]] = {}
        for package_data in package_data_list:
            if "Module" not in package_data:
                continue
            module = package_data["Module"]
            module_path = module["Path"]
            if module_path not in seen_modules:
                seen_modules[module_path] = module

        return list(seen_modules.values())

    def _run_go_module_graph(self, project_path: str) -> list[dict[str, Any]]:
        """Run go list -m -json all and return deduplicated module dicts.

        Used in module-graph fallback mode (the resolved project has no
        importable dependency packages): the module graph provides the
        transitive dependency closure at the module level. The synthetic main
        module is filtered out; every remaining entry is already shaped like a
        module dict (Path, Version, and optionally Dir).
        """
        output = output_from_command(
            ["go", "list", "-m", "-json", "all"],
            cwd=project_path,
            env={"GOTOOLCHAIN": "auto"},
        )
        if not output.strip():
            logger.warning("go list -m produced no output in %s", project_path)
            return []

        # go list -m -json emits consecutive JSON objects (no array wrapper or
        # separators); stitch them into a JSON array so json.loads can parse it.
        corrected_output = "[{}]".format(output.replace("}\n{", "},\n{"))
        module_data_list: list[dict[str, Any]] = json.loads(corrected_output)

        seen_modules: dict[str, dict[str, Any]] = {}
        for module_data in module_data_list:
            module_path = module_data["Path"]
            if module_path == SYNTHETIC_MODULE_NAME:
                continue
            if module_path not in seen_modules:
                seen_modules[module_path] = module_data

        return list(seen_modules.values())

    def _upsert_metadata(
        self, metadata: list[Metadata], module_data: dict[str, Any]
    ) -> None:
        """Add or update a metadata entry from a go list module dict."""
        module_path = module_data["Path"]
        version = module_data.get("Version")

        module_metadata = Metadata(
            name=module_path,
            origin=self._translate_github_path(module_path),
            local_src_path=module_data.get("Dir") or None,
            license=[],
            version=version,
            copyright=[],
        )

        for i, meta in enumerate(metadata):
            if meta.name == module_metadata.name:
                metadata[i].origin = module_metadata.origin
                metadata[i].local_src_path = module_metadata.local_src_path
                metadata[i].version = (
                    module_metadata.version
                    if module_metadata.version is not None
                    else metadata[i].version
                )
                return
        metadata.append(module_metadata)

    def _fetch_go_import_match(self, path: str) -> tuple[str, str] | None:
        url = f"https://{path}?go-get=1"
        try:
            status, raw_html = fetch_bounded_validated(
                url,
                max_bytes=_VANITY_MAX_RESPONSE_BYTES,
                url_validator=_validate_vanity_url,
                ip_validator=_is_public_ip,
            )
            # Like `go get`, honor go-import tags in non-2xx responses (some hosts serve
            # discovery metadata with HTTP 404); the status only matters when none match.
            match = _extract_github_repo_from_go_import(
                raw_html.decode(errors="replace"), path
            )
        except (OSError, ValueError) as e:
            logger.debug(
                "Could not resolve Go vanity import for %s: %s",
                path,
                e,
            )
            return None
        if match is None and status >= 400:
            logger.debug(
                "Could not resolve Go vanity import for %s: HTTP %s",
                path,
                status,
            )
        return match

    def _resolve_vanity_import(self, module_path: str) -> str | None:
        """Resolve a non-GitHub Go vanity module path via ?go-get=1 to a GitHub repo URL."""
        if module_path in self._vanity_import_cache:
            return self._vanity_import_cache[module_path]

        if not _is_resolvable_vanity_path(module_path):
            return None

        match = self._fetch_go_import_match(module_path)
        if match is None:
            self._vanity_import_cache[module_path] = None
            return None

        import_prefix, github_url = match
        if import_prefix != module_path:
            if import_prefix not in self._vanity_prefix_cache:
                prefix_match = self._fetch_go_import_match(import_prefix)
                self._vanity_prefix_cache[import_prefix] = (
                    prefix_match[1]
                    if prefix_match is not None and prefix_match[0] == import_prefix
                    else None
                )
            if self._vanity_prefix_cache[import_prefix] != github_url:
                self._vanity_import_cache[module_path] = None
                return None

        self._vanity_import_cache[module_path] = github_url
        return github_url

    def _translate_github_path(self, path: str) -> str:
        if not path.startswith("github.com"):
            resolved = self._resolve_vanity_import(path)
            if resolved is not None:
                return resolved
            return f"https://{path}"
        parts = path.split("/", 3)
        if len(parts) > 3:
            # GoPkg has no info about what branch was used, assuming the HEAD.
            # Use branch cache initialized in constructor
            repo_url = f"https://{parts[0]}/{parts[1]}/{parts[2]}"
            if repo_url not in self._head_branch_cache:
                try:
                    ls_remote_output = output_from_command(
                        ["git", "ls-remote", "--symref", repo_url, "HEAD"]
                    )
                    tokens = ls_remote_output.split()
                    if len(tokens) >= 2:
                        self._head_branch_cache[repo_url] = tokens[1].removeprefix(
                            "refs/heads/"
                        )
                    else:
                        logger.warning("Could not detect HEAD branch for %s", repo_url)
                        self._head_branch_cache[repo_url] = ""
                except OSError:
                    logger.warning(
                        "git ls-remote failed for %s, skipping branch detection",
                        repo_url,
                    )
                    self._head_branch_cache[repo_url] = ""
            branch = self._head_branch_cache[repo_url]
            if branch:
                return f"{repo_url}/tree/{branch}/{parts[3]}"
            return repo_url
        return f"https://{path}"

    def _is_example_package(self, go_mod_path: str) -> bool:
        # a module is an example, if the name ends with /examples and requires the main module
        module_name = None
        requires_main_module = False

        file = open_file(f"{go_mod_path}/go.mod")

        if not file:
            return False
        for line in file.splitlines():
            line = line.strip()
            module_match = re.match(r"^module\s+(\S+)", line)
            if module_match:
                module_name = module_match.group(1)
            require_match = re.match(r"^require\s+(\S+)\s+v[\d\.]+", line)
            if require_match:
                required_module = require_match.group(1)
                # Check if required module is a parent module
                if module_name and required_module in module_name:
                    requires_main_module = True

        # The module name should end with /examples and require the main module
        return bool(
            module_name and module_name.endswith("/examples") and requires_main_module
        )
