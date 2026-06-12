"""Gemini-Aufruf, validiertes Antwortmodell und Obsidian-Note-Rendering."""

from __future__ import annotations

import logging
import os
import re

import yaml
from pydantic import BaseModel, Field, field_validator

from obsidian_inbox_watcher.config import get_known_domains
from obsidian_inbox_watcher.retrying import retryable

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"


class GeminiNote(BaseModel):
    """Validated and normalized Gemini response for one inbox document.

    Tolerant gegenüber typischen LLM-Abweichungen (Liste statt String,
    fehlende Felder); strukturell kaputte Antworten schlagen als
    ValidationError fehl und landen im Dead-Letter-Ordner.
    """

    titel: str = "Unbenannt"
    domain: str = ""
    tags: list[str] = Field(default_factory=list)
    summary: str = "Keine Zusammenfassung verfügbar."
    questions: str = "Keine Fragen identifiziert."
    action_items: list[str] = Field(default_factory=list)

    @field_validator("titel", "domain", "summary", "questions", mode="before")
    @classmethod
    def _stringify(cls, v: object) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return " ".join(str(item) for item in v)
        return v if isinstance(v, str) else str(v)

    @field_validator("tags", "action_items", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [v]
        if not isinstance(v, list):
            return []
        return [str(item) for item in v]


def normalize_domain(value: str) -> str:
    """Normalize a domain to a lowercase, space-free token for stable filtering.

    Titan matches the ``domain`` payload exactly in Qdrant, so casing and
    whitespace must be canonical. German umlauts are preserved.
    """
    slug = re.sub(r"\s+", "-", value.strip().lower())
    slug = re.sub(r"[^0-9a-zäöüß_-]", "", slug)
    return slug.strip("-") or "inbox"


def build_prompt(text_content: str) -> str:
    """Build the Gemini analysis prompt, seeded with the known Titan domains."""
    domains_block = "\n".join(f"- {d}" for d in get_known_domains())
    return f"""
Du bist ein hochpräziser Informations-Analysator für ein "Personal Corporate Memory"
System. Die erzeugten Notizen werden anschließend von der RAG-Engine "Titan"
indexiert; das Feld "domain" steuert die Einordnung im Wissensgraph.

Ordne den Inhalt EINER Domain zu. Bevorzuge eine bereits existierende Domain,
damit der Graph konsistent bleibt:
{domains_block}

Wenn keine davon inhaltlich passt, darfst du eine NEUE, treffende Domain vergeben.
Regeln für "domain": ein einzelnes, kleingeschriebenes deutsches Wort ohne
Leerzeichen (Bindestrich erlaubt), z.B. "trading" oder "infrastruktur".

Du MUSST das Ergebnis als ein valides JSON-Objekt im folgenden Format zurückgeben.

JSON-Struktur:
{{
  "titel": "Ein kurzer, prägnanter und aussagekräftiger deutscher Titel",
  "domain": "eine der obigen Domains oder eine neue, passende Domain",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "summary": "Eine prägnante Zusammenfassung des Inhalts in deutscher Sprache.",
  "questions": "Relevante Wissenslücken oder Fragen an den Benutzer (Fragen an mich).",
  "action_items": ["Action Item 1", "Action Item 2"]
}}

Textinhalt, der analysiert werden soll:
{text_content}
"""


@retryable
def _generate_note_json(api_key: str, prompt: str) -> str:
    """Call Gemini and return the raw JSON text, retrying transient failures."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    if not response.text:
        raise ValueError("Empty response from Gemini API")
    return str(response.text)


def render_note(
    note: GeminiNote, domain: str, source_origin: str, created_date: str
) -> tuple[str, str]:
    """Render ``(filename, markdown_content)`` for the Obsidian note.

    Frontmatter via yaml.safe_dump statt f-String: ein Titel/Source-Wert mit
    ':' oder '"' würde sonst das YAML brechen und Titan lehnte die Note als
    "domain fehlt" ab.
    """
    # Format tags to make sure we have exactly 5 elements
    tags_list = list(note.tags)
    if len(tags_list) < 5:
        tags_list += ["Knowledge", "System", "Archive", "Inbox", "Automated"]
    tags_list = tags_list[:5]

    # Format action items
    action_items = note.action_items or ["Keine direkten Action Items identifiziert"]
    action_items_str = "\n".join(f"- [ ] {item}" for item in action_items)

    frontmatter = yaml.safe_dump(
        {
            "domain": domain,
            "created": created_date,
            "source": source_origin,
            "tags": tags_list,
            "ai_processed": True,
        },
        allow_unicode=True,
        sort_keys=False,
    ).strip()

    title = note.titel.strip() or "Unbenannt"
    summary = note.summary.strip() or "Keine Zusammenfassung verfügbar."
    questions = note.questions.strip() or "Keine Fragen identifiziert."
    markdown_content = f"""---
{frontmatter}
---
# {title}

## Zusammenfassung
{summary}

## Wissenslücken / Fragen an mich
> [!IMPORTANT]
> {questions}

## Action Items
{action_items_str}
"""

    safe_title = re.sub(r'[\/*?:"<>|]', "", title)
    safe_title = re.sub(r"\s+", "_", safe_title)
    filename = f"{created_date}_{safe_title}.md"
    return filename, markdown_content


def unique_output_path(directory: str, filename: str) -> str:
    """Return a path in ``directory`` for ``filename`` that does not yet exist.

    Two different inputs can yield the same title — and therefore the same note
    name — on the same day. Rather than silently overwrite an existing note,
    append ``_v2``, ``_v3``, ... before the extension until the path is free.
    """
    candidate = os.path.join(directory, filename)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(filename)
    version = 2
    while True:
        candidate = os.path.join(directory, f"{stem}_v{version}{ext}")
        if not os.path.exists(candidate):
            return candidate
        version += 1
