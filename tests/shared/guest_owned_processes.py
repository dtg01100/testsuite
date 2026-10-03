"""Walk ``/proc`` from inside the disposable guest to find processes the test owns.

The SJC Gold and Stock Market scenarios stub the extension's Python helper to
exercise the real JS error path. Each scenario then proves no test-owned
helper subprocess (or, for Stock Market, no ``/usr/bin/curl``) survives
teardown. A host ``pgrep`` cannot distinguish a leaked guest subprocess from
unrelated host processes, so the walk must happen inside the guest and identify
ownership by the helper name embedded in ``/proc/<pid>/cmdline``.

The walker is a single Python script invoked via ``python3 -c``; argv form is
required because ``ExtensionSession.command`` runs ``subprocess.run`` without a
shell, so any unescaped quoting inside the script becomes a literal byte the
interpreter sees and rejects with ``SyntaxError`` -- in which case the empty
stdout (and ``check=False``) silently produced ``[]`` and the assertion below
passed vacuously. Pinning that contract is what the regression tests in
``tests/unit/test_guest_owned_processes_walker.py`` cover.
"""

# The literal Python source the walker runs in the guest. Kept as a module
# constant so the unit tests can compile it without going through ``subprocess``.
WALKER_SCRIPT = (
    "import os, sys\n"
    "needle = sys.argv[1]\n"
    "pids = [int(p) for p in os.listdir('/proc') if p.isdigit()]\n"
    "owned = []\n"
    "for pid in pids:\n"
    "    try:\n"
    "        cmdline = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\\\\x00', b' ').decode('utf-8', 'replace')\n"
    "        if needle in cmdline:\n"
    "            owned.append((pid, cmdline.strip()))\n"
    "    except Exception:\n"
    "        pass\n"
    "print('\\n'.join(f'{pid} {cmdline}' for pid, cmdline in owned))\n"
)


def guest_owned_processes(context, needle):
    """Return ``"pid cmdline"`` lines whose cmdline contains ``needle``.

    Runs the walker inside the guest via the existing ``ExtensionSession.command``
    bridge with ``check=False`` so an absent walker process emits no spurious
    failures -- an empty stdout is the legitimate "nothing found" signal.
    """
    result = context.extension.command(
        ["python3", "-c", WALKER_SCRIPT, needle], check=False
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def assert_no_guest_owned_processes(context, needles):
    """Fail the step when any ``needle`` matches a guest ``/proc`` cmdline.

    ``needles`` is an iterable of substrings. The Stock Market scenario
    matches both the helper name and ``/usr/bin/curl``; SJC Gold matches the
    helper name alone.
    """
    owned = []
    for needle in needles:
        owned.extend(guest_owned_processes(context, needle))
    assert not owned, (
        "Test-owned helper or curl process must not survive scenario teardown: "
        + "\n".join(owned)
    )
