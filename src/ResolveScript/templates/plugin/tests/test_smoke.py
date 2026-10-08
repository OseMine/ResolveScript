"""Smoke tests that pass in the plugin sandbox with zero setup."""

import @NAME@


def test_version_is_a_string() -> None:
    assert isinstance(@NAME@.__version__, str)


def test_register_commands_is_callable() -> None:
    assert callable(@NAME@.register_commands)


def test_plugin_module_loads_in_sandbox() -> None:
    """Verify the plugin entry module loads correctly in the test sandbox.

    The ResolveScript test fixtures (M4) install a FakeResolve and make
    ``import @NAME@`` work from the tests/ directory.
    """
    import argparse
    parser = argparse.ArgumentParser()
    # Should not raise
    @NAME@.register_commands(parser)