"""Smoke tests that pass in the mock sandbox with zero setup."""

import @NAME@


def test_version_is_a_string() -> None:
    assert isinstance(@NAME@.__version__, str)


def test_hello() -> None:
    assert @NAME@.hello() == "Hello from @NAME@!"


def test_menu_against_mock_resolve() -> None:
    """menu.run works against the injected mock DaVinciResolveScript.

    The sandbox fixture (M4) installs a FakeResolve with a project named
    'Demo Project'.
    """
    import DaVinciResolveScript as dvr_script

    from @NAME@.menu import run

    resolve = dvr_script.scriptapp("Resolve")
    message = run(resolve)
    assert "@NAME@" in message