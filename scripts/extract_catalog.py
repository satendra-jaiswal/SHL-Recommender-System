"""
Extract catalog JSON from the shl_product_catalog.pdf file.
The PDF is a pretty-printed JSON document split across pages.

Run: python scripts/extract_catalog.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path
import pypdf

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "shl_product_catalog.pdf"
OUTPUT_PATH = ROOT / "data" / "catalog.json"
(ROOT / "data").mkdir(exist_ok=True)


def clean_newlines_in_strings(text: str) -> str:
    # Remove carriage returns first
    text = text.replace('\r', '')
    
    result = []
    in_string = False
    escaped = False
    
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        
        if char == '"' and not escaped:
            in_string = not in_string
            result.append(char)
        elif char == '\\' and in_string:
            escaped = not escaped
            result.append(char)
        else:
            if in_string and char == '\n':
                # Strip trailing whitespace from the current result
                while result and result[-1] in (' ', '\t'):
                    result.pop()
                
                # Check if it ends with a hyphen
                if result and result[-1] == '-':
                    # Keep hyphen and merge directly
                    pass
                else:
                    result.append(' ')
                
                # Skip leading whitespace on the next line
                while i + 1 < n and text[i+1] in (' ', '\t'):
                    i += 1
            else:
                result.append(char)
            escaped = False
        i += 1
        
    return "".join(result)


def main():
    print(f"Opening PDF: {PDF_PATH}")
    reader = pypdf.PdfReader(PDF_PATH)
    num_pages = len(reader.pages)
    print(f"Total pages: {num_pages}")

    page_texts = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
        
        # Clean page boundary markers like "Pretty-print"
        cleaned = re.sub(r'(?i)pretty\s*-\s*print', '', text)
        page_texts.append(cleaned)

    # Join pages
    full_json_str = "\n".join(page_texts)
    
    # Clean wrapped lines within JSON string values
    full_json_str = clean_newlines_in_strings(full_json_str)
    
    # Strip any leading/trailing whitespace
    full_json_str = full_json_str.strip()
    
    # Try parsing
    try:
        catalog_data = json.loads(full_json_str)
        print(f"Successfully parsed catalog.json! Total items: {len(catalog_data)}")
        
        # Write to catalog.json
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)
        print(f"Saved catalog to: {OUTPUT_PATH}")
        
    except json.JSONDecodeError as e:
        print(f"JSON decode failed: {e}")
        # Print context around the error
        line_num = full_json_str.count('\n', 0, e.pos) + 1
        col_num = e.pos - full_json_str.rfind('\n', 0, e.pos)
        print(f"Error at line {line_num}, column {col_num}")
        
        # Show lines around error
        lines = full_json_str.split('\n')
        start_line = max(0, line_num - 5)
        end_line = min(len(lines), line_num + 5)
        print("Context:")
        for idx in range(start_line, end_line):
            marker = "--> " if idx == line_num - 1 else "    "
            print(f"{marker}{idx+1}: {lines[idx]}")


if __name__ == "__main__":
    main()
