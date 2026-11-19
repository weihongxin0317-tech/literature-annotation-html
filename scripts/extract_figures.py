#!/usr/bin/env python3
"""Crop figures and tables out of a journal PDF for embedding in an annotated HTML.

Requires PyMuPDF (pip install pymupdf).

Usage
  # 1) list caption candidates to find page numbers and exact caption text
  python extract_figures.py paper.pdf --list

  # 2) crop a figure: band runs from a top anchor (or number) to a bottom anchor (or number)
  python extract_figures.py paper.pdf --page 9 --top 58 \
      --bottom-anchor "Network plot for pain" --xmax 566 --out F2.jpg

  # forest plot: header row to legend line, right edge = right-hand "Mean" header + 80 pt
  python extract_figures.py paper.pdf --page 10 --top-anchor "Intervention" \
      --bottom-anchor "Certainty of the evidence" --bottom-pad 6 --right-after-word Mean --out F3.jpg

Notes
  * Coordinates are PDF points (72/inch). Do NOT estimate them from a screenshot: the
    displayed image is scaled, so eyeballed pixels are wrong. Use anchors or --list.
  * Anchors are matched case-insensitively with search_for(); pick a phrase that occurs
    only in the caption (e.g. "Network plot for pain"), not in body text ("Fig 2").
  * Some journals render diagram labels as outlines, so text anchors fail. Then use
    --top/--bottom numbers and check the output visually.
  * Right-edge watermarks (e.g. BMJ "first published" text, x > ~575 pt) are excluded by --xmax.
  * Always open the output and check that nothing is clipped and no body text leaked in.
"""
import argparse
import os
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit('PyMuPDF is required: pip install pymupdf')


def find_first(page, text, top_limit=None):
    hits = page.search_for(text)
    if top_limit is not None:
        hits = [h for h in hits if h.y0 < top_limit]
    if not hits:
        raise SystemExit(f'anchor {text!r} not found on page {page.number + 1}')
    return hits[0]


def list_captions(doc):
    pat = re.compile(r'^(Fig(ure)?\.?|Table)\s*\d+\s*[|:.]', re.I)
    for i, page in enumerate(doc):
        for block in page.get_text('blocks'):
            text = block[4].strip().replace('\n', ' ')
            if pat.match(text):
                print(f'page {i + 1}  y={block[1]:.0f}  {text[:120]}')
    print('\nPages with many vector drawings (likely figures; check visually):')
    for i, page in enumerate(doc):
        n = len(page.get_drawings())
        if n > 50:
            print(f'  page {i + 1}: {n} drawing objects')


def union_band(page, y0, y1, xmin, xmax):
    rects = [d['rect'] for d in page.get_drawings()
             if d['rect'].y0 >= y0 - 2 and d['rect'].y1 <= y1 + 2
             and d['rect'].x0 >= xmin and d['rect'].x1 <= xmax]
    words = [fitz.Rect(w[:4]) for w in page.get_text('words')
             if w[1] >= y0 - 2 and w[3] <= y1 + 2 and w[0] >= xmin and w[2] <= xmax]
    items = rects + words
    if not items:
        raise SystemExit('nothing found in the band; check --top/--bottom values')
    u = fitz.Rect(items[0])
    for r in items[1:]:
        u |= r
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('--list', action='store_true', help='list caption candidates and exit')
    ap.add_argument('--page', type=int, help='1-based page number')
    ap.add_argument('--top', type=float, help='top of band in pt')
    ap.add_argument('--top-anchor', help='text whose top (minus pad) starts the band')
    ap.add_argument('--bottom', type=float, help='bottom of band in pt')
    ap.add_argument('--bottom-anchor', help='text whose top (minus 4 pt) ends the band')
    ap.add_argument('--bottom-pad', type=float, default=0, help='extra pad added below --bottom-anchor bottom')
    ap.add_argument('--xmin', type=float, default=15)
    ap.add_argument('--xmax', type=float, default=576)
    ap.add_argument('--right-after-word', help='set right edge to this header word x0 + 80 pt')
    ap.add_argument('--pad', type=float, default=5)
    ap.add_argument('--dpi', type=int, default=200)
    ap.add_argument('--out', default='figure.jpg', help='.png or .jpg')
    a = ap.parse_args()

    doc = fitz.open(a.pdf)
    if a.list:
        list_captions(doc)
        return
    if not a.page:
        sys.exit('--page is required unless --list is used')

    page = doc[a.page - 1]
    if a.top_anchor:
        top = find_first(page, a.top_anchor, top_limit=200).y0 - a.pad
    elif a.top is not None:
        top = a.top
    else:
        sys.exit('give --top or --top-anchor')

    if a.bottom_anchor:
        anchor = find_first(page, a.bottom_anchor)
        # caption-style anchor: stop just above it; legend-style anchor (--bottom-pad): stop below it
        bottom = anchor.y0 - 4 if not a.bottom_pad else anchor.y1 + a.bottom_pad
    elif a.bottom is not None:
        bottom = a.bottom
    else:
        sys.exit('give --bottom or --bottom-anchor')

    xmax = a.xmax
    if a.right_after_word:
        hdr = [w for w in page.get_text('words') if w[1] < 200 and w[4] == a.right_after_word and w[0] > 400]
        if not hdr:
            sys.exit(f'header word {a.right_after_word!r} not found above y=200')
        xmax = min(max(w[0] for w in hdr) + 80, a.xmax)

    band = union_band(page, top, bottom, a.xmin, xmax)
    clip = fitz.Rect(band.x0 - a.pad, top, min(band.x1 + a.pad, xmax), bottom) & page.rect
    zoom = a.dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    if a.out.lower().endswith('.png'):
        pix.save(a.out)
    else:
        with open(a.out, 'wb') as f:
            f.write(pix.tobytes('jpg', jpg_quality=90))
    print(f'wrote {a.out}  clip={[round(v) for v in clip]}  px={pix.width}x{pix.height}  bytes={os.path.getsize(a.out)}')


if __name__ == '__main__':
    main()
