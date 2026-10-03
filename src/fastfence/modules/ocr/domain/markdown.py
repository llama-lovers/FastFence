"""Plain-text Markdown preserves page provenance without fetching links."""

from fastfence.shared.ocr import OCRDocument, OCRError


def document_markdown(document: OCRDocument, max_bytes: int = 65_536) -> str:
    expected = list(range(1, len(document.pages) + 1))
    if [page.number for page in document.pages] != expected:
        raise OCRError("ocr_invalid_result")
    sections = ["# Extracted document"]
    for page in document.pages:
        lines = [block.text for block in page.blocks]
        # Four-space code blocks render recognized links/HTML as untrusted text.
        body = "\n".join(
            "    " + line for text in lines for line in text.splitlines()
        )
        sections.append(
            f"## Page {page.number}\n\n{body or '[No text detected]'}"
        )
    markdown = "\n\n".join(sections) + "\n"
    if len(markdown.encode()) > max_bytes:
        raise OCRError("ocr_text_limit")
    return markdown
