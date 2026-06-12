"""Text-Extraktion pro Eingabeformat — Registry statt if/elif-Kette (Review P1.4).

Neue Formate: Extractor-Funktion schreiben und in EXTRACTORS registrieren;
SUPPORTED_EXTENSIONS leitet sich daraus ab (eine Quelle der Wahrheit). Das ist
auch der Andockpunkt für die Gemini-multimodal-PDF-Idee aus IDEAS.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import docx
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from obsidian_inbox_watcher.retrying import retryable

logger = logging.getLogger(__name__)

# Ein Extractor liefert (text_content, source_origin): source_origin ist der
# Dateipfad für lokale Dateien bzw. die gecrawlte URL für .url-Shortcuts.
Extractor = Callable[[str], tuple[str, str]]


@retryable
def _http_get(url: str, headers: dict[str, str]) -> requests.Response:
    """GET a URL, retrying transient failures and raising on HTTP error status."""
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    return res


def _extract_txt(filepath: str) -> tuple[str, str]:
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        return f.read(), filepath


def _extract_pdf(filepath: str) -> tuple[str, str]:
    reader = PdfReader(filepath)
    text_list = [t for page in reader.pages if (t := page.extract_text())]
    return "\n".join(text_list), filepath


def _extract_docx(filepath: str) -> tuple[str, str]:
    document = docx.Document(filepath)
    return "\n".join(p.text for p in document.paragraphs), filepath


def _extract_url(filepath: str) -> tuple[str, str]:
    url = None
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("URL="):
                url = line.split("URL=", 1)[1].strip()
                break
    if not url:
        raise ValueError(f"No URL found in .url file: {filepath}")
    logger.info("Extracted URL from shortcut: %s. Fetching page text...", url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    res = _http_get(url, headers)
    soup = BeautifulSoup(res.text, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    raw_text = soup.get_text(separator="\n")
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return "\n".join(lines), url


EXTRACTORS: dict[str, Extractor] = {
    ".txt": _extract_txt,
    ".pdf": _extract_pdf,
    ".docx": _extract_docx,
    ".url": _extract_url,
}

# Unterstützte Endungen = registrierte Extraktoren (keine zweite Liste pflegen).
SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(EXTRACTORS)


def extract_text(filepath: str, ext: str) -> tuple[str, str]:
    """Extract text from a supported input file via the registry.

    Returns a ``(text_content, source_origin)`` tuple. Raises on extraction
    failure or unknown extension (the caller dead-letters the file).
    """
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        raise ValueError(f"Unsupported file format: {ext}")
    return extractor(filepath)
