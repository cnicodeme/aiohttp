from typing import Any
from unittest import mock

import pytest

from aiohttp.connector import Connection
from aiohttp.test_utils import make_mocked_coro


@pytest.fixture
def key() -> object:
    return object()


@pytest.fixture
def loop() -> Any:
    return mock.Mock()


@pytest.fixture
def connector() -> Any:
    return mock.Mock()


@pytest.fixture
def protocol() -> Any:
    return mock.Mock(should_close=False, close=make_mocked_coro(None))


async def test_ctor(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    assert conn.protocol is protocol
    await conn.close()


async def test_callbacks_on_close(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    notified = False

    def cb() -> None:
        nonlocal notified
        notified = True

    conn.add_callback(cb)
    await conn.close()
    assert notified


async def test_callbacks_on_release(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    notified = False

    def cb() -> None:
        nonlocal notified
        notified = True

    conn.add_callback(cb)
    await conn.release()
    assert notified


async def test_callbacks_exception(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    notified = False

    def cb1() -> None:
        raise Exception

    def cb2() -> None:
        nonlocal notified
        notified = True

    conn.add_callback(cb1)
    conn.add_callback(cb2)
    await conn.close()
    assert notified


async def test_close(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    assert not conn.closed
    await conn.close()
    # assert conn._protocol() is None
    connector._release.assert_called_with(key, protocol, should_close=True)
    assert conn.closed


async def test_release(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    assert not conn.closed
    await conn.release()
    assert not protocol.transport.close.called
    # assert conn._protocol is None
    connector._release.assert_called_with(key, protocol, should_close=False)
    assert conn.closed


async def test_release_proto_should_close(
    connector: Any, key: Any, protocol: Any
) -> None:
    protocol.should_close = True
    conn = Connection(connector, key, protocol)
    assert not conn.closed
    await conn.release()
    assert not protocol.transport.close.called
    # assert conn._protocol is None
    connector._release.assert_called_with(key, protocol, should_close=True)
    assert conn.closed


async def test_release_released(connector: Any, key: Any, protocol: Any) -> None:
    conn = Connection(connector, key, protocol)
    await conn.release()
    connector._release.reset_mock()
    await conn.release()
    assert not protocol.transport.close.called
    # assert conn._protocol is None
    assert not connector._release.called
