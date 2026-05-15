#!/usr/bin/env bash
# Render docs/*.md → docs/pdf/*.pdf via pandoc (MD→HTML) + Chrome headless (HTML→PDF).
#
# No LaTeX dependency; just pandoc + Chrome (both already on most macOS dev boxes).
# Two style sheets:
#   _pdf_style_doc.css   — case study, exec summary (hr = divider, not page break)
#   _pdf_style.css       — interview deck       (hr = page break, one slide/page)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOCS="$ROOT/docs"
OUT="$DOCS/pdf"
mkdir -p "$OUT"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "ERROR: Google Chrome not found at $CHROME"; exit 1; }
command -v pandoc >/dev/null 2>&1 || { echo "ERROR: pandoc not installed (brew install pandoc)"; exit 1; }

render() {
    local md="$1" css="$2" out_pdf="$3"
    local base
    base="$(basename "${md%.md}")"
    local html="$OUT/${base}.html"

    echo "==> $base : MD → HTML"
    pandoc \
        --standalone \
        --embed-resources \
        --metadata title="$(head -n 5 "$md" | grep -m1 '^# ' | sed 's/^# //')" \
        --css "$css" \
        --highlight-style=tango \
        -f markdown+raw_html+yaml_metadata_block-tex_math_dollars-tex_math_single_backslash \
        -t html5 \
        "$md" -o "$html" 2>/dev/null

    echo "==> $base : HTML → PDF (Chrome headless)"
    # --no-pdf-header-footer removes default URL/date footer
    "$CHROME" \
        --headless \
        --disable-gpu \
        --no-pdf-header-footer \
        --print-to-pdf-no-header \
        --print-to-pdf="$out_pdf" \
        "file://$html" 2>/dev/null

    echo "    → $out_pdf  ($(du -h "$out_pdf" | awk '{print $1}'))"
}

# CSS paths must be absolute or relative to where pandoc runs.
DOC_CSS="$DOCS/_pdf_style_doc.css"
DECK_CSS="$DOCS/_pdf_style.css"
ONEPAGE_CSS="$DOCS/_pdf_style_onepage.css"

render "$DOCS/CASE_STUDY.md"        "$DOC_CSS"      "$OUT/CASE_STUDY.pdf"
render "$DOCS/EXECUTIVE_SUMMARY.md" "$ONEPAGE_CSS"  "$OUT/EXECUTIVE_SUMMARY.pdf"
render "$DOCS/INTERVIEW_DECK.md"    "$DECK_CSS"     "$OUT/INTERVIEW_DECK.pdf"

# Clean up the intermediate HTMLs (keep them if you want to re-render manually)
rm -f "$OUT"/*.html

echo
echo "==> All PDFs in: $OUT"
ls -lah "$OUT"/*.pdf
