import pytest
from fastapi import APIRouter


def ApiRouterBuilder():
    from api.router_builder import ApiRouterBuilder

    return ApiRouterBuilder()


def test_default():
    router: APIRouter = ApiRouterBuilder().build()
    assert isinstance(router, APIRouter)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("//v1//", "/api/v1"),
        ("v2", "/api/v2"),
    ],
)
def test_version(version: str, expected: str):
    router: APIRouter = ApiRouterBuilder().version(version).build()
    assert router.prefix == expected


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("api", "/api"),
        ("/api", "/api"),
        ("/ipa", "/ipa"),
        ("ipa////", "/ipa"),
        ("////api/", "/api"),
    ],
)
def test_prefix(prefix: str, expected: str):
    router: APIRouter = ApiRouterBuilder().prefix(prefix).build()
    assert router.prefix == expected


@pytest.mark.parametrize(
    ("prefix", "version", "expected"),
    [
        ("asd//", "v1", "/asd/v1"),
        ("//asd", "v1", "/asd/v1"),
        ("//asd//", "v1", "/asd/v1"),
        ("//api//nested//", "v1", "/api/nested/v1"),
        ("health", "", "/health"),
        ("/", "", ""),
        ("", None, ""),
        (None, "v1", "/v1"),
    ],
)
def test_prefix_version(prefix: str, version: str, expected: str):
    router: APIRouter = ApiRouterBuilder().prefix(prefix).version(version).build()
    assert router.prefix == expected


def test_tags():
    router: APIRouter = (
        ApiRouterBuilder()
        .tags(["knowledge"])
        .version("v1")
        .add_tags(["search"])
        .version("v1")
        .version("v1")
        .build()
    )
    assert all(t in router.tags for t in ["knowledge", "search", "v1"])

    router = ApiRouterBuilder().version("v1").version("v2").build()
    assert router.tags == ["v2"]


def test_tags_do_not_modify_by_ref():
    original: list[str] = ["knowledge"]
    _ = ApiRouterBuilder().tags(original).add_tags(["search"]).version("v1").build()
    assert original == ["knowledge"]


def test_clear():
    router: APIRouter = (
        ApiRouterBuilder().prefix("testpref").version("asdfg").clear().build()
    )
    assert not router.tags
    assert "testpref" not in router.prefix
    assert "asdfg" not in router.prefix
