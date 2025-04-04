# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dataclasses import dataclass
from datetime import datetime

import pytz

from dd_license_attribution.adaptors.datetime import get_datetime_now
from dd_license_attribution.adaptors.os import list_dir, path_exists


def validate_cache_dir(local_cache_dir: str) -> bool:
    for time_copy_str in list_dir(local_cache_dir):
        try:
            datetime.strptime(time_copy_str, "%Y%m%d_%H%M%SZ").replace(tzinfo=pytz.UTC)
        except ValueError:
            return False
    return True


@dataclass
class SourceCodeReference:
    repo_url: str
    branch: str
    local_root_path: str
    local_full_path: str


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
