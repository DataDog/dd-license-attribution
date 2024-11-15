import os
from unittest.mock import Mock, call, mock_open, patch

import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy import (
    GoLicensesMetadataCollectionStrategy,
)


def test_go_licenses_collection_strategy_clones_and_run_go_license_on_init(mocker):
    # Todo: This test doesn't check that the calls to os.system are executed in the right directory
    # We need to validate the chroot is called before the first call to os.system and after the last call to os.system
    # I couldn't find a way to do this with the current implementation, we need to revisit this test to harden it.

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    temp_dir_object.__enter__ = mocker.Mock(return_value=temp_dir_object)
    temp_dir_object.__exit__ = mocker.Mock(return_value=None)
    temp_dir_mock = mocker.patch(
        "tempfile.TemporaryDirectory", return_value=temp_dir_object
    )

    system_mock = mocker.patch("os.system", return_value=0)

    get_cwd_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.get_current_working_directory",
        return_value="test_cwd",
    )
    chdir_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.change_directory"
    )

    mock_csv_file_content = "test_line1\ntest_line2\n"
    mock_open_obj = mock_open(read_data=mock_csv_file_content)
    with patch("builtins.open", mock_open_obj):
        strategy = GoLicensesMetadataCollectionStrategy("test_purl")

    # assert that the temporary directory was created
    temp_dir_mock.assert_called_once_with()
    # assert that the repository was cloned and setup
    system_mock.assert_has_calls(
        [
            call("git clone --depth 1 test_purl test_temp_dir"),
            call("go mod download"),
            call("go mod vendor"),
            call("go-licenses csv . > licenses.csv"),
        ]
    )
    # assert that the licenses were read from the csv file
    mock_open_obj.assert_called_once_with("licenses.csv", "r")

    # assert that the cwd was changed before setting up go licenses and set back to the cwd afterwards
    get_cwd_mock.assert_called_once()
    chdir_mock.assert_has_calls([call("test_temp_dir"), call("test_cwd")])

    # assert that the file was open and completely read
    mock_open_obj.assert_called_once_with("licenses.csv", "r")
    assert strategy.go_licenses == ["test_line1\n", "test_line2\n"]


def test_go_licenses_collection_strategy_failing_clone_raises_exception(mocker):
    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    temp_dir_object.__enter__ = mocker.Mock(return_value=temp_dir_object)
    temp_dir_object.__exit__ = mocker.Mock(return_value=None)
    temp_dir_mock = mocker.patch(
        "tempfile.TemporaryDirectory", return_value=temp_dir_object
    )

    system_mock = mocker.patch("os.system", return_value=1)

    with pytest.raises(ValueError, match="Failed to clone repository: test_purl"):
        GoLicensesMetadataCollectionStrategy("test_purl")

    temp_dir_mock.assert_called_once_with()
    system_mock.assert_called_once_with("git clone --depth 1 test_purl test_temp_dir")


def test_go_licenses_collection_strategy_do_not_miss_or_replace_non_go_packages(mocker):
    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    temp_dir_object.__enter__ = mocker.Mock(return_value=temp_dir_object)
    temp_dir_object.__exit__ = mocker.Mock(return_value=None)
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    mocker.patch("os.system", return_value=0)
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.get_current_working_directory",
        return_value="test_cwd",
    )
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.change_directory"
    )

    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.get_current_working_directory",
        return_value="test_cwd",
    )
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy.change_directory"
    )

    mock_open_obj = mock_open(read_data="")
    with patch("builtins.open", mock_open_obj):
        strategy = GoLicensesMetadataCollectionStrategy("test_purl")

    initial_metadata = [
        Metadata(
            name="go:package1",
            version="1.0",
            origin="test_purl",  # should be skipped because has origin
            license=None,
            copyright=None,
        ),
        Metadata(
            name="non_go_package1",  # should be skipped because doesn't start with go:
            version=None,
            origin=None,
            license=None,
            copyright=None,
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == initial_metadata
