from enum import Enum


class ProjectScope(Enum):
    ONLY_ROOT_PROJECT = "Only Root Project"
    ONLY_TRANSITIVE_DEPENDENCIES = "Only Transitive Dependencies"
    ALL = "All"
