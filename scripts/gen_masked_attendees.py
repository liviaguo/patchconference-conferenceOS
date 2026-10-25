"""Generate a SIMULATED masked attendee list (company + title only, no names), fixed seed.

Mimics what organizers share with exhibitors: one row per registrant, messy company
spellings and free-text titles, so entity resolution and title bucketing get exercised.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.config import DATA  # noqa: E402

rng = random.Random(7)
accounts = list(csv.DictReader(open(DATA / "icp_accounts.csv")))
seeds = list(csv.DictReader(open(DATA / "event_seeds.csv")))
YEAR = 2026  # last completed edition

# Rough relative audience size per series (sampled, not true headcounts)
SIZE = {
    "SLAS International Conference": 320, "SLAS Europe": 180, "Bio-IT World Conference & Expo": 260,
    "BIO International Convention": 340, "BIO-Europe Spring": 220, "AACR Annual Meeting": 340,
    "Pittcon": 220, "PEGS Boston": 200, "ASGCT Annual Meeting": 260, "Biotech Showcase": 160,
    "Festival of Genomics": 180, "Paperless Lab Academy": 90,
    "Society of Toxicology Annual Meeting": 200, "CPHI Americas": 160,
}

# Function -> title stems
TITLES = {
    "research": ["Scientist", "Research Scientist", "Principal Scientist", "Postdoctoral Fellow",
                 "Group Leader", "Assay Development Scientist"],
    "lab_ops": ["Lab Manager", "Laboratory Operations Manager", "Lab Technician",
                "Automation Engineer", "Lab Automation Specialist", "Research Operations Lead"],
    "informatics": ["Bioinformatician", "Data Scientist", "Computational Biologist", "Scientific Informatics Lead",
                    "LIMS Administrator", "ELN Product Owner", "Research Data Architect"],
    "quality": ["QA Specialist", "QC Analyst", "Quality Control Manager", "Validation Engineer",
                "GxP Compliance Lead"],
    "bd": ["Business Development Manager", "Partnering Manager", "Alliance Manager",
           "Search & Evaluation Lead", "Licensing Director"],
    "exec": ["CEO", "CSO", "CTO", "Founder", "Chief Digital Officer", "SVP Research"],
    "procurement": ["Strategic Sourcing Manager", "Category Manager, Lab Services", "Procurement Lead"],
    "sales": ["Account Executive", "Field Application Scientist", "Sales Director", "Marketing Manager"],
    "student": ["PhD Student", "Graduate Student", "Postdoc"],
}

# Topic -> function weights (topics come from event_seeds.csv)
TOPIC_MIX = {
    "lab automation": {"lab_ops": 4, "research": 3, "informatics": 2, "sales": 2, "exec": 1},
    "lab informatics": {"informatics": 5, "lab_ops": 3, "quality": 2, "research": 1, "sales": 1},
    "AI in drug discovery": {"informatics": 4, "research": 3, "exec": 1, "sales": 1},
    "biopharma partnering": {"bd": 6, "exec": 2, "research": 1, "sales": 1},
    "oncology research": {"research": 6, "student": 3, "exec": 1, "sales": 1},
    "analytical chemistry": {"research": 3, "quality": 3, "lab_ops": 2, "sales": 2, "student": 1},
    "biologics": {"research": 5, "lab_ops": 1, "bd": 1, "sales": 1},
    "protein engineering": {"research": 5, "informatics": 1, "student": 1},
    "cell and gene therapy": {"research": 5, "quality": 1, "bd": 1, "student": 2, "exec": 1},
    "genomics": {"research": 4, "informatics": 4, "student": 1, "sales": 1},
    "toxicology": {"research": 5, "quality": 2, "student": 2},
    "preclinical": {"research": 4, "lab_ops": 1, "quality": 1},
    "pharma manufacturing": {"quality": 4, "procurement": 3, "lab_ops": 2, "bd": 1, "sales": 2},
    "CDMO": {"bd": 3, "procurement": 3, "quality": 2, "sales": 2},
}

SENIORITY = {"": 6, "Senior ": 3, "Sr. ": 2, "Associate ": 1.5}  # prefixes for IC titles
LEADERSHIP = {"Assoc. Director": 3, "Director": 3, "Head of": 2, "Sr. Director": 1.5, "VP": 1}
AREA = {  # function -> what a leadership title says it runs
    "research": ["Discovery Biology", "Translational Research", "Biologics", "Assay Development"],
    "lab_ops": ["Lab Operations", "Lab Automation", "Research Operations"],
    "informatics": ["R&D IT", "Scientific Informatics", "Data Science", "Research Data"],
    "quality": ["Quality Assurance", "Quality Control", "Compliance"],
    "bd": ["Business Development", "Search & Evaluation", "Licensing"],
    "procurement": ["Procurement", "Strategic Sourcing"],
    "sales": ["Sales", "Marketing"],
}

# Non-ICP organizations (real names; registrations are simulated)
OTHER_US = ["Pfizer", "Merck & Co.", "Bristol Myers Squibb", "Eli Lilly and Company", "AbbVie",
            "Johnson & Johnson Innovative Medicine", "Agilent Technologies", "Waters Corporation",
            "Revvity", "Benchling", "Emerald Cloud Lab", "Insitro", "Generate:Biomedicines",
            "Harvard Medical School", "Broad Institute", "MIT", "Stanford University",
            "UCSF", "Dana-Farber Cancer Institute", "Memorial Sloan Kettering", "NIH / NCI",
            "Scripps Research", "Labcorp", "IQVIA", "WuXi AppTec", "Catalent"]
OTHER_EU = ["Boehringer Ingelheim", "Ipsen", "Servier", "Almirall", "Lundbeck", "Galapagos",
            "Sartorius", "Eppendorf", "QIAGEN", "Tecan", "Hamilton Bonaduz", "IDBS", "LabVantage",
            "Wellcome Sanger Institute", "Francis Crick Institute", "University of Cambridge",
            "Karolinska Institutet", "ETH Zurich", "EMBL", "Institut Pasteur", "Max Planck Institute",
            "KU Leuven", "Oxford University", "Recipharm", "Siegfried", "Cambrex"]
EU_COUNTRIES = ["GB", "DE", "CH", "FR", "NL", "BE", "DK", "SE", "ES", "IT", "IE", "AT"]
SUFFIX = {"US": [", Inc.", " Inc", ""], "CH": [" AG", " Ltd", ""], "DE": [" GmbH", " SE", " AG", ""],
          "GB": [" plc", " Ltd", ""], "FR": [" SA", ""], "DK": [" A/S", ""], "NL": [" N.V.", ""],
          "BE": [" SA", ""]}


def pick(weights: dict) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def messy_company(a: dict) -> str:
    """Spell an ICP account the way registrants type it."""
    names = [a["name"]] + [x for x in a["aliases"].split(";") if x]
    name = rng.choice(names)
    r = rng.random()
    if r < 0.25:
        name += rng.choice(SUFFIX.get(a["hq_country"], [""]))
    elif r < 0.32:
        name = name.upper()
    elif r < 0.37:
        name = a["domain"].split(".")[0]
    return name


def title_for(function: str) -> str:
    stem = rng.choice(TITLES[function])
    if function in ("exec", "student") or stem.startswith(("Head", "Postdoc", "Founder")):
        return stem
    if rng.random() < 0.15:
        lead = pick(LEADERSHIP)
        t = f"{lead} {rng.choice(AREA[function])}" if lead == "Head of" else f"{lead}, {rng.choice(AREA[function])}"
    else:
        t = pick(SENIORITY) + stem
    if rng.random() < 0.08:
        t = t.lower()
    return t


def mix_for(topics: list) -> dict:
    mix: dict = {}
    for tp in topics:
        for k, v in TOPIC_MIX.get(tp, {"research": 1}).items():
            mix[k] = mix.get(k, 0) + v
    return mix


out = DATA / "synthetic"
out.mkdir(exist_ok=True)
rows = []
for s in seeds:
    region = s["region_hint"]
    topics = s["topics"].split(";")
    mix = mix_for(topics)
    # Each event favors ICP accounts in its region; tools/CRO vendors show up everywhere
    icp_weights = [
        (3 if a["region"] == region else 1) * (2 if a["segment"] in ("tools", "cro") else 1)
        * {"1": 3, "2": 2, "3": 1}[a["tier"]] * rng.uniform(0.2, 1.8)
        for a in accounts
    ]
    icp_share = rng.uniform(0.18, 0.35)
    others = OTHER_US + OTHER_EU[:8] if region == "US" else OTHER_EU + OTHER_US[:8]
    academic = [o for o in others if any(
        w in o for w in ("Univ", "Institut", "MIT", "UCSF", "School", "EMBL", "ETH", "KU ", "Kettering"))]
    for _ in range(SIZE.get(s["series"], 150)):
        function = pick(mix)
        if function == "student" and rng.random() < 0.7:
            company = rng.choice(academic)
            country = "US" if company in OTHER_US else rng.choice(EU_COUNTRIES)
        elif rng.random() < icp_share:
            a = rng.choices(accounts, weights=icp_weights)[0]
            company = messy_company(a)
            country = a["hq_country"] if rng.random() < 0.7 else (
                "US" if region == "US" else rng.choice(EU_COUNTRIES))
        else:
            company = rng.choice(others)
            country = "US" if company in OTHER_US else rng.choice(EU_COUNTRIES)
        title = title_for(function)
        if rng.random() < 0.04:
            title = ""  # registrants skip optional fields
        rows.append([s["series"], YEAR, company, title, country, "true"])

rng.shuffle(rows)
rows.sort(key=lambda r: r[0])
with open(out / "masked_attendees.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["series", "year", "company", "title", "country", "simulated"])
    w.writerows(rows)

print("Wrote", out / "masked_attendees.csv", f"({len(rows)} rows, {len(seeds)} events)")
