"""Regression for the guest owned-process walker in sjc_gold / stock_market steps.

The walker is the python ``-c`` payload ``_guest_owned_processes`` /
``_stock_guest_owned_processes`` invoke. Issue #919 originally passed the
script through ``cmd.split()`` to ``ExtensionSession.command``,
which runs ``subprocess.run(argv, ...)`` without a shell. The single
quotes inside the script became literal bytes the interpreter saw and
rejected with ``SyntaxError: unterminated string literal``; with
``check=False`` the empty stdout produced ``[]`` and the assertion
silently passed -- a vacuous guard that could not catch a leaked helper.

The fix sends the script as a single argv element and lets the guest's
``python3 -c`` parse it as a file would. These tests pin that:

* the script string is syntactically valid Python;
* the argv shape passed to ``command`` is ``[python3, -c, <script>, <needle>]``,
  not a shell-tokenised string.

The walker logic itself (the /proc walk, the needle match, the print) runs
on the guest; we exercise the host-side glue by stubbing ``command``.
"""

from __future__ import annotations

import subprocess as _subprocess
from unittest.mock import Mock

import pytest

from tests.extensions.features.steps import sjc_gold_steps, stock_market_steps


def _argv_for(command_mock):
    """Extract the argv the step passed to ``ExtensionSession.command``."""
    assert command_mock.call_count == 1, command_mock.call_args_list
    args, _ = command_mock.call_args
    return args[0]


@pytest.mark.parametrize(
    "walker, needle, expected_count",
    [
        (sjc_gold_steps._guest_owned_processes, "sjc_price.py", 4),
        (stock_market_steps._stock_guest_owned_processes, "stocks_fetch.py", 4),
        (stock_market_steps._stock_guest_owned_processes, "/usr/bin/curl", 4),
    ],
)
def test_walker_passes_a_python_invocation_with_three_positional_args(
    walker, needle, expected_count
):
    """The script must reach ``python3`` as a single argv element, not as a
    shell tokenised string. ``subprocess.run`` without ``shell=True`` would
    otherwise feed every whitespace-separated byte to ``python3 -c`` and
    raise ``SyntaxError`` on the embedded single quotes -- exactly the
    vacuous-pass regression this test pins.
    """
    context = Mock()
    context.extension.command = Mock(
        return_value=_subprocess.CompletedProcess([], 0, "", "")
    )
    if walker is stock_market_steps._stock_guest_owned_processes:
        walker(context, needle)
    else:
        walker(context)
    argv = _argv_for(context.extension.command)
    assert argv[0] == "python3"
    assert argv[1] == "-c"
    assert isinstance(argv[2], str) and argv[2].strip(), (
        "the script must be a non-empty single argv element"
    )
    assert argv[3] == needle
    assert len(argv) == expected_count


def test_sjc_walker_script_is_valid_python():
    """The literal script the step embeds must parse as Python; if a future
    refactor reintroduces a syntax error the walker would always return
    ``[]`` (the assertion it backs would silently pass).
    """
    context = Mock()
    context.extension.command = Mock(
        return_value=_subprocess.CompletedProcess([], 0, "", "")
    )
    sjc_gold_steps._guest_owned_processes(context)
    argv = _argv_for(context.extension.command)
    compile(argv[2], "<sjc-walker-script>", "exec")


def test_stock_walker_script_is_valid_python():
    """The literal script ``_stock_guest_owned_processes`` embeds must parse
    as Python. Same vacuous-pass concern as the sjc walker.
    """
    context = Mock()
    context.extension.command = Mock(
        return_value=_subprocess.CompletedProcess([], 0, "", "")
    )
    stock_market_steps._stock_guest_owned_processes(context, "stocks_fetch.py")
    argv = _argv_for(context.extension.command)
    compile(argv[2], "<stock-walker-script>", "exec")
