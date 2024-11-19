import http.client
import os
import re
from shlex import quote
import sys
import tempfile

from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def change_directory(dir_name: str) -> None:
    os.chdir(dir_name)


def get_current_working_directory() -> str:
    return os.getcwd()


class GoLicensesMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self, repository_url: str) -> None:
        self.purl_parser = PurlParser()
        # create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # in the temporary directory make a shallow clone of the repository
            result = os.system(
                "git clone --depth 1 {} {}".format(
                    quote(repository_url), quote(temp_dir)
                )
            )
            if result != 0:
                raise ValueError(f"Failed to clone repository: {repository_url}")
            # setting up go licenses
            cwd = get_current_working_directory()
            change_directory(temp_dir)
            os.system("go mod download")
            os.system("go mod vendor")
            os.system("go-licenses csv . > licenses.csv")
            # read the licenses from the csv file to a list
            with open("licenses.csv", "r") as file:
                self.go_licenses = file.readlines()
                change_directory(cwd)

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        if not self.go_licenses:
            # rename packages with no metadata associated that start with go:
            for package in metadata:
                if (
                    not package.origin
                    and package.name is not None
                    and package.name.startswith("go:")
                ):
                    package.origin = self.__infer_origin_heuristic(
                        package.name.replace("go:", "")
                    )
                updated_metadata.append(package)
            return updated_metadata
        # so far we do not have an example package where we can get the license from go-licenses
        # dd-trace-go, datado-agent, strauss-red-team, all return: build constraints exclude all Go files in ...
        # we will revisit when we find a package that works with it or after making those work with go-licenses
        raise NotImplementedError(
            "GoLicensesMetadataCollectionStrategy.augment_metadata is not implemented"
        )

    def __infer_origin_heuristic(self, package_name: str) -> str:
        # we may be able to infer the origin from the package name by scraping information from websites
        # starting at the one referenced in the name of the package.

        # check if the package is a github package
        owner, repo = self.purl_parser.get_github_owner_and_repo(package_name)
        if owner is None or repo is None:
            return package_name
        # check if the package is a gitlab package
        owner, repo = self.purl_parser.get_gitlab_owner_and_repo(package_name)
        if owner is None or repo is None:
            return package_name
        # remove protocol from the package name and break domain from path
        if "://" in package_name:
            url = package_name.split("://")[1]
        else:
            url = package_name
        domain = url.split("/")[0]
        path = url.replace(domain, "")

        # open connection to the website
        conn = http.client.HTTPSConnection(domain)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            # deal with redirections
            while response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if location is None:
                    raise ValueError(
                        f"Redirection status {response.status} without location header"
                    )
                if location.startswith("/"):
                    conn = http.client.HTTPSConnection(domain)
                    path = location
                else:
                    match = re.match(r"https?://([^/]+)(/.*)", location)
                    if match:
                        domain, path = match.groups()
                        conn = http.client.HTTPSConnection(domain)
                conn.request("GET", path)
                response = conn.getresponse()
            if response.status == 200:
                repo_info = response.read().decode("utf-8")
                # deal with the potential html-redirection inside the website
                if 'http-equiv="refresh"' in repo_info:
                    # an example to match would be: <meta http-equiv="refresh" content="0; url=https://pkg.go.dev/go-simpler.org/musttag"
                    match = re.search(
                        r'<meta http-equiv="refresh" content="0; url=(https://[^"]+)"',
                        repo_info,
                    )
                    if match:
                        new_url = match.group(1)
                        return self.__infer_origin_heuristic(new_url)
                    return package_name

                # try to match UnitMeta-repo class tag a
                match = re.search(
                    r'<div class="UnitMeta-repo">\s*<a href="([^"]+)"', repo_info
                )
                if match:
                    new_url = match.group(1)
                    return self.__infer_origin_heuristic(new_url)

                # try to match go-import meta tag
                match = re.search(
                    r'<meta name="go-import" content="[^ ]+ git (http.+)">', repo_info
                )
                if match:
                    new_url = match.group(1)
                    return self.__infer_origin_heuristic(new_url)

                # try to match Source Code labeled links
                match = re.search(
                    r'<a class="btn btn-lg btn-info" href="([^"]+)"[^>]*>.*?Source Code.*?</a>',
                    repo_info,
                    re.DOTALL,
                )
                if match:
                    new_url = match.group(1)
                    return self.__infer_origin_heuristic(new_url)
        except http.client.HTTPException as e:
            print(
                f"SSL verification failed for {domain}{path} skipping the request: {e}",
                file=sys.stderr,
            )
        return package_name
