# type: ignore
import gzip
from socket import socket
from typing import Any
from unittest import mock

import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

import aiohttp
from aiohttp import web
from aiohttp.test_utils import (
    AioHTTPTestCase,
    RawTestServer as _RawTestServer,
    TestClient as _TestClient,
    TestServer as _TestServer,
    get_port_socket,
    loop_context,
    make_mocked_request,
)

_hello_world_str = "Hello, world"
_hello_world_bytes = _hello_world_str.encode("utf-8")
_hello_world_gz = gzip.compress(_hello_world_bytes)


def _create_example_app():
    async def hello(request):
        return web.Response(body=_hello_world_bytes)

    async def websocket_handler(request):

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == "close":
                await ws.close()
            else:
                await ws.send_str(msg.data + "/answer")

        return ws

    async def cookie_handler(request):
        resp = web.Response(body=_hello_world_bytes)
        resp.set_cookie("cookie", "val")
        return resp

    app = web.Application()
    app.router.add_route("*", "/", hello)
    app.router.add_route("*", "/websocket", websocket_handler)
    app.router.add_route("*", "/cookie", cookie_handler)
    return app


# these exist to test the pytest scenario
@pytest.fixture
def loop() -> None:
    with loop_context() as loop:
        yield loop


@pytest.fixture
def app():
    return _create_example_app()


@pytest.fixture
def test_client(loop: Any, app: Any) -> None:
    async def make_client():
        return _TestClient(_TestServer(app))

    client = loop.run_until_complete(make_client())

    loop.run_until_complete(client.start_server())
    yield client
    loop.run_until_complete(client.close())


async def test_aiohttp_client_close_is_idempotent() -> None:
    # a test client, called multiple times, should
    # not attempt to close the server again.
    app = _create_example_app()
    client = _TestClient(_TestServer(app))
    await client.close()
    await client.close()


class TestAioHTTPTestCase(AioHTTPTestCase):
    def get_app(self):
        return _create_example_app()

    async def test_example_with_loop(self) -> None:
        request = await self.client.request("GET", "/")
        assert request.status == 200
        text = await request.text()
        assert _hello_world_str == text

    def test_inner_example(self) -> None:
        async def test_get_route() -> None:
            resp = await self.client.request("GET", "/")
            assert resp.status == 200
            text = await resp.text()
            assert _hello_world_str == text

        self.loop.run_until_complete(test_get_route())

    async def test_example_without_explicit_loop(self) -> None:
        request = await self.client.request("GET", "/")
        assert request.status == 200
        text = await request.text()
        assert _hello_world_str == text

    async def test_inner_example_without_explicit_loop(self) -> None:
        async def test_get_route() -> None:
            resp = await self.client.request("GET", "/")
            assert resp.status == 200
            text = await resp.text()
            assert _hello_world_str == text

        await test_get_route()


def test_get_route(loop: Any, test_client: Any) -> None:
    async def test_get_route() -> None:
        resp = await test_client.request("GET", "/")
        assert resp.status == 200
        text = await resp.text()
        assert _hello_world_str == text

    loop.run_until_complete(test_get_route())


async def test_client_websocket(loop: Any, test_client: Any) -> None:
    resp = await test_client.ws_connect("/websocket")
    await resp.send_str("foo")
    msg = await resp.receive()
    assert msg.type == aiohttp.WSMsgType.TEXT
    assert "foo" in msg.data
    await resp.send_str("close")
    msg = await resp.receive()
    assert msg.type == aiohttp.WSMsgType.CLOSE


async def test_client_cookie(loop: Any, test_client: Any) -> None:
    assert not test_client.session.cookie_jar
    await test_client.get("/cookie")
    cookies = list(test_client.session.cookie_jar)
    assert cookies[0].key == "cookie"
    assert cookies[0].value == "val"


@pytest.mark.parametrize(
    "method", ["get", "post", "options", "post", "put", "patch", "delete"]
)
async def test_test_client_methods(method: Any, loop: Any, test_client: Any) -> None:
    resp = await getattr(test_client, method)("/")
    assert resp.status == 200
    text = await resp.text()
    assert _hello_world_str == text


async def test_test_client_head(loop: Any, test_client: Any) -> None:
    resp = await test_client.head("/")
    assert resp.status == 200


@pytest.mark.parametrize("headers", [{"token": "x"}, CIMultiDict({"token": "x"}), {}])
def test_make_mocked_request(headers: Any) -> None:
    req = make_mocked_request("GET", "/", headers=headers)
    assert req.method == "GET"
    assert req.path == "/"
    assert isinstance(req, web.Request)
    assert isinstance(req.headers, CIMultiDictProxy)


def test_make_mocked_request_sslcontext() -> None:
    req = make_mocked_request("GET", "/")
    assert req.transport.get_extra_info("sslcontext") is None


def test_make_mocked_request_unknown_extra_info() -> None:
    req = make_mocked_request("GET", "/")
    assert req.transport.get_extra_info("unknown_extra_info") is None


def test_make_mocked_request_app() -> None:
    app = mock.Mock()
    req = make_mocked_request("GET", "/", app=app)
    assert req.app is app


def test_make_mocked_request_app_can_store_values() -> None:
    req = make_mocked_request("GET", "/")
    req.app["a_field"] = "a_value"
    assert req.app["a_field"] == "a_value"


def test_make_mocked_request_match_info() -> None:
    req = make_mocked_request("GET", "/", match_info={"a": "1", "b": "2"})
    assert req.match_info == {"a": "1", "b": "2"}


def test_make_mocked_request_content() -> None:
    payload = mock.Mock()
    req = make_mocked_request("GET", "/", payload=payload)
    assert req.content is payload


def test_make_mocked_request_transport() -> None:
    transport = mock.Mock()
    req = make_mocked_request("GET", "/", transport=transport)
    assert req.transport is transport


async def test_test_client_props() -> None:
    app = _create_example_app()
    server = _TestServer(app, scheme="http", host="127.0.0.1")
    client = _TestClient(server)
    assert client.scheme == "http"
    assert client.host == "127.0.0.1"
    assert client.port is None
    async with client:
        assert isinstance(client.port, int)
        assert client.server is not None
        assert client.app is not None
    assert client.port is None


async def test_test_client_raw_server_props() -> None:
    async def hello(request):
        return web.Response(body=_hello_world_bytes)

    server = _RawTestServer(hello, scheme="http", host="127.0.0.1")
    client = _TestClient(server)
    assert client.scheme == "http"
    assert client.host == "127.0.0.1"
    assert client.port is None
    async with client:
        assert isinstance(client.port, int)
        assert client.server is not None
        assert client.app is None
    assert client.port is None


async def test_test_server_context_manager(loop: Any) -> None:
    app = _create_example_app()
    async with _TestServer(app) as server:
        client = aiohttp.ClientSession()
        resp = await client.head(server.make_url("/"))
        assert resp.status == 200
        await resp.close()
        await client.close()


def test_client_unsupported_arg() -> None:
    with pytest.raises(TypeError) as e:
        _TestClient("string")

    assert (
        str(e.value) == "server must be TestServer instance, found type: <class 'str'>"
    )


async def test_server_make_url_yarl_compatibility(loop: Any) -> None:
    app = _create_example_app()
    async with _TestServer(app) as server:
        make_url = server.make_url
        assert make_url(URL("/foo")) == make_url("/foo")
        with pytest.raises(AssertionError):
            make_url("http://foo.com")
        with pytest.raises(AssertionError):
            make_url(URL("http://foo.com"))


def test_testcase_no_app(testdir: Any, loop: Any) -> None:
    testdir.makepyfile(
        """
        from aiohttp.test_utils import AioHTTPTestCase


        class InvalidTestCase(AioHTTPTestCase):
            def test_noop(self) -> None:
                pass
        """
    )
    result = testdir.runpytest()
    result.stdout.fnmatch_lines(["*RuntimeError*"])


async def test_server_context_manager(app: Any, loop: Any) -> None:
    async with _TestServer(app) as server:
        async with aiohttp.ClientSession() as client:
            async with client.head(server.make_url("/")) as resp:
                assert resp.status == 200


@pytest.mark.parametrize(
    "method", ["head", "get", "post", "options", "post", "put", "patch", "delete"]
)
async def test_client_context_manager_response(
    method: Any, app: Any, loop: Any
) -> None:
    async with _TestClient(_TestServer(app)) as client:
        async with getattr(client, method)("/") as resp:
            assert resp.status == 200
            if method != "head":
                text = await resp.text()
                assert "Hello, world" in text


async def test_custom_port(loop: Any, app: Any, aiohttp_unused_port: Any) -> None:
    port = aiohttp_unused_port()
    client = _TestClient(_TestServer(app, port=port))
    await client.start_server()

    assert client.server.port == port

    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert _hello_world_str == text

    await client.close()


@pytest.mark.parametrize(
    ("hostname", "expected_host"),
    [("127.0.0.1", "127.0.0.1"), ("localhost", "127.0.0.1"), ("::1", "::1")],
)
async def test_test_server_hostnames(
    hostname: Any, expected_host: Any, loop: Any
) -> None:
    app = _create_example_app()
    server = _TestServer(app, host=hostname, loop=loop)
    async with server:
        pass
    assert server.host == expected_host


@pytest.mark.parametrize("test_server_cls", [_TestServer, _RawTestServer])
async def test_base_test_server_socket_factory(
    test_server_cls: type, app: Any, loop: Any
) -> None:
    factory_called = False

    def factory(*args, **kwargs) -> socket:
        nonlocal factory_called
        factory_called = True
        return get_port_socket(*args, **kwargs)

    server = test_server_cls(app, loop=loop, socket_factory=factory)
    async with server:
        pass

    assert factory_called
