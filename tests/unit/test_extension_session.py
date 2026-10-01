"""Behavioral boundaries of the guest command/result adapter; no live GNOME calls."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import Mock

import pytest

from tests.shared.extension_session import ExtensionSession, installed_path, parse_shell_json


def test_shell_json_preserves_unicode_rendered_labels_and_false_state():
    output = "(true, '{\"title\":\"THỊ TRƯỜNG TÀI CHÍNH\",\"visible\":false,\"rows\":[\"BTC-USD\",\"^GSPC\"]}')"
    assert parse_shell_json(output) == {
        "title": "THỊ TRƯỜNG TÀI CHÍNH", "visible": False, "rows": ["BTC-USD", "^GSPC"],
    }


@pytest.mark.parametrize("output", [
    "(false, 'true')", "(true, 'undefined')", "(true, 1)", "true", "(true, '{broken')",
])
def test_rejected_or_malformed_eval_cannot_pass_a_rendering_assertion(output):
    with pytest.raises(AssertionError):
        parse_shell_json(output)


def test_installed_path_uses_the_cli_candidate_path_not_a_system_default():
    assert installed_path("Example\n  State: ACTIVE\n  Path: /var/home/guest/.local/share/gnome-shell/extensions/example@host\n") == Path(
        "/var/home/guest/.local/share/gnome-shell/extensions/example@host"
    )


@pytest.mark.parametrize("info", ["State: ACTIVE", "Path: relative/extension"])
def test_missing_candidate_location_is_a_failure(info):
    with pytest.raises(AssertionError, match="absolute Path"):
        installed_path(info)


def test_failed_settings_restoration_remains_a_cleanup_failure():
    session = ExtensionSession({"uuid": "example@host", "schema": "org.gnome.shell.extensions.example"})
    session._saved_settings = {"visible": "true"}
    session.command = Mock(side_effect=AssertionError("schema unavailable"))
    with pytest.raises(AssertionError, match="cleanup failed.*",):
        session.cleanup()
    assert session._saved_settings == {"visible": "true"}


def test_enabled_state_matching_does_not_accept_a_different_uuid():
    session = ExtensionSession({"uuid": "example@host", "schema": "org.gnome.shell.extensions.example"})
    session.command = Mock(return_value=subprocess.CompletedProcess([], 0, "prefix-example@host\nexample@host-suffix\n", ""))
    assert session.is_enabled() is False


@pytest.mark.parametrize("active_state", ["ACTIVE", "ENABLED"])
def test_enabled_flag_waits_for_actual_activation(monkeypatch, active_state):
    session = ExtensionSession({"uuid": "example@host", "schema": "org.gnome.shell.extensions.example"})
    session.command = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "example@host\n", ""),
        subprocess.CompletedProcess([], 0, "State: ACTIVATING\n", ""),
        subprocess.CompletedProcess([], 0, f"State: {active_state}\n", ""),
    ])
    monkeypatch.setattr("tests.shared.extension_session.time.sleep", lambda seconds: None)
    assert session.enable() == active_state


@pytest.mark.parametrize("state", ["ERROR", "OUT OF DATE"])
def test_terminal_activation_errors_fail_immediately(state):
    session = ExtensionSession({"uuid": "example@host", "schema": "org.gnome.shell.extensions.example"})
    session.command = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "example@host\n", ""),
        subprocess.CompletedProcess([], 0, f"State: {state}\n", ""),
    ])
    with pytest.raises(AssertionError, match="cannot activate"):
        session.enable()


@pytest.mark.parametrize(("expression", "expected"), [
    ("true", True),
    ("false", False),
    ('"true"', "true"),
    ('[true, false, 45, "THỊ TRƯỜNG TÀI CHÍNH"]', [True, False, 45, "THỊ TRƯỜNG TÀI CHÍNH"]),
    ('({visible: false, rows: ["BTC-USD", "^GSPC"]})', {"visible": False, "rows": ["BTC-USD", "^GSPC"]}),
])
def test_shell_eval_returns_typed_rendered_state(tmp_path, monkeypatch, expression, expected):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Eval serialization boundary test needs a JavaScript runtime (node)")
    # Execute real JS with Shell's EvalAsync serialization contract, without
    # connecting to or mutating the maintainer's GNOME session.
    bridge = tmp_path / "gdbus"
    bridge.write_text(
        f"#!{node}\n"
        "global.context = {unsafe_mode: true};\n"
        "const payload = JSON.stringify(eval(process.argv.at(-1)));\n"
        "process.stdout.write('(true, ' + JSON.stringify(payload ?? '') + ')');\n",
        encoding="utf-8",
    )
    bridge.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    session = ExtensionSession({"uuid": "example@host", "schema": "org.gnome.shell.extensions.example"})

    actual = session.shell_json(expression)

    assert type(actual) is type(expected)
    assert actual == expected


@pytest.mark.parametrize("probe", [False, "true", 1, None])
def test_installed_candidate_rejects_a_non_boolean_shell_prerequisite(tmp_path, probe):
    profile = {"uuid": "example@host", "schema": "org.gnome.shell.extensions.example"}
    (tmp_path / "metadata.json").write_text(json.dumps({
        "uuid": profile["uuid"], "settings-schema": profile["schema"],
    }), encoding="utf-8")
    session = ExtensionSession(profile)
    session.command = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, f"Path: {tmp_path}\n", ""),
        subprocess.CompletedProcess([], 0, "", ""),
    ])
    session.shell_json = Mock(return_value=probe)

    with pytest.raises(AssertionError, match="boolean true"):
        session.ensure_installed()
