"""
Build catalog.json from the product_urls.txt list.
Uses a smarter HTML parser that ignores the Wayback Machine banner
and the sidebar legend that lists ALL test type codes.
"""
import json, re, time, requests
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = Path(__file__).parent
URL_FILE = DIR / "product_urls.txt"
OUT = DIR / "catalog.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch(url):
    """Fetch from Wayback with retries."""
    wb = f"https://web.archive.org/web/2024/{url.strip()}"
    for attempt in range(3):
        try:
            r = requests.get(wb, timeout=25, headers=HEADERS)
            if r.status_code == 200:
                return r.text
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        except Exception:
            if attempt < 2:
                time.sleep(2)
    return None


def parse(url, html):
    """Parse product page. Key fix: only look for test type codes
    within the product's own data section, not the sidebar legend."""
    soup = BeautifulSoup(html, "html.parser")
    slug = url.strip().rstrip("/").split("/")[-1]
    p = {"url": url.strip(), "slug": slug}

    # Remove Wayback Machine injected elements
    for wb in soup.find_all("div", id=re.compile(r"wm-ipp|donato|playback")):
        wb.decompose()
    for script in soup.find_all("script"):
        script.decompose()

    # ── Name ──
    h1 = soup.find("h1")
    p["name"] = h1.get_text(strip=True) if h1 else slug.replace("-", " ").title()

    # ── Description ── Look for the main product description paragraph
    desc = ""
    # Find the product description section
    main_content = soup.find("main") or soup.find("div", class_=re.compile(r"product|catalogue|content", re.I)) or soup
    for tag in main_content.find_all("p"):
        t = tag.get_text(strip=True)
        if (len(t) > 40 and 
            "cookie" not in t.lower() and 
            "wayback" not in t.lower() and
            "archive.org" not in t.lower() and
            "web archive" not in t.lower()):
            desc = t[:600]
            break
    p["description"] = desc

    # ── Job Levels ──
    jl = []
    jh = soup.find(string=re.compile(r"Job\s*Levels?", re.I))
    if jh:
        parent = jh.parent or jh
        ul = parent.find_next("ul")
        if ul:
            jl = [li.get_text(strip=True) for li in ul.find_all("li") if len(li.get_text(strip=True)) > 1]
    p["jobLevels"] = jl

    # ── Languages ──
    langs = []
    lh = soup.find(string=re.compile(r"Available\s+in|Languages?\s*$", re.I))
    if lh:
        parent = lh.parent or lh
        ul = parent.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                lt = li.get_text(strip=True)
                if len(lt) > 2 and lt not in ("A", "B", "C", "D", "E", "K", "P", "S"):
                    langs.append(lt)
    p["languages"] = langs

    # ── Duration ──
    full_text = soup.get_text()
    dm = re.search(r"(?:Approximate\s+)?(?:Completion|completion)\s*(?:Time|time)[:\s]*(?:in\s+)?(\d+)\s*(?:minutes|mins)?", full_text)
    if not dm:
        dm = re.search(r"(\d+)\s*(?:minutes|mins)\s*(?:approximate|approx)?", full_text, re.I)
    p["duration_minutes"] = int(dm.group(1)) if dm else None

    # ── Test Types ──
    # CRITICAL: Only look in the product's own "Assessment Type" or "Test Type" section
    # NOT the sidebar legend which lists all possible types
    test_types = []
    
    # Strategy 1: Look for "Assessment Type" section
    at_header = soup.find(string=re.compile(r"Assessment\s+Type|Test\s+Type|Product\s+Type", re.I))
    if at_header:
        parent = at_header.parent
        if parent:
            # Look at the next sibling elements for single-letter codes
            next_el = parent.find_next_sibling() or parent.find_next()
            if next_el:
                for el in next_el.find_all(["span", "li", "div", "p", "td"]):
                    txt = el.get_text(strip=True)
                    if len(txt) == 1 and txt in "ABCDEKPS" and txt not in test_types:
                        test_types.append(txt)
    
    # Strategy 2: Look for styled badges/keys near the product name
    if not test_types:
        for el in soup.find_all(class_=re.compile(r"product.*key|key.*badge|type.*badge|catalogue.*key", re.I)):
            txt = el.get_text(strip=True)
            if len(txt) == 1 and txt in "ABCDEKPS" and txt not in test_types:
                test_types.append(txt)
    
    # Strategy 3: Infer from product name/slug
    if not test_types:
        name_lower = p["name"].lower()
        slug_lower = slug.lower()
        
        # Knowledge & Skills tests (technology, domain knowledge)
        k_indicators = ["new)", "(new", "simulation", "programming", "development",
                       "engineering", "accounting", "administration", "microsoft",
                       "excel", "word", "sql", "java", "python", "angular", "react",
                       "docker", "aws", "linux", "networking", "statistics", "medical",
                       "hipaa", "safety", "svar", "typing", "data"]
        if any(kw in slug_lower for kw in k_indicators):
            test_types.append("K")
        
        # Simulations
        if "simulation" in slug_lower:
            test_types.append("S")
        
        # Personality
        p_indicators = ["opq", "personality", "questionnaire", "motivation", "dsi",
                       "dependability", "safety-and-dependability"]
        if any(kw in slug_lower for kw in p_indicators):
            test_types.append("P")
        
        # Ability & Aptitude
        a_indicators = ["verify", "reasoning", "ability", "aptitude", "cognitive",
                       "numerical", "verbal", "inductive", "deductive", "interactive-g"]
        if any(kw in slug_lower for kw in a_indicators):
            test_types.append("A")
        
        # Biodata & SJT
        b_indicators = ["scenario", "situational", "biodata", "graduate-scenario"]
        if any(kw in slug_lower for kw in b_indicators):
            test_types.append("B")
        
        # Competencies
        c_indicators = ["competenc", "global-skills", "ucf"]
        if any(kw in slug_lower for kw in c_indicators):
            test_types.append("C")
        
        # Development
        d_indicators = ["360", "development", "feedback", "report"]
        if any(kw in slug_lower for kw in d_indicators):
            test_types.append("D")
        
        # Solutions (pre-packaged)
        if "solution" in slug_lower and not test_types:
            test_types.extend(["P", "C"])
        
        # Default fallback
        if not test_types:
            if "-new" in slug_lower:
                test_types.append("K")
            else:
                test_types.append("K")  # Most products are K type
    
    p["testTypes"] = test_types

    # ── Remote / Adaptive ──
    p["remoteSupported"] = bool(re.search(r"Remote\s+(?:Testing|Proctoring)", full_text, re.I))
    p["adaptiveIRT"] = bool(re.search(r"Adaptive|IRT|Item Response", full_text, re.I))

    return p


def main():
    urls = [u.strip() for u in URL_FILE.read_text().splitlines() if u.strip()]
    print(f"[*] {len(urls)} URLs to scrape")

    # Use ThreadPoolExecutor for parallel fetching (5 threads)
    products = []
    errors = 0

    def process(url):
        html = fetch(url)
        if html:
            return parse(url, html)
        return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(process, url): url for url in urls}
        for i, future in enumerate(as_completed(futures)):
            url = futures[future]
            slug = url.strip().rstrip("/").split("/")[-1]
            try:
                result = future.result()
                if result:
                    products.append(result)
                    print(f"  [{i+1}/{len(urls)}] {slug:<45s} ✓  dur={result.get('duration_minutes')} types={result.get('testTypes')}")
                else:
                    errors += 1
                    print(f"  [{i+1}/{len(urls)}] {slug:<45s} ✗")
            except Exception as e:
                errors += 1
                print(f"  [{i+1}/{len(urls)}] {slug:<45s} ERR: {e}")

            # Checkpoint every 50
            if (i + 1) % 50 == 0:
                with open(OUT, "w") as f:
                    json.dump(products, f, indent=2, ensure_ascii=False)
                print(f"    --- Checkpoint: {len(products)} saved ---")

    # Sort by name
    products.sort(key=lambda p: p.get("name", ""))

    with open(OUT, "w") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Total: {len(products)} products saved ({errors} errors)")
    print(f"With description: {sum(1 for p in products if p.get('description'))}")
    print(f"With duration: {sum(1 for p in products if p.get('duration_minutes'))}")
    print(f"With job levels: {sum(1 for p in products if p.get('jobLevels'))}")
    print(f"With languages: {sum(1 for p in products if p.get('languages'))}")


if __name__ == "__main__":
    main()
