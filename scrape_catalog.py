"""
Scrape the SHL Product Catalog — Individual Test Solutions only.
Multi-strategy: tries API first, then Playwright fallback.
"""
import asyncio
import json
import re
import time
import requests
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

OUT = Path(__file__).parent / "catalog.json"

# ─── Strategy 1: Try to scrape paginated catalog pages ─────────────────────────

def try_requests_scrape():
    """Attempt to scrape the SHL catalog using requests + BeautifulSoup."""
    products = []
    
    # The SHL catalog at shl.com is JS-rendered, but the individual product
    # pages at /products/product-catalog/view/SLUG/ are server-rendered.
    # Let's try to get the list from multiple approaches.
    
    # Approach: Try the catalog with query params
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    for page in range(1, 30):
        url = f"https://www.shl.com/solutions/products/product-catalog/?type=1&page={page}"
        print(f"  Trying page {page}: {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Find product links
            links = soup.find_all("a", href=re.compile(r"/product-catalog/view/"))
            if not links:
                print(f"    No products found on page {page}")
                break
            
            for link in links:
                name = link.get_text(strip=True)
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.shl.com" + href
                if name and len(name) > 2:
                    products.append({"name": name, "url": href})
            
            print(f"    Found {len(links)} links on page {page}")
        except Exception as e:
            print(f"    Error on page {page}: {e}")
            break
    
    return products


# ─── Strategy 2: Scrape via Playwright ──────────────────────────────────────────

async def try_playwright_scrape():
    """Use Playwright to scrape the JS-rendered catalog."""
    from playwright.async_api import async_playwright
    
    products = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()

        for pg in range(1, 30):
            url = f"https://www.shl.com/solutions/products/product-catalog/?type=1&page={pg}"
            print(f"  [Playwright] Loading page {pg} …")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                
                # Extract all product links
                rows = await page.evaluate("""() => {
                    const results = [];
                    const links = document.querySelectorAll('a[href*="product-catalog/view"]');
                    for (const link of links) {
                        const row = link.closest('tr');
                        const cells = row ? row.querySelectorAll('td') : [];
                        
                        // Get all text from each cell
                        const cellTexts = [];
                        for (const cell of cells) {
                            cellTexts.push(cell.textContent.trim());
                        }
                        
                        // Check for checkmark icons in cells (for Remote/Adaptive columns)
                        const cellChecks = [];
                        for (const cell of cells) {
                            const hasCheck = cell.querySelector('.catalogue__circle--yes, [class*="check"]') !== null;
                            const dotClass = cell.querySelector('[class*="circle"]');
                            cellChecks.push(hasCheck || (dotClass && dotClass.className.includes('yes')));
                        }
                        
                        results.push({
                            name: link.textContent.trim(),
                            url: link.href,
                            cells: cellTexts,
                            checks: cellChecks,
                            rowHTML: row ? row.innerHTML.substring(0, 1000) : ''
                        });
                    }
                    return results;
                }""")
                
                if not rows:
                    print(f"    No products on page {pg} — stopping.")
                    break
                
                print(f"    Found {len(rows)} products on page {pg}")
                for row in rows:
                    if not any(p["url"] == row["url"] for p in products):
                        products.append(row)
            except Exception as e:
                print(f"    Error on page {pg}: {e}")
                break
        
        await browser.close()
    
    return products


# ─── Strategy 3: Fetch individual product detail pages ─────────────────────────

def fetch_product_details(url, headers):
    """Fetch a single product's detail page and extract metadata."""
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        data = {}
        
        # Get title
        h1 = soup.find("h1")
        if h1:
            data["name"] = h1.get_text(strip=True)
        
        # Get description
        desc = soup.find("div", class_=re.compile(r"product.*desc|desc.*product|content", re.I))
        if desc:
            data["description"] = desc.get_text(strip=True)[:500]
        
        # Look for test type, duration, languages in the page content
        text = soup.get_text()
        
        # Duration pattern
        dur_match = re.search(r"(\d+)\s*minutes?", text)
        if dur_match:
            data["duration_minutes"] = int(dur_match.group(1))
        
        return data
    except Exception as e:
        print(f"    Error fetching {url}: {e}")
        return {}


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SHL Product Catalog Scraper")
    print("=" * 60)
    
    # Strategy 1: requests
    print("\n[1] Trying requests-based scrape …")
    products = try_requests_scrape()
    print(f"    → Got {len(products)} products")
    
    # Strategy 2: Playwright (if requests didn't get enough)
    if len(products) < 50:
        print("\n[2] Trying Playwright-based scrape …")
        pw_products = asyncio.run(try_playwright_scrape())
        print(f"    → Got {len(pw_products)} products")
        
        # Merge
        seen_urls = {p["url"] for p in products}
        for p in pw_products:
            if p["url"] not in seen_urls:
                products.append(p)
                seen_urls.add(p["url"])
    
    # Deduplicate
    seen = set()
    unique = []
    for p in products:
        key = p.get("url", p.get("name"))
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    
    print(f"\n[*] Total unique products: {len(unique)}")
    
    # Save
    with open(OUT, "w") as f:
        json.dump(unique, f, indent=2)
    print(f"[*] Saved to {OUT}")
    
    # Print first few
    for p in unique[:5]:
        print(f"  - {p.get('name', 'N/A')} → {p.get('url', 'N/A')}")


if __name__ == "__main__":
    main()
