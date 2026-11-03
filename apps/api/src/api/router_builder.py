from typing import Self

from fastapi import APIRouter

DEFAULT_API_PREFIX: str = "/api/"


def _normalize_prefix(prefix: str | None) -> str:
    if prefix is None:
        return ""

    segments = [seg for seg in prefix.split("/") if seg]
    return "/" + "/".join(segments) if segments else ""


class ApiRouterBuilder:
    def __init__(self) -> None:
        self.clear()

    def clear(self) -> Self:
        self.prefix(DEFAULT_API_PREFIX)
        self._version = ""
        self._tags: list[str] = []
        return self

    def prefix(self, prefix: str) -> Self:
        self._prefix = _normalize_prefix(prefix)
        return self

    def version(self, version: str) -> Self:
        if self._version != version and self._version in self._tags:
            self._tags.remove(self._version)

        self._version = version
        if version not in self._tags:
            self._tags.append(version)
        return self

    def tags(self, tags: list[str]) -> Self:
        self._tags = tags.copy()
        return self

    def add_tags(self, tags: list[str]) -> Self:
        self._tags += tags
        return self

    def build(self) -> APIRouter:
        prefix = f"{self._prefix}{_normalize_prefix(self._version)}"
        return APIRouter(prefix=prefix, tags=[*self._tags])
