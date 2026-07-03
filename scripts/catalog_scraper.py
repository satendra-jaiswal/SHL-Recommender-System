"""
Alternative catalog builder: fetches all product pages by hitting each known
URL pattern and extracts data. This approach works when the main catalog page
is JS-rendered.

Uses requests + BeautifulSoup to:
1. Fetch the sitemap or known product URL patterns
2. Scrape individual product pages for metadata
"""
from __future__ import annotations
import json
import time
import re
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "catalog.json"
DATA_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

KEY_TO_CODE = {
    "Ability & Aptitude": "A",
    "Assessment Exercises": "E",
    "Biodata & Situational Judgment": "B",
    "Competencies": "C",
    "Development & 360": "D",
    "Knowledge & Skills": "K",
    "Personality & Behavior": "P",
    "Simulations": "S",
}

BASE = "https://www.shl.com"
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch_sitemap_urls() -> list[str]:
    """Get product URLs from SHL sitemap."""
    product_urls = []
    
    sitemaps = [
        "https://www.shl.com/sitemap.xml",
        "https://www.shl.com/sitemap_index.xml",
        "https://www.shl.com/wp-sitemap.xml",
    ]
    
    for sitemap_url in sitemaps:
        try:
            resp = SESSION.get(sitemap_url, timeout=20)
            if resp.status_code == 200:
                # Find product catalog URLs
                urls = re.findall(r'<loc>(https://www\.shl\.com/(?:solutions/)?products/product-catalog/view/[^<]+)</loc>', resp.text)
                if urls:
                    print(f"Found {len(urls)} product URLs in {sitemap_url}")
                    product_urls.extend(urls)
                    break
                # Check for nested sitemaps
                nested = re.findall(r'<loc>(https://www\.shl\.com/[^<]*sitemap[^<]*)</loc>', resp.text)
                for ns in nested:
                    try:
                        nr = SESSION.get(ns, timeout=20)
                        if nr.status_code == 200:
                            u = re.findall(r'<loc>(https://www\.shl\.com/(?:solutions/)?products/product-catalog/view/[^<]+)</loc>', nr.text)
                            product_urls.extend(u)
                    except:
                        pass
        except Exception as e:
            print(f"  Sitemap error {sitemap_url}: {e}")
    
    return list(set(product_urls))


def scrape_product_page(url: str, entity_id: int) -> dict | None:
    """Scrape a single product page."""
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"    Error: {e}")
        return None

    # Get name from title or h1
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)
    if not name:
        title = soup.find("title")
        if title:
            name = title.get_text(strip=True).split("|")[0].strip()

    if not name:
        return None

    # Description
    description = ""
    for sel in [
        ".product-catalogue-training-calendar__row--description p",
        ".product-overview__description p",
        ".product-description p",
        "meta[name='description']",
    ]:
        el = soup.select_one(sel)
        if el:
            description = el.get("content", "") or el.get_text(strip=True)
            if description:
                break

    # Parse detail rows
    job_levels, languages, duration, remote, adaptive = [], [], "", "", ""
    keys = []

    rows = soup.select(".product-catalogue-training-calendar__row")
    for row in rows:
        label_el = row.select_one(".product-catalogue-training-calendar__row--title")
        value_el = row.select_one(".product-catalogue-training-calendar__row--content")
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True).lower()
        value = value_el.get_text(separator=", ", strip=True)

        if "job level" in label or "assessment population" in label:
            job_levels = [v.strip() for v in value.split(",") if v.strip()]
        elif "language" in label:
            languages = [v.strip() for v in value.split(",") if v.strip()]
        elif "duration" in label or "time limit" in label:
            duration = value
        elif "remote" in label:
            remote = "Yes" if "yes" in value.lower() else "No"
        elif "adaptive" in label:
            adaptive = "Yes" if "yes" in value.lower() else "No"

    # Infer keys from page content (look for type badges)
    page_text = soup.get_text()
    for key in KEY_TO_CODE:
        if key in page_text:
            keys.append(key)

    return {
        "entity_id": str(entity_id),
        "name": name,
        "link": url,
        "description": description[:1000],
        "keys": keys,
        "job_levels": job_levels,
        "languages": languages,
        "duration": duration,
        "remote": remote,
        "adaptive": adaptive,
        "status": "ok",
    }


def main():
    print("Fetching product URLs from sitemap...")
    urls = fetch_sitemap_urls()
    
    if not urls:
        print("No URLs found from sitemap. Trying alternative approach...")
        # Try Google/Bing cached list of SHL product URLs
        # This is a known subset from the assignment traces and public info
        urls = build_known_urls()
    
    print(f"Found {len(urls)} product URLs to scrape.")
    
    catalog = []
    for i, url in enumerate(sorted(set(urls))):
        print(f"[{i+1}/{len(urls)}] {url[:80]}")
        item = scrape_product_page(url, i + 1)
        if item:
            catalog.append(item)
        time.sleep(0.4)
    
    if catalog:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(catalog)} items to {OUTPUT_PATH}")
    else:
        print("No items scraped.")


def build_known_urls() -> list[str]:
    """Build list of known product URLs from the traces and common SHL products."""
    base = "https://www.shl.com/solutions/products/product-catalog/view/"
    known_slugs = [
        "occupational-personality-questionnaire-opq32r",
        "opq-universal-competency-report-2-0",
        "opq-leadership-report",
        "shl-verify-interactive-g",
        "graduate-scenarios",
        "dependability-and-safety-instrument-dsi",
        "hipaa-security",
        "medical-terminology-new",
        "microsoft-word-365-essentials-new",
        "core-java-advanced-level-new",
        "spring-new",
        "restful-web-services-new",
        "sql-new",
        "amazon-web-services-aws-development-new",
        "docker-new",
        "linux-programming-general",
        "networking-and-implementation-new",
        "smart-interview-live-coding",
        "contact-centre-call-simulation",
        "customer-service-phone-simulation",
        "svar-spoken-english-us-new",
        "entry-level-customer-service",
        "safety-8",
        "financial-analysis-new",
        "opq-sales-report",
        "opq-mq-sales-report",
        "verify-numerical-ability",
        "verify-verbal-ability",
        "verify-inductive-reasoning",
        "verify-deductive-reasoning",
        "verify-mechanical-comprehension",
    ]
    return [base + s + "/" for s in known_slugs]


if __name__ == "__main__":
    main()
