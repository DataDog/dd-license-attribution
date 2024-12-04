"""This is a collection of tools to transform purls from different format and
   extract/validate parts of them"""

import re


class PurlParser:
    def __init__(self) -> None:
        pass

    def get_github_owner_repo_path(
        self, purl: str | None
    ) -> tuple[str | None, str | None, str | None]:
        if purl is None:
            return None, None, None
        # remove protocol from purl
        if "://" in purl:
            purl = purl.split("://")[1]
        # remove version from purl if it is available
        if "@" in purl:
            purl = purl.split("@")[0]
        # Regular expression to match GitHub URLs and extract owner and repo
        match = re.match(r"^github\.com/([^/]+)/([^/]+)(.*)", purl)
        if match:
            return match.group(1), match.group(2), match.group(3)
        return None, None, None

    def get_gitlab_owner_repo_path(
        self, purl: str | None
    ) -> tuple[str | None, str | None, str | None]:
        if purl is None:
            return None, None, None
        # remove protocol from purl
        if "://" in purl:
            purl = purl.split("://")[1]
        # remove version from purl if it is available
        if "@" in purl:
            purl = purl.split("@")[0]
        # Regular expression to match GitLab URLs and extract owner and repo
        match = re.match(r"^gitlab\.com/([^/]+)/([^/]+)(.*)", purl)
        if match:
            return match.group(1), match.group(2), match.group(3)
        return None, None, None
