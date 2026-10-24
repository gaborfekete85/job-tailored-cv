"""The tailored CV as a PDF, styled by a template from the reference folder.

A template is a PDF in `reference/` whose name contains "cv" — the look to match. Its style
is the CSS file next to it with the same name (`Gabor-Fekete-cv.pdf` -> `Gabor-Fekete-cv.css`);
a template without one gets `assets/cv-default.css`. The HTML has the same content as
`nodes.cv_markdown`, and headless Chrome prints it (no extra dependency).
"""

import base64
import html
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import nodes
from state import CvDatabase, TailoredCv

ROOT = Path(__file__).parent
REFERENCE_DIR = ROOT / "reference"
ASSETS_DIR = ROOT / "assets"
DEFAULT_CSS = ASSETS_DIR / "cv-default.css"
PDF_TIMEOUT_S = float(os.getenv("PDF_TIMEOUT_S", "45"))

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)
FONTS = (
    ("Carlito-Regular.ttf", 400, "normal"),
    ("Carlito-Bold.ttf", 700, "normal"),
    ("Carlito-Italic.ttf", 400, "italic"),
    ("Carlito-BoldItalic.ttf", 700, "italic"),
)
BOLD = re.compile(r"\*\*(.+?)\*\*")


class PdfError(RuntimeError):
    pass


class UnknownTemplate(PdfError):
    pass


# --- templates -----------------------------------------------------------------


def list_templates() -> list[dict]:
    return [
        {"name": pdf.name, "styled": pdf.with_suffix(".css").exists()}
        for pdf in sorted(REFERENCE_DIR.glob("*.pdf"))
        if "cv" in pdf.stem.lower()
    ]


def template_css(name: str) -> str:
    if name not in {t["name"] for t in list_templates()}:
        raise UnknownTemplate(f"Unknown CV template {name!r}")
    css = (REFERENCE_DIR / name).with_suffix(".css")
    return (css if css.exists() else DEFAULT_CSS).read_text(encoding="utf-8")


# --- CV -> HTML ----------------------------------------------------------------


def _data_uri(path: Path, mime: str) -> str | None:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}" if path.exists() else None


def _font_faces() -> str:
    """Embedded, so the PDF looks the same on any machine (Carlito is Calibri's metric twin)."""
    return "".join(
        f"@font-face{{font-family:'Carlito';font-weight:{weight};font-style:{style};"
        f"src:url({uri}) format('truetype');}}"
        for file, weight, style in FONTS
        if (uri := _data_uri(ASSETS_DIR / "fonts" / file, "font/ttf"))
    )


def _inline(text: str) -> str:
    """Escape the text, keeping **bold**."""
    parts = BOLD.split(text)
    return "".join(f"<strong>{html.escape(p)}</strong>" if n % 2 else html.escape(p) for n, p in enumerate(parts))


def _join(*parts: str | None) -> str:
    return '<span class="sep">|</span>'.join(html.escape(p) for p in parts if p)


def _section(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2>{body}</section>" if body else ""


def _list(items: list[str]) -> str:
    return f"<ul>{''.join(f'<li>{_inline(i)}</li>' for i in items)}</ul>" if items else ""


def cv_html(cv: CvDatabase, tailored: TailoredCv, bullets: dict[str, list[str]], css: str) -> str:
    contact, personal = cv.contact, cv.personal
    links = [
        f'<a href="mailto:{html.escape(email)}">{html.escape(email)}</a>' if (email := contact.get("Email")) else "",
        f'<a href="{html.escape(url)}">{html.escape(re.sub(r"^https?://", "", url))}</a>'
        if (url := contact.get("Portfolio"))
        else "",
    ]
    birthday = nodes._birthday(personal.get("Date of Birth"))
    codes = [
        ("portfolio_qr.png", "Portfolio", contact.get("Portfolio")),
        ("linkedin_qr.png", "LinkedIn", contact.get("LinkedIn")),
    ]
    qr = "".join(
        f'<img src="{uri}" alt=""><div class="cap">{label}</div>'
        for file, label, target in codes
        if target and (uri := _data_uri(ASSETS_DIR / file, "image/png"))
    )
    photo = _data_uri(ASSETS_DIR / "photo.png", "image/png")

    titles = {r.role_id: r.title for r in tailored.roles}
    entries = "".join(
        '<div class="entry">'
        f'<div class="entry-head">{html.escape(" — ".join(filter(None, [titles.get(role.id, role.title), role.company])))}</div>'
        f'<div class="entry-meta"><span class="period">{html.escape(nodes.format_period(role))}</span>'
        + (f'<span class="sep">|</span><span class="customer">Customer: {html.escape(role.customer)}</span>' if role.customer else "")
        + f"</div>{_list(nodes.role_bullets(role, bullets))}</div>"
        for role in cv.roles
    )
    certifications = [
        cert.name + (f" — {details}" if (details := ", ".join(filter(None, [cert.issuer, cert.status]))) else "")
        for cert in cv.certifications
    ]
    education = [
        " · ".join(filter(None, [" – ".join(filter(None, [e.start_year, e.end_year])), ", ".join(filter(None, [e.field, e.institution]))]))
        for e in cv.education
    ]

    body = "".join(
        [
            '<header class="cv-head">',
            f'<div class="cv-codes">{qr}</div>',
            '<div class="cv-who">',
            f"<h1>{html.escape(cv.name)}</h1>",
            f'<div class="cv-links">{'<span class="sep">|</span>'.join(filter(None, links))}</div>',
            f'<div class="cv-line">{_join(birthday and f"Born {birthday}", personal.get("Nationality"), personal.get("Work Permit"), personal.get("Availability"))}</div>',
            f'<div class="cv-line">{_join(contact.get("Address"), contact.get("Phone"))}</div>',
            "</div>",
            f'<div class="cv-portrait"><img src="{photo}" alt=""></div>' if photo else '<div class="cv-portrait"></div>',
            "</header>",
            f'<div class="cv-headline">{html.escape(tailored.headline)}</div>',
            _section(
                "Value Proposition",
                f"<h3>My Contribution</h3><p>{_inline(tailored.my_contribution)}</p>"
                f"<h3>My Profile</h3>{_list(tailored.my_profile)}",
            ),
            _section("Business Experience", entries),
            _section("Core Skills", f'<p class="skills">{_inline(" · ".join(tailored.core_skills))}</p>'),
            _section("Professional Development", _list(certifications)),
            _section("Education", _list(education)),
            _section("Interests", f"<p>{html.escape(', '.join(cv.interests))}</p>" if cv.interests else ""),
        ]
    )
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(cv.name)} — CV</title>'
        f"<style>{_font_faces()}{css}</style></head><body>{body}</body></html>"
    )


# --- HTML -> PDF ---------------------------------------------------------------


def chrome_path() -> str:
    if override := os.getenv("CHROME_PATH"):
        return override
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    if found := shutil.which("google-chrome") or shutil.which("chromium"):
        return found
    raise PdfError("No Chrome or Chromium found to print the PDF — set CHROME_PATH")


def to_pdf(page: str) -> bytes:
    """Print with headless Chrome. It tends to linger after writing the file, so the PDF is done
    when its size holds between two polls, and Chrome is killed either way."""
    with tempfile.TemporaryDirectory(prefix="cv-pdf-") as tmp:
        source, target = Path(tmp) / "cv.html", Path(tmp) / "cv.pdf"
        source.write_text(page, encoding="utf-8")
        child = subprocess.Popen(
            [
                chrome_path(),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={Path(tmp) / 'profile'}",  # never touch the real Chrome profile
                "--no-pdf-header-footer",
                f"--print-to-pdf={target}",
                source.as_uri(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            deadline, previous = time.monotonic() + PDF_TIMEOUT_S, -1
            while time.monotonic() < deadline:
                if target.exists():
                    if (size := target.stat().st_size) and size == previous:
                        break
                    previous = size
                elif child.poll() is not None:
                    stderr = child.stderr.read().decode(errors="replace").strip()
                    raise PdfError(f"Chrome exited {child.returncode} without a PDF: {stderr[:400]}")
                time.sleep(0.15)
            else:
                raise PdfError(f"Chrome did not produce a PDF within {PDF_TIMEOUT_S:.0f}s")
        finally:
            child.kill()
            child.wait()
        data = target.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise PdfError("Chrome produced a file that is not a PDF")
    return data
