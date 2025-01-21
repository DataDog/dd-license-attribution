from typer.testing import CliRunner

from ospo_tools.cli.get_licenses_copyrights import app

runner = CliRunner(mix_stderr=False)


def test_basic_run() -> None:
    result = runner.invoke(app, ["test", "--no-gh-auth"], color=False)
    assert result.exit_code == 0


def test_no_github_auth() -> None:
    result = runner.invoke(app, ["test"], color=False)
    assert result.exit_code == 2
    assert "No Github token available" in result.stderr


def test_github_auth_param() -> None:
    result = runner.invoke(app, ["test", "--github-token=12345"], color=False)
    assert result.exit_code == 0


def test_github_auth_env() -> None:
    result = runner.invoke(app, ["test"], env={"GITHUB_TOKEN": "12345"}, color=False)
    assert result.exit_code == 0


def test_missing_package() -> None:
    result = runner.invoke(app, color=False)
    assert result.exit_code == 2
    assert "Missing argument 'PACKAGE'." in result.stderr


def test_cache_ttl_without_cache_dir() -> None:
    result = runner.invoke(app, ["test", "--cache-ttl=10"], color=False)
    assert result.exit_code == 2
    assert "Invalid value for '--cache-ttl'" in result.stderr


def test_transitive_root_same_time() -> None:
    result = runner.invoke(
        app,
        ["test", "--only-transitive-dependencies", "--only-root-project"],
        color=False,
    )
    assert result.exit_code == 2
    assert "Invalid value for '--only-root-project'" in result.stderr
