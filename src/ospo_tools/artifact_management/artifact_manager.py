from ospo_tools.adaptors.datetime import get_datetime_now
from ospo_tools.adaptors.os import path_exists
from ospo_tools.adaptors.os import list_dir
from datetime import datetime
import pytz


def validate_cache_dir(local_cache_dir: str) -> bool:
    for time_copy_str in list_dir(local_cache_dir):
        try:
            datetime.strptime(time_copy_str, "%Y%m%d_%H%M%SZ").replace(tzinfo=pytz.UTC)
        except ValueError:
            return False
    return True


class ArtifactManager:
    def __init__(self, local_cache_dir: str, local_cache_ttl: int = 86400) -> None:
        self.local_cache_dir = local_cache_dir
        self.local_cache_ttl = local_cache_ttl
        self.setup_time = get_datetime_now()
        self.timestamped_dir = self.setup_time.strftime("%Y%m%d_%H%M%SZ")
        # validate the cache dir is a directory with only expected subdirectories
        if not path_exists(local_cache_dir):
            raise ValueError(f"Local cache directory {local_cache_dir} does not exist")
        if not validate_cache_dir(local_cache_dir):
            raise ValueError(
                f"Local cache directory {local_cache_dir} has invalid subdirectory, are you sure it is a cache directory?"
            )
