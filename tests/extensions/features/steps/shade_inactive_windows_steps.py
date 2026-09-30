"""Observe real application actors; never inspect extension controller objects.

Source: gnome-extensions-hive/Shade-Inactive-Windows-Reborn,
59b0afaf7320f72ef408621dafac19ec0214705b, extension.js and its schema.
The named BrightnessContrastEffect changes all three brightness channels; active
windows retain a disabled effect with zero brightness, not reduced opacity.
"""

import json
import re
from pathlib import Path

from behave import given, then, when

from tests.shared.results_dir import resolve_results_dir


EFFECT_NAME = "shade-inactive-windows-reborn-binhnguyensoft-com"
SHADE_PROPERTY = f"@effects.{EFFECT_NAME}.shade-value"
APPLICATION_IDS = {
    "Text Editor": "org.gnome.TextEditor",
    "Calculator": "org.gnome.Calculator",
}


def _application_actors(application):
    """Return a JS expression identifying actual GTK/WM application windows."""
    app_id = json.dumps(APPLICATION_IDS[application].lower())
    return f"""global.get_window_actors().filter(actor => {{
        const window = actor.get_meta_window();
        return window && [window.get_gtk_application_id(),
                          window.get_wm_class(), window.get_wm_class_instance()]
            .some(id => id && id.toLowerCase() === {app_id});
    }})"""


def _window_actor(context, application):
    sequence = context.shade_windows[application]["sequence"]
    return f"""global.get_window_actors().find(actor =>
        actor.get_meta_window()?.get_stable_sequence() === {sequence})"""


def _window_state(context, application):
    """Only public Meta.Window, Clutter.Actor and Clutter.Effect observations."""
    actor = _window_actor(context, application)
    return f"""(() => {{
        const actor = {actor};
        if (!actor) return null;
        const effect = actor.get_effect({json.dumps(EFFECT_NAME)});
        const transition = actor.get_transition({json.dumps(SHADE_PROPERTY)});
        return {{
            mapped: actor.is_mapped(),
            focused: actor.get_meta_window() === global.display.focus_window,
            opacity: actor.get_opacity(),
            effectPresent: effect !== null,
            effectEnabled: effect ? effect.get_enabled() : false,
            brightness: effect ? effect.get_brightness() : null,
            transitionPresent: transition !== null,
            transitionPlaying: transition ? transition.is_playing() : false,
            transitionDuration: transition ? transition.get_duration() : null,
            transitionElapsed: transition ? transition.get_elapsed_time() : null,
        }};
    }})()"""


def _wait_window(context, application, *, focused, brightness=None, exempt=False):
    opacity = context.shade_windows[application]["opacity"]
    # get_brightness() has exactly three out parameters (red, green, blue).
    # Float channels must be compared with a tolerance after the real fade ends.
    effect_check = (
        "!state.effectPresent && !state.transitionPresent"
        if exempt
        else f"""state.effectPresent && !state.transitionPresent &&
            state.effectEnabled === {json.dumps(not focused)} &&
            Array.isArray(state.brightness) && state.brightness.length === 3 &&
            state.brightness.every(value => Math.abs(value - {brightness}) < 0.0001)"""
    )
    context.extension.wait_for(f"""(() => {{
        const state = {_window_state(context, application)};
        return state !== null && state.mapped &&
            state.focused === {json.dumps(focused)} &&
            state.opacity === {opacity} && ({effect_check});
    }})()""")


def _close_application_windows(session, applications):
    """Close only apps proved absent before this scenario launched them."""
    for application in applications:
        actors = _application_actors(application)
        session.shell_json(f"""(() => {{
            for (const actor of {actors})
                actor.get_meta_window().delete(global.display.get_current_time_roundtrip());
            return true;
        }})()""")
        session.wait_for(f"({actors}).length === 0")


@given("Shade Inactive Windows is configured for {percent:d} percent shading and a {duration:d} millisecond fade")
def configure_shading(context, percent, duration):
    context.extension.set_setting("shade-level", str(percent))
    context.extension.set_setting("fade-duration", str(duration))
    context.extension.set_setting("excluded-apps", "[]")


@given("fresh Text Editor and Calculator application windows are open for shading")
def launch_application_windows(context):
    # Import only at runtime: the desktop/GI stack is not a dry-run dependency.
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    desktop_apps = {}
    for application, app_id in APPLICATION_IDS.items():
        desktop_apps[application] = Gio.DesktopAppInfo.new(f"{app_id}.desktop")
        assert desktop_apps[application] is not None, (
            f"Required guest application is missing: {app_id}.desktop"
        )
        existing = context.extension.shell_json(f"({_application_actors(application)}).length")
        assert existing == 0, (
            f"Fresh disposable guest required: {application} already has {existing} windows"
        )

    launched = []
    context.shade_windows = {}
    context.extension_cleanups.append((_close_application_windows, (context.extension, launched)))
    for application, desktop_app in desktop_apps.items():
        # Record ownership before launch so a partially failed launch is cleaned up.
        launched.append(application)
        assert desktop_app.launch([], None), f"Could not launch required {application} application"
        actors = _application_actors(application)
        context.extension.wait_for(f"""(() => {{
            const actors = {actors};
            return actors.length === 1 && actors[0].is_mapped() &&
                actors[0].get_opacity() === 255;
        }})()""", timeout=20)
        context.shade_windows[application] = context.extension.shell_json(f"""(() => {{
            const actor = ({actors})[0];
            const window = actor.get_meta_window();
            return {{sequence: window.get_stable_sequence(),
                     opacity: actor.get_opacity(),
                     windowClass: window.get_wm_class() || window.get_wm_class_instance()}};
        }})()""")

    assert context.shade_windows["Text Editor"]["sequence"] != context.shade_windows["Calculator"]["sequence"], (
        "The shading scenario must use two distinct real application windows"
    )


@when('I focus the "{application}" application window for shading using keyboard input')
def focus_application_window(context, application):
    # qecore.utility.keyboard_key_combo_input emits a real /dev/uinput combo.
    # Its source requires evdev names: LEFTALT, not the unsupported ALT alias.
    from qecore.utility import keyboard_key_combo_input

    sequence = context.shade_windows[application]["sequence"]
    focused = f"global.display.focus_window?.get_stable_sequence() === {sequence}"
    if not context.extension.shell_json(focused):
        keyboard_key_combo_input("<LEFTALT><TAB>")
    context.extension.wait_for(f"""(() => {{
        const state = {_window_state(context, application)};
        return state !== null && state.mapped && state.focused;
    }})()""")
    context.shade_focused_application = application


@then('the "{application}" application window is focused and unshaded')
def assert_focused_unshaded(context, application):
    _wait_window(context, application, focused=True, brightness=0)


@then('the "{application}" application window is inactive and shaded by {percent:d} percent')
def assert_inactive_shaded(context, application, percent):
    _wait_window(context, application, focused=False, brightness=-percent / 100)


def _restore_forced_animations(session, original):
    session.shell_json(f"(() => {{ global.force_animations = {json.dumps(original)}; return true; }})()")


@given("Shell animations are forced for the Shade transition scenario")
def force_transition_animations(context):
    animations = context.extension.command([
        "gsettings", "get", "org.gnome.desktop.interface", "enable-animations",
    ]).stdout.strip()
    assert animations == "true", "Guest enable-animations must be true for the active-fade teardown scenario"
    original = context.extension.shell_json("global.force_animations")
    context.extension_cleanups.append((_restore_forced_animations, (context.extension, original)))
    context.extension.shell_json("(() => { global.force_animations = true; return true; })()")


@when("I change the Shade Inactive Windows shade level to {percent:d} percent")
def change_shade_level(context, percent):
    context.extension.set_setting("shade-level", str(percent))


@when("I change the Shade Inactive Windows fade duration to {duration:d} milliseconds")
def change_fade_duration(context, duration):
    context.extension.set_setting("fade-duration", str(duration))


@when('I disable Shade Inactive Windows while the "{application}" window is transitioning')
def disable_during_transition(context, application):
    from time import monotonic, sleep

    deadline = monotonic() + 2
    while monotonic() < deadline:
        t_probe = monotonic()
        probe = context.extension.shell_json(_window_state(context, application))
        if probe and probe["transitionPresent"] and probe["transitionDuration"] != 1000:
            raise AssertionError("Guest animation slowdown must be 1x for the 1000ms fade test")
        if (probe and probe["mapped"] and not probe["focused"] and probe["effectPresent"] and
                probe["effectEnabled"] and probe["transitionPlaying"] and
                probe["transitionElapsed"] < probe["transitionDuration"] - 100):
            break
        sleep(0.05)
    else:
        raise AssertionError("Guest must expose a playing 1000ms focus fade with time remaining")

    context.extension.disable()
    state = context.extension.shell_json(_window_state(context, application))
    elapsed_since_probe = (monotonic() - t_probe) * 1000
    assert probe["transitionElapsed"] + elapsed_since_probe < probe["transitionDuration"] - 100, (
        "Fade ended before teardown observation's 100ms safety margin; "
        "cannot distinguish explicit transition removal from natural completion"
    )
    assert state is not None and not state["effectPresent"] and not state["transitionPresent"], (
        "Disabling must remove the running effect and transition synchronously"
    )


@then('a screenshot records the "{application}" window shaded by {percent:d} percent')
def capture_shaded_window(context, application, percent):
    _wait_window(context, application, focused=False, brightness=-percent / 100)
    directory = Path(resolve_results_dir(context)).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    scenario = re.sub(r"[^a-z0-9]+", "_", context.scenario.name.lower()).strip("_")[:60]
    label = re.sub(r"[^a-z0-9]+", "_", application.lower()).strip("_")
    path = directory / f"screenshot_extensions_shade_{label}_{percent}_{scenario}.png"
    path.unlink(missing_ok=True)
    # Use the exact native args from tests.shared.screenshot, but stay guest-local
    # on GNOME OS as well as bootc guests; never route screenshot input over SSH.
    context.extension.command([
        "gdbus", "call", "--session", "--dest", "org.gnome.Shell",
        "--object-path", "/org/gnome/Shell/Screenshot",
        "--method", "org.gnome.Shell.Screenshot.Screenshot",
        "true", "false", json.dumps(str(path)),
    ])
    assert path.is_file(), (
        "Required guest-local org.gnome.Shell.Screenshot capture did not produce "
        f"{path}; provision native screenshot permission and a writable results directory"
    )
    with path.open("rb") as screenshot:
        assert screenshot.read(8) == b"\x89PNG\r\n\x1a\n", f"Screenshot is not a PNG: {path}"
    print(f"Screenshot saved: {path}", flush=True)


@when('I exclude the "{application}" application from shading using its window class')
def exclude_application(context, application):
    window_class = context.shade_windows[application]["windowClass"]
    assert window_class, f"Required {application} window exposes no WM_CLASS identifier"
    # Source normalizes identifiers by trimming whitespace and lowercasing.
    context.extension.set_setting("excluded-apps", json.dumps([f"  {window_class.upper()}  "]))


@then('the "{application}" application window is inactive and exempt from shading')
def assert_inactive_exempt(context, application):
    _wait_window(context, application, focused=False, exempt=True)


@when("I clear the Shade Inactive Windows application exclusions")
def clear_application_exclusions(context):
    context.extension.set_setting("excluded-apps", "[]")


@then("no window actor retains a Shade Inactive Windows effect or transition")
def assert_effects_removed(context):
    # Do not let app crashes make the universal cleanup assertion pass vacuously.
    for application in APPLICATION_IDS:
        focused = application == context.shade_focused_application
        _wait_window(context, application, focused=focused, exempt=True)
    context.extension.wait_for(f"""global.get_window_actors().every(actor =>
        actor.get_effect({json.dumps(EFFECT_NAME)}) === null &&
        actor.get_transition({json.dumps(SHADE_PROPERTY)}) === null)""")
