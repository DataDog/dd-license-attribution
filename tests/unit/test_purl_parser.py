# using pytest write a test that will check what happens when calling the get_github_owner_and_repo method with the following inputs: with None

from ospo_tools.metadata_collector.purl_parser import PurlParser

import pytest


def test_get_github_owner_and_repo_with_none_as_input():
    purl_parser = PurlParser()
    owner, repo = purl_parser.get_github_owner_and_repo(None)
    assert owner == None
    assert repo == None
