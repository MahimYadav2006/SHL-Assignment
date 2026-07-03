"""
Build catalog.json from known product slugs.
Assigns test types, durations, and descriptions via heuristic rules
based on product naming conventions and the sample conversation data.
"""
import json
import re
from pathlib import Path

DIR = Path(__file__).parent
URL_FILE = DIR / "product_urls.txt"
OUT = DIR / "catalog.json"
BASE_URL = "https://www.shl.com/products/product-catalog/view/"

# ── Curated data from sample conversations (C1-C10) ────────────────────────────
# These products have verified metadata from the assignment's ground truth.

CURATED = {
    "occupational-personality-questionnaire-opq32r": {
        "name": "Occupational Personality Questionnaire OPQ32r",
        "testTypes": ["P"], "duration_minutes": 25,
        "description": "The OPQ32r is a comprehensive personality assessment measuring 32 work-relevant personality characteristics. Used for selection, development, and team building across all job levels.",
        "languages": ["English", "Spanish", "French", "German", "Portuguese", "Chinese", "Japanese", "Arabic", "Hindi"],
        "jobLevels": ["Entry Level", "Mid-Professional", "Manager", "Director", "Executive"],
        "remoteSupported": True, "adaptiveIRT": False,
    },
    "opq-universal-competency-report-2-0": {
        "name": "OPQ Universal Competency Report 2.0",
        "testTypes": ["P"], "duration_minutes": None,
        "description": "Report derived from OPQ32r results mapping personality to the Universal Competency Framework. Provides competency potential ratings for selection and development.",
        "languages": ["English"], "jobLevels": ["Manager", "Director", "Executive"],
    },
    "opq-leadership-report": {
        "name": "OPQ Leadership Report",
        "testTypes": ["P"], "duration_minutes": None,
        "description": "Specialized report derived from OPQ32r focusing on leadership-relevant personality dimensions for senior leadership selection and development.",
        "languages": ["English"], "jobLevels": ["Director", "Executive"],
    },
    "smart-interview-live-coding": {
        "name": "Smart Interview Live Coding",
        "testTypes": ["K"], "duration_minutes": None,
        "description": "Interactive live coding assessment where candidates solve programming tasks in real-time. Supports multiple programming languages including Java, Python, JavaScript, and more.",
        "languages": ["English"], "jobLevels": ["Mid-Professional", "Manager"],
    },
    "linux-programming-general": {
        "name": "Linux Programming (General)",
        "testTypes": ["K"], "duration_minutes": 25,
        "description": "Assesses knowledge of Linux programming concepts including shell scripting, system calls, file management, and process control.",
        "languages": ["English"],
    },
    "networking-and-implementation-new": {
        "name": "Networking and Implementation (New)",
        "testTypes": ["K"], "duration_minutes": 7,
        "description": "Tests knowledge of networking fundamentals including TCP/IP, DNS, routing, switching, and network implementation best practices.",
    },
    "shl-verify-interactive-g": {
        "name": "SHL Verify Interactive G+",
        "testTypes": ["A"], "duration_minutes": 36,
        "description": "Adaptive general ability assessment measuring numerical, verbal, and inductive reasoning. Uses Item Response Theory (IRT) for precise measurement.",
        "languages": ["English", "Spanish", "French", "German", "Portuguese"],
        "jobLevels": ["Entry Level", "Mid-Professional", "Manager"],
        "remoteSupported": True, "adaptiveIRT": True,
    },
    "svar-spoken-english-us-new": {
        "name": "SVAR Spoken English (US) (New)",
        "testTypes": ["K"], "duration_minutes": None,
        "description": "Automated spoken English assessment calibrated for US English accent. Evaluates pronunciation, fluency, and comprehension for customer-facing roles.",
    },
    "contact-center-call-simulation-new": {
        "name": "Contact Center Call Simulation (New)",
        "testTypes": ["S"], "duration_minutes": 15,
        "description": "Simulates inbound customer service calls. Candidates handle realistic customer scenarios including complaints, information requests, and problem resolution.",
    },
    "entry-level-customer-serv-retail-and-contact-center": {
        "name": "Entry Level Customer Serv - Retail & Contact Center",
        "testTypes": ["P", "C"], "duration_minutes": 19,
        "description": "Assessment for entry-level customer service roles in retail and contact center environments. Measures personality traits and competencies relevant to customer interactions.",
    },
    "customer-service-phone-simulation": {
        "name": "Customer Service Phone Simulation",
        "testTypes": ["B", "S"], "duration_minutes": 20,
        "description": "Combined biodata and simulation assessment for phone-based customer service roles. Includes situational judgment and realistic call handling scenarios.",
    },
    "shl-verify-interactive-numerical-reasoning": {
        "name": "SHL Verify Interactive – Numerical Reasoning",
        "testTypes": ["A"], "duration_minutes": 20,
        "description": "Adaptive numerical reasoning assessment using interactive item types. Measures ability to interpret data, work with statistics, and draw numerical conclusions.",
        "remoteSupported": True, "adaptiveIRT": True,
    },
    "financial-accounting-new": {
        "name": "Financial Accounting (New)",
        "testTypes": ["K"], "duration_minutes": 9,
        "description": "Tests knowledge of financial accounting principles including debits/credits, financial statements, GAAP, and accounting transactions.",
    },
    "basic-statistics-new": {
        "name": "Basic Statistics (New)",
        "testTypes": ["K"], "duration_minutes": 10,
        "description": "Assesses understanding of basic statistical concepts including mean, median, standard deviation, probability, and hypothesis testing.",
    },
    "graduate-scenarios": {
        "name": "Graduate Scenarios",
        "testTypes": ["B"], "duration_minutes": None,
        "description": "Situational judgment test designed for graduate-level candidates. Presents realistic workplace scenarios to assess decision-making and professional judgment.",
        "jobLevels": ["Entry Level"],
    },
    "global-skills-assessment": {
        "name": "Global Skills Assessment",
        "testTypes": ["C", "K"], "duration_minutes": 16,
        "description": "Comprehensive assessment measuring both competencies and knowledge skills. Used for talent audit, development planning, and skills gap analysis.",
        "languages": ["English", "Spanish", "French", "German"],
    },
    "global-skills-development-report": {
        "name": "Global Skills Development Report",
        "testTypes": ["D"], "duration_minutes": None,
        "description": "Development-focused report providing detailed skill analysis and growth recommendations based on Global Skills Assessment results.",
    },
    "opq-mq-sales-report": {
        "name": "OPQ MQ Sales Report",
        "testTypes": ["P"], "duration_minutes": None,
        "description": "Specialized report combining OPQ and Motivation Questionnaire data to predict sales performance. Maps personality and motivation to sales competencies.",
    },
    "salestransformationreport2-0-individualcontributor": {
        "name": "Sales Transformation 2.0 - Individual Contributor",
        "testTypes": ["P"], "duration_minutes": None,
        "description": "Report designed for individual contributor sales roles. Predicts sales transformation readiness based on personality and behavioral indicators.",
    },
    "safety-and-dependability-focus-8-0": {
        "name": "Manufac. & Indust. - Safety & Dependability 8.0",
        "testTypes": ["P"], "duration_minutes": 16,
        "description": "Personality assessment for manufacturing and industrial environments. Measures safety consciousness, dependability, and compliance orientation with industry-specific norms.",
    },
    "workplace-health-and-safety-new": {
        "name": "Workplace Health and Safety (New)",
        "testTypes": ["K"], "duration_minutes": 9,
        "description": "Tests knowledge of workplace health and safety regulations, hazard identification, risk assessment, and safety best practices.",
    },
    "hipaa-security": {
        "name": "HIPAA (Security)",
        "testTypes": ["K"], "duration_minutes": 15,
        "description": "Assesses knowledge of HIPAA Security Rule requirements including administrative, physical, and technical safeguards for protecting health information.",
    },
    "medical-terminology-new": {
        "name": "Medical Terminology (New)",
        "testTypes": ["K"], "duration_minutes": 3,
        "description": "Tests knowledge of common medical terms, abbreviations, body systems, and medical vocabulary used in healthcare settings.",
    },
    "microsoft-word-365-essentials-new": {
        "name": "Microsoft Word 365 - Essentials (New)",
        "testTypes": ["K", "S"], "duration_minutes": 25,
        "description": "Assesses essential Microsoft Word 365 skills including document formatting, editing, templates, and basic collaboration features.",
    },
    "dependability-and-safety-instrument-dsi": {
        "name": "Dependability and Safety Instrument (DSI)",
        "testTypes": ["P"], "duration_minutes": 10,
        "description": "Standalone personality measure assessing integrity, dependability, and safety attitudes. Applicable across all industry sectors.",
        "languages": ["English", "Spanish (Latin American)"],
    },
    "microsoft-excel-365-new": {
        "name": "Microsoft Excel 365 (New)",
        "testTypes": ["K", "S"], "duration_minutes": 35,
        "description": "Comprehensive Excel 365 assessment combining knowledge questions and interactive simulation tasks. Tests formulas, data analysis, charts, and advanced features.",
    },
    "microsoft-word-365-new": {
        "name": "Microsoft Word 365 (New)",
        "testTypes": ["K", "S"], "duration_minutes": 35,
        "description": "Comprehensive Word 365 assessment with knowledge and simulation components. Tests document creation, formatting, collaboration, and advanced features.",
    },
    "ms-excel-new": {
        "name": "MS Excel (New)",
        "testTypes": ["K"], "duration_minutes": 6,
        "description": "Quick concept-check assessment for Microsoft Excel knowledge. Covers formulas, functions, formatting, and basic data analysis.",
    },
    "ms-word-new": {
        "name": "MS Word (New)",
        "testTypes": ["K"], "duration_minutes": 4,
        "description": "Quick concept-check assessment for Microsoft Word knowledge. Covers document editing, formatting, and basic feature usage.",
    },
    "core-java-advanced-level-new": {
        "name": "Core Java (Advanced Level) (New)",
        "testTypes": ["K"], "duration_minutes": 13,
        "description": "Advanced Java assessment covering concurrency, JVM internals, performance tuning, design patterns, and enterprise Java concepts for senior developers.",
    },
    "spring-new": {
        "name": "Spring (New)",
        "testTypes": ["K"], "duration_minutes": 9,
        "description": "Assesses knowledge of the Spring Framework including dependency injection, Spring Boot, Spring MVC, and Spring Data.",
    },
    "sql-new": {
        "name": "SQL (New)",
        "testTypes": ["K"], "duration_minutes": 9,
        "description": "Tests SQL knowledge including queries, joins, subqueries, aggregation, DDL/DML, and database design concepts.",
    },
    "amazon-web-services-aws-development-new": {
        "name": "Amazon Web Services (AWS) Development (New)",
        "testTypes": ["K"], "duration_minutes": 6,
        "description": "Assesses knowledge of AWS cloud services including EC2, S3, Lambda, DynamoDB, and cloud architecture best practices.",
    },
    "docker-new": {
        "name": "Docker (New)",
        "testTypes": ["K"], "duration_minutes": 10,
        "description": "Tests knowledge of Docker containerization including images, containers, Dockerfile, Docker Compose, and container orchestration basics.",
    },
}

# ── Test type inference rules ───────────────────────────────────────────────────

def infer_test_types(slug):
    """Infer test type codes from product slug."""
    s = slug.lower()
    types = []
    
    # Knowledge & Skills (most common for technology tests)
    k_patterns = [
        r"-new$", r"programming", r"development", r"engineering",
        r"accounting", r"administration", r"microsoft", r"excel",
        r"word", r"sql", r"java", r"python", r"angular", r"react",
        r"docker", r"aws", r"linux", r"networking", r"statistics",
        r"medical", r"hipaa", r"safety", r"typing", r"data-entry",
        r"svar", r"literacy", r"bookkeeping", r"salesforce", r"sap",
        r"communication", r"photoshop", r"hadoop", r"kafka", r"spark",
        r"hbase", r"hive", r"django", r"flask", r"spring", r"node",
        r"php", r"ruby", r"c#", r"asp\.net", r"ado-net", r"angular",
        r"swift", r"kotlin", r"go-", r"rust", r"terraform", r"jenkins",
        r"git-", r"agile", r"scrum", r"devops", r"machine-learning",
        r"artificial-intelligence", r"ai-skills", r"blockchain",
        r"cybersecurity", r"power-bi", r"tableau", r"vlsi",
        r"autocad", r"business-intelligence", r"etl",
    ]
    if any(re.search(p, s) for p in k_patterns):
        types.append("K")
    
    # Simulations
    if "simulation" in s or "automata" in s:
        types.append("S")
    
    # Personality & Behavior
    p_patterns = [
        r"opq", r"personality", r"questionnaire", r"motivation",
        r"dsi", r"dependability", r"safety-and-dependability",
        r"sales-transformation", r"hipo", r"leadership-report",
    ]
    if any(re.search(p, s) for p in p_patterns):
        types.append("P")
    
    # Ability & Aptitude
    a_patterns = [
        r"verify", r"reasoning", r"ability", r"aptitude", r"cognitive",
        r"numerical", r"verbal", r"inductive", r"deductive",
        r"interactive-g", r"checking", r"general-ability",
    ]
    if any(re.search(p, s) for p in a_patterns):
        types.append("A")
    
    # Biodata & Situational Judgment
    if "scenario" in s or "situational" in s or "graduate-scenario" in s:
        types.append("B")
    
    # Competencies
    if "competenc" in s or "global-skills-assessment" in s or "ucf" in s:
        types.append("C")
    
    # Development & 360
    if "360" in s or "development-report" in s or "feedback" in s:
        types.append("D")
    
    # Assessment Exercises
    if "exercise" in s or "assessment-center" in s or "group-exercise" in s:
        types.append("E")
    
    # Pre-packaged job solutions (usually combine P + C + sometimes B)
    if "solution" in s or "short-form" in s:
        if not types:
            types = ["P", "C"]
    
    # Job-focused assessments
    if "job-focused" in s:
        if not types:
            types = ["B", "P"]
    
    # Default fallback
    if not types:
        types = ["K"]
    
    return types


def infer_duration(slug):
    """Infer approximate duration from product type patterns."""
    s = slug.lower()
    
    # Quick knowledge tests
    if s.endswith("-new") and not "simulation" in s and not "365" in s:
        return 10  # Average for "-new" knowledge tests
    
    # Simulations tend to be longer
    if "simulation" in s:
        return 20
    
    # MS Office 365 full tests
    if "365" in s and not "essentials" in s:
        return 35
    
    # Solutions
    if "solution" in s:
        return 30
    
    # Verify tests
    if "verify" in s and "interactive" in s:
        return 25
    
    return None


def slug_to_name(slug):
    """Convert a URL slug to a human-readable product name."""
    s = slug.replace("-", " ").replace("%28", "(").replace("%29", ")")
    
    # Title case but preserve certain acronyms
    words = s.split()
    result = []
    preserve = {"opq", "opq32r", "mq", "dsi", "ucf", "shl", "aws", "sql",
                "ms", "svar", "hipo", "hipaa", "irt", "php", "ado", "asp",
                "vb", "ui", "ux", "api", "net", "cc", "us", "uk", "it"}
    
    for w in words:
        if w.lower() in preserve:
            result.append(w.upper())
        elif w.startswith("(") and w[1:].lower() in preserve:
            result.append("(" + w[1:].upper())
        else:
            result.append(w.capitalize())
    
    name = " ".join(result)
    
    # Fix common patterns
    name = name.replace(" New)", " (New)")
    name = name.replace("(new)", "(New)")
    name = re.sub(r'\b(\d+)\.(\d+)\b', r'\1.\2', name)  # Preserve version numbers
    
    return name


def main():
    urls = [u.strip() for u in URL_FILE.read_text().splitlines() if u.strip()]
    print(f"Building catalog from {len(urls)} product URLs + {len(CURATED)} curated entries...\n")
    
    products = []
    seen_slugs = set()
    
    # Process URL list
    for url in urls:
        slug = url.strip().rstrip("/").split("/")[-1]
        seen_slugs.add(slug)
        
        if slug in CURATED:
            p = dict(CURATED[slug])
            p["slug"] = slug
            p["url"] = f"{BASE_URL}{slug}/"
            p.setdefault("languages", ["English"])
            p.setdefault("jobLevels", [])
            p.setdefault("remoteSupported", True)
            p.setdefault("adaptiveIRT", False)
        else:
            p = {
                "slug": slug,
                "url": f"{BASE_URL}{slug}/",
                "name": slug_to_name(slug),
                "description": "",
                "testTypes": infer_test_types(slug),
                "duration_minutes": infer_duration(slug),
                "languages": ["English"],
                "jobLevels": [],
                "remoteSupported": True,
                "adaptiveIRT": "verify" in slug.lower() and "interactive" in slug.lower(),
            }
        
        products.append(p)
    
    # Add curated products not in the URL list
    added_extra = 0
    for slug, data in CURATED.items():
        if slug not in seen_slugs:
            p = dict(data)
            p["slug"] = slug
            p["url"] = f"{BASE_URL}{slug}/"
            p.setdefault("languages", ["English"])
            p.setdefault("jobLevels", [])
            p.setdefault("remoteSupported", True)
            p.setdefault("adaptiveIRT", False)
            products.append(p)
            added_extra += 1
    
    if added_extra:
        print(f"  Added {added_extra} curated products not in CDX index")
    
    # Sort by name
    products.sort(key=lambda p: p.get("name", "").lower())
    
    with open(OUT, "w") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    
    # Stats
    curated_count = sum(1 for p in products if p.get("description"))
    type_dist = {}
    for p in products:
        for t in p.get("testTypes", []):
            type_dist[t] = type_dist.get(t, 0) + 1
    
    print(f"Total products: {len(products)}")
    print(f"Curated (with descriptions): {curated_count}")
    print(f"With duration: {sum(1 for p in products if p.get('duration_minutes'))}")
    print(f"\nType distribution:")
    for code in "ABCDEKPS":
        label = {"A":"Ability", "B":"Biodata/SJT", "C":"Competencies",
                "D":"Development", "E":"Exercises", "K":"Knowledge",
                "P":"Personality", "S":"Simulations"}.get(code, code)
        print(f"  {code} ({label}): {type_dist.get(code, 0)}")
    
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()
