#!/usr/bin/env python3
"""
Render one slideshow post from a content JSON file.

Usage:
    python3 render_slideshow.py content-example.json

Builds every slide into a single page (one KaTeX init, one font load, so all
slides are guaranteed visually consistent), then screenshots each slide
element to output/<slug>/01.png, 02.png, ...

Slide types: cover, body, list, closer.
Math: inline as $...$ inside any text field, or display blocks via the
"math" array on a slide. mhchem is loaded, so \\ce{...} works.
"""
import html
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))

# Text fields may contain **bold** and $math$. Escape the HTML first, then
# re-introduce markup — order matters, or the escaping eats our own tags.
BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def rich(text: str) -> str:
    """Escape a text field, then restore **bold**. Math is left for KaTeX."""
    escaped = html.escape(text, quote=False)
    return BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def math_blocks(slide) -> str:
    blocks = slide.get("math") or []
    # \[...\] is picked up by auto-render as display math. The expression is
    # raw LaTeX, so it must NOT be HTML-escaped.
    return "\n".join(f'<div class="math-block">\\[{m}\\]</div>' for m in blocks)


def progress_markup(index: int, total: int, slide_type: str) -> str:
    """
    Mirrors the flashcard viewer's ProgressBar: muted rounded track, brand
    gradient fill, no numeric label (Instagram already shows position dots).
    Absent on the cover (nothing read yet), full on the closer.
    """
    if slide_type == "cover":
        return ""
    percent = 100.0 if slide_type == "closer" else (index / (total - 1)) * 100
    return (
        '<div class="progress-track">'
        f'<div class="progress-fill" style="width: {percent:.1f}%"></div>'
        "</div>"
    )


def corner_logo(slide_type: str) -> str:
    if slide_type == "closer":
        return ""  # the closer carries the logo in its content instead
    return (
        '<div class="corner-logo">'
        '<img src="assets/social-media-logo-inverted.png">'
        "</div>"
    )


def build_slide(slide, index: int, total: int) -> str:
    kind = slide["type"]
    parts = [progress_markup(index, total, kind), '<div class="content">']

    if kind == "cover":
        parts.append(f'<div class="eyebrow">{rich(slide.get("eyebrow", ""))}</div>')
        parts.append(f'<div class="title">{rich(slide["title"])}</div>')
        if slide.get("sub"):
            parts.append(f'<div class="sub">{rich(slide["sub"])}</div>')

    elif kind == "body":
        parts.append(f'<div class="heading">{rich(slide["heading"])}</div>')
        parts.append('<div class="body-wrap">')
        if slide.get("math"):
            parts.append(math_blocks(slide))
        if slide.get("text"):
            parts.append(f'<div class="text">{rich(slide["text"])}</div>')
        parts.append("</div>")

    elif kind == "list":
        parts.append(f'<div class="heading">{rich(slide["heading"])}</div>')
        items = "\n".join(
            f'<div class="list-item"><span class="list-marker"></span>'
            f"<span>{rich(item)}</span></div>"
            for item in slide["items"]
        )
        parts.append(f'<div class="body-wrap"><div class="list">{items}</div></div>')

    elif kind == "closer":
        parts.append(
            '<div class="closer-logo">'
            '<img src="assets/social-media-logo-inverted.png"></div>'
        )
        parts.append(f'<div class="heading">{rich(slide["heading"])}</div>')
        parts.append(f'<div class="text">{rich(slide["text"])}</div>')
        if slide.get("cta"):
            parts.append(f'<div class="cta">{rich(slide["cta"])}</div>')

    else:
        raise ValueError(f"Unknown slide type: {kind}")

    parts.append("</div>")
    if kind in ("cover", "closer"):
        parts.append('<div class="glow-a"></div><div class="glow-b"></div>')
    parts.append(corner_logo(kind))

    # "list" would collide with the inner .list container's styles, so the
    # section carries a distinct class name.
    section_class = "list-slide" if kind == "list" else kind
    return (
        f'<section class="slide {section_class}" id="slide-{index}">'
        + "\n".join(parts)
        + "</section>"
    )


def fit_slides(page):
    """
    Content length varies per slide, so a fixed type scale will overflow on the
    long ones. Shrink each slide's content block until it fits its own frame,
    measured from the rendered box rather than guessed from character count.
    """
    return page.evaluate(
        """
        () => {
            const report = [];
            document.querySelectorAll('.slide').forEach((slide) => {
                const content = slide.querySelector('.content');
                let scale = 1.0;
                // .content is a flex child with a fixed available height, so
                // clientHeight IS the space it has to fit into. zoom scales
                // KaTeX along with the text, which font-size alone would not.
                while (content.scrollHeight > content.clientHeight && scale > 0.6) {
                    scale = Number((scale - 0.03).toFixed(2));
                    content.style.zoom = scale;
                }
                report.push({ id: slide.id, scale: scale });
            });
            return report;
        }
        """
    )


def check_collisions(page):
    """
    The failure mode that actually bit during design was elements overlapping
    (text landing on the corner logo, heading touching the progress bar) —
    which a text-fitting pass doesn't catch, because nothing overflows. Assert
    the fixed chrome and the content column never intersect.
    """
    return page.evaluate(
        """
        () => {
            const hits = [];
            const overlaps = (a, b) =>
                a.right > b.left && a.left < b.right &&
                a.bottom > b.top && a.top < b.bottom;
            // Compare the leaf text elements, not the .content container —
            // .content is a flex child whose box extends down past the visible
            // text into the padding, so it "overlaps" the logo even when
            // nothing visible does.
            const LEAVES =
                '.title, .heading, .text, .sub, .eyebrow, .list-item, .math-block, .cta, .closer-logo';
            document.querySelectorAll('.slide').forEach((slide) => {
                const chrome = slide.querySelectorAll('.corner-logo, .progress-track');
                slide.querySelectorAll(LEAVES).forEach((leaf) => {
                    const l = leaf.getBoundingClientRect();
                    if (l.width === 0 || l.height === 0) return;
                    chrome.forEach((el) => {
                        if (overlaps(l, el.getBoundingClientRect())) {
                            hits.push(
                                slide.id + ': ' + leaf.className + ' hits ' + el.className
                            );
                        }
                    });
                });
            });
            return hits;
        }
        """
    )


def render(content_path: str):
    with open(content_path) as f:
        content = json.load(f)

    with open(os.path.join(HERE, "template.html")) as f:
        template = f.read()

    slides = content["slides"]
    total = len(slides)
    markup = "\n".join(build_slide(s, i, total) for i, s in enumerate(slides))

    tmp_path = os.path.join(HERE, "_rendered.html")
    with open(tmp_path, "w") as f:
        f.write(template.replace("{{SLIDES}}", markup))

    slug = content.get("slug", "deck")
    out_dir = os.path.join(HERE, "output", slug)
    os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.goto("file://" + tmp_path)
        page.wait_for_function("window.__katexDone === true", timeout=15000)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(400)

        # Fail loudly rather than shipping a slide with a raw LaTeX error in it.
        errors = page.evaluate(
            "Array.from(document.querySelectorAll('.katex-error')).map(e => e.textContent)"
        )
        if errors:
            raise RuntimeError(f"KaTeX failed on: {errors}")

        fit_slides(page)
        page.wait_for_timeout(200)

        collisions = check_collisions(page)
        if collisions:
            raise RuntimeError(f"Overlapping elements on: {collisions}")

        written = []
        for i in range(total):
            # JPEG, not PNG: Instagram's Content Publishing API accepts JPEG
            # only. quality=95 is visually indistinguishable here and keeps
            # each slide far under the 8 MB per-image limit.
            path = os.path.join(out_dir, f"{i + 1:02d}.jpg")
            page.locator(f"#slide-{i}").screenshot(path=path, type="jpeg", quality=95)
            written.append(path)

        browser.close()

    os.remove(tmp_path)

    for path in written:
        size = os.path.getsize(path)
        if size > 8 * 1024 * 1024:
            raise RuntimeError(f"{path} is {size} bytes, over Instagram's 8 MB limit")
        print(f"Wrote {path} ({size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 render_slideshow.py <content-file.json>")
        sys.exit(1)
    render(sys.argv[1])
