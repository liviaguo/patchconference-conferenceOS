"""ConferenceOS: explainable conference shortlist. Run: .venv/bin/streamlit run app/streamlit_app.py"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos import config  # noqa: E402
from conferenceos.discover import cache, live_scan  # noqa: E402
from conferenceos.graph.load import build, load_accounts  # noqa: E402
from conferenceos import icp_store  # noqa: E402
from conferenceos.agent.outreach import draft_batch  # noqa: E402
from conferenceos.graph import client  # noqa: E402
from conferenceos.graph.score import score_events  # noqa: E402

st.set_page_config(page_title="ConferenceOS", layout="wide")

PROV_BADGE = {"scraped": "Scraped", "estimated": "Estimated", "simulated": "Simulated"}
PROV_COLOR = {"scraped": "#4C8C6B", "estimated": "#C29B3E", "simulated": "#8A7BB0"}

CSS = """
<style>
  .block-container {max-width: 1180px; padding-top: 2.2rem;}
  h1 {font-weight: 600; letter-spacing: -0.02em; font-size: 2rem !important;}
  h2, h3 {font-weight: 600; letter-spacing: -0.01em;}
  [data-testid="stSidebar"] {border-right: 1px solid #E6E8EB;}
  .stTabs [data-baseweb="tab-list"] {gap: 1.5rem; border-bottom: 1px solid #E6E8EB;}
  .stTabs [data-baseweb="tab"] {padding: 0.4rem 0; font-weight: 500;}
  .stButton button, .stDownloadButton button {border-radius: 8px; border: 1px solid #D5D9DE; font-weight: 500;}
  [data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #E6E8EB; border-radius: 10px; padding: 0.8rem 1rem;}
  [data-testid="stExpander"] details {border: 1px solid #E6E8EB; border-radius: 10px; background: #FFFFFF;}
  .muted {color: #6B7280; font-size: 0.9rem;}
  .dot {display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
STALE_HOURS = 24


def badge(prov: str | None) -> str:
    return PROV_BADGE.get(prov or "", prov or "—")


def money(v) -> str:
    return "—" if v is None else f"${v:,.0f}"


@st.cache_data(ttl=60)
def load_scores(regions: tuple, date_from: str, date_to: str) -> list[dict]:
    return score_events(regions=list(regions), date_from=date_from, date_to=date_to)


def q(s: str) -> str:
    """Quote scraped text as a DOT identifier (names can contain quotes or backslashes)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def path_to_dot(event: str, why: list[str]) -> str:
    lines = ['digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#f4f4f5", fontname=Helvetica];',
             f'{q(event)} [fillcolor="#dbeafe"];']
    for w in why:
        w = re.sub(r" \((scraped|estimated|simulated)\)$", "", w)
        m = re.match(r"(.+) <-\[WORKS_AT\]- (.+) -\[SPEAKS_AT\]-> (.+)", w)
        if m:
            acct, person, ev = m.groups()
            lines += [f'{q(acct)} [fillcolor="#dcfce7"];', f'{q(person)} [shape=ellipse];',
                      f'{q(person)} -> {q(acct)} [label="WORKS_AT"];', f'{q(person)} -> {q(ev)} [label="SPEAKS_AT"];']
            continue
        m = re.match(r"(.+) -\[(\w+)\]-> (.+)", w)
        if m:
            acct, rel, ev = m.groups()
            style = ', style=dashed' if rel == "ATTENDS" else ""
            lines += [f'{q(acct)} [fillcolor="#dcfce7"];', f'{q(acct)} -> {q(ev)} [label="{rel}"{style}];']
    return "\n".join(lines + ["}"])


# ---------- header + data freshness ----------
st.title("ConferenceOS")
st.caption("Which Q1–Q2 2027 life-science conferences in the US and EU should LabFlow shortlist, and why?")

doc = cache.latest()
if not doc:
    st.error("No event data yet. Run `scripts/discover.py` then `scripts/seed_graph.py`.")
    st.stop()
fetched = datetime.fromisoformat(doc["fetched_at"])
age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
if age_h > STALE_HOURS:
    st.warning(f"Showing cached event data from {fetched:%Y-%m-%d %H:%M} UTC ({age_h:.0f}h old). Live scrape not refreshed.")
else:
    st.markdown(f"<p class='muted'>{len(doc['events'])} events scraped via Bright Data · "
                f"{fetched:%b %d, %H:%M} UTC · graph in FalkorDB</p>", unsafe_allow_html=True)
if doc.get("rejected"):
    with st.expander(f"{len(doc['rejected'])} scraped sources rejected by validation"):
        for x in doc["rejected"]:
            st.markdown(f"- **{x['series']}**: {x['reason']} ([source]({x['url']}))")

with st.sidebar:
    st.header("Filters")
    regions = st.multiselect("Regions", ["US", "EU"], default=config.REGIONS)
    # date pickers, not free text: scoring compares ISO date strings
    date_from = st.date_input("From", date.fromisoformat(config.DATE_FROM)).isoformat()
    date_to = st.date_input("To", date.fromisoformat(config.DATE_TO)).isoformat()
    st.markdown("---")
    st.markdown("**Data provenance**")
    for k, v in PROV_BADGE.items():
        st.markdown(f"<span class='dot' style='background:{PROV_COLOR[k]}'></span>{v}", unsafe_allow_html=True)
    st.caption("Pipeline and past-event outcomes are **simulated** LabFlow data.")
    st.markdown("---")
    use_reg = st.toggle("Factor in attendee lists (simulated)", value=False,
                        help="Masked organizer attendee lists (company + title, simulated). Adds weighted "
                             "credit for ICP accounts with registrants; real presence still counts fully.")
    reg_weight = st.slider("Attendee-list weight", 0.0, 1.0, 0.3, 0.05, disabled=not use_reg)

if not regions:
    st.warning("Select at least one region.")
    st.stop()
if date_from > date_to:
    st.warning("'From' date is after 'To' date.")
    st.stop()
tab_icp, tab_list, tab_why, tab_outreach = st.tabs(["Target accounts", "Shortlist", "Why", "Outreach"])

# ---------- ICP + live Bright Data scan ----------
ICP_COLS = ["name", "aliases", "segment", "tier", "region"]


def icp_records(df: pd.DataFrame) -> list[dict]:
    # keep original ids by name so simulated pipeline stays attached to the right company
    known = {a["name"]: a["account_id"] for a in load_accounts()}
    df = df.fillna("")
    recs = []
    for i, r in enumerate(df.to_dict("records")):
        if str(r.get("name", "")).strip():
            name = str(r["name"]).strip()
            recs.append({"account_id": known.get(name, f"N{i + 1:03d}"), "name": name,
                         "aliases": str(r.get("aliases") or ""), "domain": "", "segment": str(r.get("segment") or ""),
                         "tier": int(r.get("tier") or 3), "region": str(r.get("region") or "")})
    return recs


def rebuild(icp: list[dict]) -> dict:
    stats = build(client.get_graph(), doc, accounts=icp, live=live_scan.load_evidence())
    icp_store.save(icp)
    load_scores.clear()
    return stats


with tab_icp:
    st.subheader("Who do we want to meet?")
    st.caption("Edit the ICP target accounts: add a row, change tiers, add aliases (e.g. subsidiaries, `;`-separated). "
               "Then apply to re-score every event in the graph, or run a live Bright Data scan for fresh evidence.")
    if "icp_df" not in st.session_state:
        st.session_state.icp_df = pd.DataFrame(icp_store.load())[ICP_COLS]
    edited = st.data_editor(
        st.session_state.icp_df, num_rows="dynamic", use_container_width=True, hide_index=True, key="icp_editor",
        column_config={
            "name": st.column_config.TextColumn("Company", required=True),
            "aliases": st.column_config.TextColumn("Aliases / subsidiaries"),
            "segment": st.column_config.SelectboxColumn("Segment", options=["pharma", "biotech", "cro", "tools"]),
            "tier": st.column_config.NumberColumn("Tier", min_value=1, max_value=3, step=1),
            "region": st.column_config.SelectboxColumn("HQ region", options=["US", "EU"]),
        })
    icp = icp_records(edited)

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button(f"Apply ICP ({len(icp)} accounts) & re-score", use_container_width=True):
            with st.spinner("Rebuilding graph in FalkorDB…"):
                stats = rebuild(icp)
            st.session_state.icp_df = edited
            st.toast(f"Graph rebuilt: {stats['accounts']} target accounts, {stats['events']} events")
    with c2:
        names = [a["name"] for a in icp]
        prev_scanned = {x["account"] for x in live_scan.load_evidence()}
        to_scan = st.multiselect("Accounts to scan live", names,
                                 default=[n for n in names if n not in prev_scanned][:8] or names[:8])

    if st.button("Run live scan with Bright Data", disabled=not to_scan):
        events_in_scope = doc["events"]
        found: list[dict] = []
        with st.status(f"Scanning {len(to_scan)} accounts across {len(events_in_scope)} events via Bright Data SERP…",
                       expanded=True) as status:
            for res in live_scan.scan(to_scan, events_in_scope):
                if res.get("error"):
                    st.write(f"**{res['account']}**: {res['error']}")
                    continue
                hits = ", ".join(f"{m['relation']} @ {m['event']}" for m in res["matches"]) or "no verifiable 2027 evidence"
                st.write(f"{'✓' if res['matches'] else '–'} **{res['account']}**: {res['n_results']} results "
                         f"in {res['seconds']:.1f}s → {hits}")
                found += res["matches"]
            status.update(label=f"Live scan done: {len(found)} verified links. Updating graph…", state="running")
            evidence = live_scan.load_evidence()
            seen = {(x["account"], x["event_id"], x["relation"], x["source_url"]) for x in evidence}
            evidence += [m for m in found if (m["account"], m["event_id"], m["relation"], m["source_url"]) not in seen]
            live_scan.save_evidence(evidence)
            rebuild(icp)
            st.session_state.icp_df = edited
            status.update(label=f"Live scan done: {len(found)} verified links added to the graph and re-scored.",
                          state="complete")

    evidence = live_scan.load_evidence()
    if evidence:
        st.markdown(f"**Live evidence in graph** ({len(evidence)}): each one quoted verbatim from a Bright Data search result")
        st.dataframe(pd.DataFrame([{
            "Account": x["account"], "Event": x["event"], "Link": x["relation"], "Person": x.get("person") or "",
            "Quote": x["quote"], "Source": x["source_url"], "Fetched": x["fetched_at"],
        } for x in evidence]), hide_index=True, use_container_width=True,
            column_config={"Source": st.column_config.LinkColumn("Source")})

rows = load_scores(tuple(regions), date_from, date_to)
for r in rows:
    # blended reach: confirmed presence + weighted simulated registrant accounts not already present
    extra = max((r.get("registered_accounts_sim") or 0) - r["accounts_present"], 0) if use_reg else 0
    r["blended_per_10k"] = ((r["accounts_present"] + reg_weight * extra) * 10000.0 / r["cost"]) if r["cost"] else 0
if use_reg:
    rows.sort(key=lambda r: r["blended_per_10k"], reverse=True)
if not rows:
    with tab_list:
        st.warning("No events in this window/region.")
    st.stop()

# ---------- shortlist ----------
with tab_list:
    df = pd.DataFrame([{
        "Rank": i + 1,
        "Event": r["event"],
        "Region": r["region"],
        "Starts": r["start_date"],
        "City": r["city"],
        "ICP accounts": r["accounts_present"],
        "Density": f"{r['density']:.0%}",
        "Total cost": money(r["cost"]),
        "Accounts / $10k": round(r["reached_per_10k"] or 0, 2),
        "Pipeline at event (simulated)": money(r["simulated_pipeline_usd"]),
        "ICP accts on attendee list (simulated)": r.get("registered_accounts_sim") or 0,
        **({"Blended / $10k": round(r["blended_per_10k"], 2)} if use_reg else {}),
        "Cost has estimates": "yes" if "estimated" in (r["pass_price_prov"], r["booth_price_prov"], r["travel_est_prov"]) else "no",
    } for i, r in enumerate(rows)])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(("Ranked by blended reach: confirmed ICP accounts + "
                f"{reg_weight:.2f} × extra ICP accounts on the simulated attendee list, per $10k. ")
               if use_reg else
               "Ranked by ICP target accounts reached per $10k. Density = ICP accounts present / total ICP accounts.")

# ---------- why panel ----------
with tab_why:
    names = [f"{i + 1}. {r['event']}" for i, r in enumerate(rows)]
    pick = st.selectbox("Event", names)
    r = rows[names.index(pick)]
    st.session_state["top_event"] = r

    c1, c2, c3 = st.columns(3)
    c1.metric("ICP accounts present", r["accounts_present"], f"{r['density']:.0%} of ICP")
    c2.metric("Total cost", money(r["cost"]))
    c3.metric("Accounts per $10k", f"{r['reached_per_10k'] or 0:.2f}")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Why: graph paths")
        if r["why"]:
            st.graphviz_chart(path_to_dot(r["event"], r["why"]))
            for w in r["why"]:
                st.markdown(f"- `{w}`")
        else:
            st.caption("No target accounts found at this event yet (sponsor and speaker lists may not be published).")
    with right:
        st.subheader("Cost breakdown")
        st.dataframe(pd.DataFrame([
            {"Item": "Passes", "USD": money(r["pass_price"]), "Source": badge(r["pass_price_prov"]), "Note": r["pass_price_note"]},
            {"Item": "Booth / sponsorship", "USD": money(r["booth_price"]), "Source": badge(r["booth_price_prov"]), "Note": r["booth_price_note"]},
            {"Item": "Travel", "USD": money(r["travel_est"]), "Source": badge(r["travel_est_prov"]), "Note": r["travel_est_note"]},
        ]), hide_index=True, use_container_width=True)
        st.markdown(f"**Simulated pipeline on present accounts:** {money(r['simulated_pipeline_usd'])}")
        st.markdown(f"[Event page]({r['url']}) · scraped {r['fetched_at']}")

# ---------- outreach ----------
with tab_outreach:
    names = [f"{i + 1}. {r['event']}" for i, r in enumerate(rows) if r["accounts"]]
    if not names:
        st.write("No ICP accounts found at any shortlisted event yet.")
        st.stop()
    pick = st.selectbox("Event", names, key="outreach_event")
    top = rows[int(pick.split(".")[0]) - 1]
    st.caption("One draft per ICP account present, each grounded in the graph path that puts the account there. "
               "Drafts are for review and editing; nothing is sent from here.")
    drafts_by_event = st.session_state.setdefault("drafts", {})
    if st.button(f"Draft {len(top['accounts'])} emails"):
        opp_accts = {x["name"] for x in client.query(
            "MATCH (a:Account)-[:IN_PIPELINE]->(:Opportunity) WHERE a.name IN $names RETURN DISTINCT a.name AS name",
            {"names": top["accounts"]})}
        with st.spinner("Drafting…"):
            drafts_by_event[top["event_id"]] = draft_batch(top, opp_accts)
    drafts = drafts_by_event.get(top["event_id"])
    if drafts:
        export = []
        for i, d in enumerate(drafts):
            with st.expander(f"{d['account']}  ·  owner: {d.get('owner', '?')}", expanded=i == 0):
                if d.get("error"):
                    st.error(f"Draft failed: {d['error']}")
                st.caption("Evidence: " + " · ".join(d.get("evidence", [])))
                # keys include the event so text never carries over between events
                k = f"{top['event_id']}-{i}"
                subj = st.text_input("Subject", d["subject"], key=f"s-{k}")
                body = st.text_area("Body", d["body"], key=f"b-{k}", height=200)
                export.append({"account": d["account"], "owner": d.get("owner"), "subject": subj, "body": body,
                               "evidence": " | ".join(d.get("evidence", []))})
        st.download_button("Download drafts (CSV)", pd.DataFrame(export).to_csv(index=False),
                           file_name=f"{top['event_id']}-outreach.csv", mime="text/csv")
