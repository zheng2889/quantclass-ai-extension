"""PDF extraction router — download and parse PDF files for Chat with PDF."""

import io
import base64
import logging
from typing import Optional, List

import httpx
import fitz  # PyMuPDF

from fastapi import APIRouter, File, UploadFile, Form
from pydantic import BaseModel, Field
from models import success, param_error, internal_error

logger = logging.getLogger(__name__)

router = APIRouter(tags=["PDF"])


class PdfExtractRequest(BaseModel):
    """Request to extract text from a PDF URL."""
    url: str = Field(..., min_length=1, description="URL of the PDF file")
    max_pages: Optional[int] = Field(default=50, description="Max pages to extract")


class PdfExtractResponse(BaseModel):
    """Extracted PDF content."""
    text: str
    title: str
    pages: int
    chars: int


@router.post("/extract")
async def extract_pdf(request: PdfExtractRequest):
    """Download a PDF from URL and extract its text content.

    Uses PyMuPDF (fitz) for fast, accurate text extraction including
    CJK characters. Falls back gracefully on encrypted or image-only PDFs.
    """
    try:
        # Download the PDF
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(request.url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) QuantClass/1.0",
            })

        if resp.status_code != 200:
            return param_error(f"Failed to download PDF: HTTP {resp.status_code}")

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not request.url.lower().endswith(".pdf"):
            # Try anyway — some servers don't set content-type correctly
            logger.warning(f"Content-Type is {content_type}, trying to parse as PDF anyway")

        pdf_bytes = resp.content
        result = _parse_pdf_bytes(pdf_bytes, request.max_pages or 100)

        if not result:
            return param_error("PDF appears to be image-only or too small")

        return success(result)

    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return internal_error(f"PDF extraction failed: {str(e)}")


def _parse_pdf_bytes(pdf_bytes: bytes, max_pages: int = 100, extract_images: bool = True) -> dict:
    """Shared PDF parsing logic for both URL and upload paths.

    Extracts full text + images (as base64 data URIs) from each page.
    Images are filtered: only those > 5KB and reasonable dimensions
    (likely figures/charts, not icons/logos).
    """
    if len(pdf_bytes) < 100:
        return None

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    max_pages = min(max_pages, len(doc))

    pages_text = []
    images = []  # [{page, base64, width, height, mime}]

    for i in range(max_pages):
        page = doc[i]

        # Text extraction
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"--- Page {i+1} ---\n{text.strip()}")

        # Image extraction (figures, charts — skip tiny icons)
        if extract_images:
            for img_idx, img in enumerate(page.get_images(full=True)):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    img_bytes = base_image["image"]
                    mime = base_image.get("ext", "png")
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Filter: skip tiny images (icons, bullets, logos)
                    if len(img_bytes) < 5000:
                        continue
                    if width < 100 or height < 100:
                        continue
                    # Cap at 20 images total to avoid memory explosion
                    if len(images) >= 20:
                        break

                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    mime_type = f"image/{mime}" if mime in ("png", "jpeg", "jpg", "gif", "webp") else f"image/png"
                    images.append({
                        "page": i + 1,
                        "index": img_idx,
                        "base64": f"data:{mime_type};base64,{b64}",
                        "width": width,
                        "height": height,
                        "size_kb": len(img_bytes) // 1024,
                    })
                except Exception as e:
                    logger.debug(f"Failed to extract image {img_idx} from page {i+1}: {e}")

    doc.close()

    if not pages_text:
        return None

    full_text = "\n\n".join(pages_text)

    # Extract title from metadata or first line
    title = ""
    doc2 = fitz.open(stream=pdf_bytes, filetype="pdf")
    metadata = doc2.metadata
    if metadata and metadata.get("title"):
        title = metadata["title"]
    else:
        for line in full_text.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("---") and len(stripped) > 5:
                title = stripped[:100]
                break
    doc2.close()

    return {
        "text": full_text,
        "title": title,
        "pages": max_pages,
        "chars": len(full_text),
        "images": images,
        "image_count": len(images),
    }


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    max_pages: int = Form(default=50),
):
    """Upload a PDF file and extract its text content."""
    try:
        if not file.filename.lower().endswith(".pdf"):
            return param_error("File must be a PDF")

        pdf_bytes = await file.read()
        result = _parse_pdf_bytes(pdf_bytes, max_pages)

        if not result:
            return param_error("PDF appears to be image-only or empty")

        # Use filename as fallback title
        if not result["title"]:
            result["title"] = file.filename.replace(".pdf", "")

        return success(result)

    except Exception as e:
        logger.error(f"PDF upload extraction failed: {e}")
        return internal_error(f"PDF extraction failed: {str(e)}")
