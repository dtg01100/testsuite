"""Observe SJC Gold through the rendered Shell actor tree and real settings.

Actor classes and the unstyled parent widget's monitor-relative origin follow
extension.js at 1588c7683d113e42d2f36a69165a9bacd6b1d95b. Quote fetching is
not mocked here; successful HTTPS responses belong to the fixture lane (#909).
"""

import json

from behave import then, when


_SJC_ACTORS = """
    const hasClass = (actor, name) =>
        (actor.get_style_class_name?.() ?? '').split(/\\s+/).includes(name);
    const descendants = root => {
        const result = [];
        const visit = actor => {
            result.push(actor);
            for (const child of actor.get_children())
                visit(child);
        };
        if (root)
            visit(root);
        return result;
    };
    const rendered = actor => {
        if (!actor || !actor.is_visible() || !actor.is_mapped() ||
            !actor.has_allocation() || actor.get_paint_opacity() === 0)
            return false;
        const [width, height] = actor.get_transformed_size();
        return width > 0 && height > 0;
    };
    // Count every card, including invisible leftovers, before checking mapping.
    const cards = descendants(global.stage).filter(a => hasClass(a, 'sjc-card'));
    const card = cards.length === 1 ? cards[0] : null;
    // The source adds sjc-card to an unstyled St.Widget whose allocation sets
    // the primary-monitor origin. Card padding is not the preference offset.
    const widget = card?.get_parent();
    const cardRendered = rendered(card) && rendered(widget);
"""


def _sjc_expression(body):
    return "(() => {" + _SJC_ACTORS + body + "})()"


def _wait_for_sjc(context, body):
    context.extension.wait_for(_sjc_expression(body))


@when('I set the SJC Gold "{key}" preference to {value:d}')
def set_sjc_position_preference(context, key, value):
    assert key in {"left", "top"}, f"Not an SJC Gold position preference: {key}"
    context.extension.set_setting(key, str(value))


@then("exactly one SJC Gold desktop card is mapped and allocated")
def sjc_card_is_rendered(context):
    _wait_for_sjc(context, "return cardRendered;")


@then('the SJC Gold header reads "{text}"')
def sjc_header_is_rendered(context, text):
    expected = json.dumps(text, ensure_ascii=False)
    _wait_for_sjc(
        context,
        """
        if (!cardRendered)
            return false;
        const headers = descendants(card).filter(a => hasClass(a, 'sjc-header'));
        if (headers.length !== 1 || !rendered(headers[0]))
            return false;
        const titles = descendants(headers[0]).filter(a => hasClass(a, 'sjc-title'));
        return titles.length === 1 && rendered(titles[0]) &&
            titles[0].text === """ + expected + ";",
    )


@then("the SJC Gold price labels are rendered:")
def sjc_price_labels_are_rendered(context):
    expected = json.dumps([row["text"] for row in context.table], ensure_ascii=False)
    _wait_for_sjc(
        context,
        """
        if (!cardRendered)
            return false;
        const priceRows = descendants(card).filter(a => hasClass(a, 'sjc-price-row'));
        if (priceRows.length !== 1 || !rendered(priceRows[0]))
            return false;
        const labels = descendants(priceRows[0]).filter(a => hasClass(a, 'sjc-label'));
        const expected = """ + expected + """;
        return labels.length === expected.length && labels.every(rendered) &&
            expected.every(text => labels.filter(label => label.text === text).length === 1);
        """,
    )


@then(
    "the SJC Gold card is rendered at left {left:d} and top {top:d} "
    "on the primary monitor"
)
def sjc_card_has_monitor_position(context, left, top):
    _wait_for_sjc(
        context,
        """
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor || !cardRendered)
            return false;
        const [width, height] = widget.get_transformed_size();
        const [x, y] = widget.get_transformed_position();
        const left = """ + str(left) + "; const top = " + str(top) + """;
        // The source clamps to the monitor. These in-bounds preferences must
        // fit, or this scenario cannot demonstrate each independent movement.
        return width + left <= monitor.width && height + top <= monitor.height &&
            Math.abs(x - (monitor.x + left)) <= 1 &&
            Math.abs(y - (monitor.y + top)) <= 1;
        """,
    )


@then("no SJC Gold desktop card remains in the Shell actor tree")
def sjc_card_was_removed(context):
    _wait_for_sjc(context, "return cards.length === 0;")
