"""This is a collection of tools to transform purls from different format and extract/validate parts of them"""

import re


class PurlParser:
    def __init__(self):
        pass

    def get_github_owner_and_repo(self, purl):
        # remove protocol from purl
        if "://" in purl:
            purl = purl.split("://")[1]
        # Regular expression to match GitHub URLs and extract owner and repo
        match = re.match(r"^github\.com/([^/]+)/([^/]+)", purl)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def get_gitlab_owner_and_repo(self, purl):
        # remove protocol from purl
        if "://" in purl:
            purl = purl.split("://")[1]
        # Regular expression to match GitLab URLs and extract owner and repo
        match = re.match(r"^gitlab\.com/([^/]+)/([^/]+)", purl)
        if match:
            return match.group(1), match.group(2)
        return None, None
