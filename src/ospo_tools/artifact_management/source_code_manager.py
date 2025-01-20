from dataclasses import dataclass
import os
from datetime import datetime
from giturlparse import parse as parse_git_url
import pytz


@dataclass
class SourceCodeReference:
    repo_url: str
    branch: str
    local_root_path: str
    local_full_path: str


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def run_command(command: str) -> int:
    return os.system(command)


def get_datetime_now() -> datetime:
    return datetime.now(pytz.UTC)


def path_exists(file_path: str) -> bool:
    return os.path.exists(file_path)


def create_dirs(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def extract_ref(ref: str, url: str) -> str:
    split_ref = ref.split("/")
    for i in range(len(split_ref)):
        ref_guess = "/".join(split_ref[: i + 1])
        validated = run_command(
            f"git ls-remote {url} {ref_guess} | grep -q {ref_guess}"
        )
        if validated == 0:
            return ref_guess
    if len(split_ref) > 0:  # may be a hash
        validated = run_command(f"git ls-remote {url} | grep -q {split_ref[0]}")
        if validated == 0:
            return split_ref[0]
    return ""


def output_from_command(command: str) -> str:
    return os.popen(command).read()


class SourceCodeManager:
    def __init__(self, local_cache_dir: str, local_cache_ttl: int = 86400) -> None:
        self.local_cache_dir = local_cache_dir
        self.local_cache_ttl = local_cache_ttl
        self.setup_time = get_datetime_now()
        # validate the cache dir is a directory with only expected subdirectories
        if not path_exists(local_cache_dir):
            raise ValueError(f"Local cache directory {local_cache_dir} does not exist")
        for time_copy_str in list_dir(local_cache_dir):
            try:
                datetime.strptime(time_copy_str, "%Y%m%d_%H%M%SZ").replace(
                    tzinfo=pytz.UTC
                )
            except ValueError:
                raise ValueError(
                    f"Local cache directory {local_cache_dir} has invalid subdirectory {time_copy_str}, are you sure it is a cache directory?"
                )

    def get_code(
        self, resource_url: str, force_update: bool = False
    ) -> SourceCodeReference | None:
        parsed_url = parse_git_url(resource_url)
        if not parsed_url.valid:
            return None
        if not parsed_url.github:  # Only GitHub supported for now
            return None
        owner = parsed_url.owner
        repo = parsed_url.repo
        repository_url = f"{parsed_url.protocol}://{parsed_url.host}/{parsed_url.owner}/{parsed_url.repo}"
        branch = "default_branch"
        if parsed_url.branch:
            # branches are guessed from url, and may fail to be correct specially on tags and branches with slashes
            validated_ref = extract_ref(parsed_url.branch, repository_url)
            if validated_ref != "":
                branch = validated_ref
        if parsed_url.path_raw.startswith("/tree/"):
            path = parsed_url.path_raw.removeprefix(f"/tree/{branch}")
        elif parsed_url.path_raw.startswith("/blob/"):
            path = "/".join(parsed_url.path_raw.removeprefix("/blob/").split("/")[:-1])
            validated_ref = extract_ref(path, repository_url)
            if validated_ref != "":
                branch = validated_ref
                path = path.removeprefix(f"{branch}")
        else:
            path = ""
        if branch == "default_branch":
            branch = (
                output_from_command(f"git ls-remote --symref {repository_url} HEAD")
                .split()[1]
                .removeprefix("refs/heads/")
            )
        cached_timestamps = list_dir(self.local_cache_dir)
        cached_timestamps.sort(reverse=True)
        if not force_update:
            # check if there is a cache
            for time_copy_str in cached_timestamps:
                time_copy = datetime.strptime(time_copy_str, "%Y%m%d_%H%M%SZ").replace(
                    tzinfo=pytz.UTC
                )
                if (self.setup_time - time_copy).total_seconds() > self.local_cache_ttl:
                    break
                local_branch_path = (
                    f"{self.local_cache_dir}/{time_copy_str}/{owner}-{repo}/{branch}"
                )
                if path_exists(local_branch_path):
                    return SourceCodeReference(
                        repo_url=repository_url,
                        branch=branch,
                        local_root_path=f"{local_branch_path}",
                        local_full_path=f"{local_branch_path}{path}",
                    )
        # we need to clone
        current_time = get_datetime_now()
        current_time_str = current_time.strftime("%Y%m%d_%H%M%SZ")
        local_branch_path = (
            f"{self.local_cache_dir}/{current_time_str}/{owner}-{repo}/{branch}"
        )

        create_dirs(local_branch_path)
        run_command(
            f"git clone -c advice.detachedHead=False --depth 1 --branch={branch} {repository_url} {local_branch_path}"
        )

        return SourceCodeReference(
            repo_url=repository_url,
            branch=branch,
            local_root_path=f"{local_branch_path}",
            local_full_path=f"{local_branch_path}{path}",
        )
