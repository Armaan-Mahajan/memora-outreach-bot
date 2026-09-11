#!/usr/bin/env python3
"""
Render one single-image post from a content JSON file, using whichever
layout the content is written for.

Usage:
    python3 render.py <layout-name> <content-file.json>
    python3 render.py --all          # render every layout's own example

Layouts live in layouts/<name>/template.html. Every layout shares one
brand shell -- header (logo, wordmark, badge), footer (CTA pill, "Link in
bio"), background glow, Geist font -- copy-pasted identically into each
template file so there's no build step, and differs only in its .hero
zone. Adding a new layout means adding layouts/<name>/template.html (+ a
content-example.json) and, if it introduces a list-shaped field (an array
in the content JSON), a small builder function registered below --
scalar string fields substitute into {{FIELD_NAME}} tokens automatically.

Two self-checks run on every render, same discipline as the slideshow
renderer: a per-render assertion on the primary variable-length text (no
orphaned wraps), and a whole-hero overflow check that raises rather than
silently letting content spill past the canvas. Single-image cards don't
need the slideshow's element-collision check -- there's no absolutely
positioned chrome floating over content here, everything is in normal
flow, so the failure mode that actually applies is overflow, not overlap.
"""
import html
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUTS_DIR = os.path.join(HERE, "layouts")

BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

CHECK_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.6" '
    'stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
)
# Chat-bubble mark: reserved for Mora specifically (the chatbot, not a
# generator), per the icon convention set on the flow-outline/Agent card.
MORA_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 '
    '8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 '
    '4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>'
)


def rich(text: str) -> str:
    """Escape a text field, then restore **bold** markup."""
    escaped = html.escape(text, quote=False)
    return BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def build_outline_items(items):
    return "\n".join(
        f'<div class="outline-item"><span class="outline-dot"></span>{rich(item)}</div>'
        for item in items
    )


def build_check_items(items):
    return "\n".join(
        f'<div class="check-item"><span class="check-mark">{CHECK_ICON}</span>'
        f'<span class="check-text">{rich(item)}</span></div>'
        for item in items
    )


def build_comparison_rows(items, side):
    row_cls = "row-old" if side == "old" else "row-new"
    marker_cls = "marker-old" if side == "old" else "marker-new"
    return "\n".join(
        f'<div class="row {row_cls}"><span class="marker {marker_cls}"></span>'
        f"<span>{rich(item)}</span></div>"
        for item in items
    )


def build_messages(messages):
    parts = []
    for m in messages:
        text = rich(m.get("text", ""))
        if m.get("role") == "mora":
            parts.append(
                f'<div class="bubble bubble-mora">'
                f'<div class="mora-avatar">{MORA_ICON}</div>'
                f'<div class="bubble-text">{text}</div></div>'
            )
        else:
            parts.append(
                f'<div class="bubble bubble-user"><div class="bubble-text">{text}</div></div>'
            )
    return "\n".join(parts)


# Per-layout config: which array fields need a builder function (anything
# not listed here is treated as a plain scalar and substituted directly),
# plus how aggressively the primary-text auto-fit is allowed to shrink it.
# fit_min_px is set relative to each layout's own base font-size in its
# template.html -- a quote starting at 92px shouldn't shrink as far, in
# absolute terms, as a 58px comparison headline before it stops reading
# like the intended layout.
LAYOUTS = {
    "flow-outline": {
        "list_fields": {"outline_items": build_outline_items},
        "fit_max_lines": 2,
        "fit_min_px": 44,
    },
    "stat-hero": {
        "list_fields": {},
        "fit_max_lines": 2,
        "fit_min_px": 40,
    },
    "quote-callout": {
        "list_fields": {},
        "fit_max_lines": 4,
        "fit_min_px": 56,
    },
    "comparison": {
        "list_fields": {
            "left_items": lambda items: build_comparison_rows(items, "old"),
            "right_items": lambda items: build_comparison_rows(items, "new"),
        },
        "fit_max_lines": 2,
        "fit_min_px": 38,
    },
    "chat-mockup": {
        "list_fields": {"messages": build_messages},
        "fit_max_lines": 2,
        "fit_min_px": 40,
    },
    "flashcard-mockup": {
        "list_fields": {},
        "fit_max_lines": 2,
        "fit_min_px": 40,
    },
    "checklist": {
        "list_fields": {"items": build_check_items},
        "fit_max_lines": 2,
        "fit_min_px": 40,
    },
}


def fit_headline(page, max_lines, min_font_px, step_px=2):
    """
    Shrinks #headline's font-size until it wraps within max_lines, measured
    from its own rendered box height rather than assumed from character
    count -- a fixed size that looks right for one headline can overflow to
    an orphaned extra line for another. Every layout tags its primary
    variable-length text id="headline", whatever its semantic role
    (headline, quote, comparison title, ...), so this hooks into all of them
    the same way.
    """
    if page.query_selector("#headline") is None:
        return None
    font_size = page.evaluate(
        "parseFloat(getComputedStyle(document.querySelector('#headline')).fontSize)"
    )
    while font_size > min_font_px:
        lines = page.evaluate(
            """
            () => {
                const h = document.querySelector('#headline');
                const cs = getComputedStyle(h);
                const lineHeight = parseFloat(cs.lineHeight);
                return Math.round(h.getBoundingClientRect().height / lineHeight);
            }
            """
        )
        if lines <= max_lines:
            break
        font_size -= step_px
        page.evaluate(f"document.querySelector('#headline').style.fontSize = '{font_size}px'")
    return font_size


def fit_hero(page, min_scale=0.7, step=0.03):
    """
    Safety net beneath the headline-specific fit above: shrinks the whole
    .hero zone -- icons, panels, chat bubbles, flashcard mock included, via
    zoom rather than font-size alone -- if content still overflows its
    allotted space between the header and footer. Mirrors the slideshow
    renderer's per-slide fit_slides.
    """
    return page.evaluate(
        f"""
        () => {{
            const hero = document.querySelector('.hero');
            let scale = 1.0;
            while (hero.scrollHeight > hero.clientHeight && scale > {min_scale}) {{
                scale = Number((scale - {step}).toFixed(2));
                hero.style.zoom = scale;
            }}
            return {{ scale, overflow: hero.scrollHeight - hero.clientHeight }};
        }}
        """
    )


def render(layout: str, content_path: str):
    if layout not in LAYOUTS:
        raise ValueError(f"Unknown layout '{layout}'. Known: {', '.join(LAYOUTS)}")
    config = LAYOUTS[layout]

    with open(content_path) as f:
        content = json.load(f)

    template_path = os.path.join(LAYOUTS_DIR, layout, "template.html")
    with open(template_path) as f:
        template = f.read()

    out_html = template
    for key, value in content.items():
        if key == "slug":
            continue
        token = "{{" + key.upper() + "}}"
        if key in config["list_fields"]:
            out_html = out_html.replace(token, config["list_fields"][key](value))
        elif isinstance(value, str):
            out_html = out_html.replace(token, rich(value))

    tmp_path = os.path.join(LAYOUTS_DIR, layout, "_rendered.html")
    with open(tmp_path, "w") as f:
        f.write(out_html)

    slug = content.get("slug", "card")
    out_dir = os.path.join(HERE, "output", layout)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{slug}.jpg")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
            page.goto("file://" + tmp_path)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)

            fit_headline(page, max_lines=config["fit_max_lines"], min_font_px=config["fit_min_px"])
            page.wait_for_timeout(100)
            result = fit_hero(page)
            page.wait_for_timeout(100)

            if result["overflow"] > 4:  # a few px of subpixel slack
                raise RuntimeError(
                    f"{layout}/{slug}: hero content still overflows by "
                    f"{result['overflow']}px at the {result['scale']} zoom floor -- "
                    f"shorten the content or extend fit_hero's min_scale for this layout"
                )

            page.screenshot(path=out_path, type="jpeg", quality=95)
            browser.close()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    size = os.path.getsize(out_path)
    if size > 8 * 1024 * 1024:
        raise RuntimeError(f"{out_path} is {size} bytes, over Instagram's 8 MB limit")
    print(f"Wrote {out_path} ({size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--all":
        for name in LAYOUTS:
            render(name, os.path.join(LAYOUTS_DIR, name, "content-example.json"))
        sys.exit(0)

    if len(sys.argv) != 3:
        print("Usage: python3 render.py <layout-name> <content-file.json>")
        print("       python3 render.py --all")
        print(f"Layouts: {', '.join(LAYOUTS)}")
        sys.exit(1)
    render(sys.argv[1], sys.argv[2])
