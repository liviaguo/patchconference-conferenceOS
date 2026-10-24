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
from conferenceos.discover import cache  # noqa: E402
from conferenceos.agent.outreach import draft_batch  # noqa: E402
from conferenceos.approvals import gate  # noqa: E402
from conferenceos.graph import client  # noqa: E402
from conferenceos.graph.score import score_events  # noqa: E402

st.set_page_config(page_title="ConferenceOS", layout="wide")

PROV_BADGE = {"scraped": "🟢 scraped", "estimated": "🟡 estimated", "simulated": "🟣 simulated"}
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
    st.warning(f"⚠️ Showing cached event data from {fetched:%Y-%m-%d %H:%M} UTC ({age_h:.0f}h old). Live scrape not refreshed.")
else:
    st.info(f"Event data scraped via Bright Data at {fetched:%Y-%m-%d %H:%M} UTC · {len(doc['events'])} events")
if doc.get("rejected"):
    with st.expander(f"🚫 {len(doc['rejected'])} scraped sources rejected by validation"):
        for x in doc["rejected"]:
            st.markdown(f"- **{x['series']}**: {x['reason']} ([source]({x['url']}))")

with st.sidebar:
    st.header("Filters")
    regions = st.multiselect("Regions", ["US", "EU"], default=config.REGIONS)
    # date pickers, not free text: scoring compares ISO date strings
    date_from = st.date_input("From", date.fromisoformat(config.DATE_FROM)).isoformat()
    date_to = st.date_input("To", date.fromisoformat(config.DATE_TO)).isoformat()
    st.markdown("---")
    st.markdown("**Legend**")
    for v in PROV_BADGE.values():
        st.markdown(v)
    st.caption("Pipeline and past-event outcomes are **simulated** LabFlow data.")

if not regions:
    st.warning("Select at least one region.")
    st.stop()
if date_from > date_to:
    st.warning("'From' date is after 'To' date.")
    st.stop()
rows = load_scores(tuple(regions), date_from, date_to)
if not rows:
    st.warning("No events in this window/region.")
    st.stop()

tab_list, tab_why, tab_outreach, tab_approve = st.tabs(["Shortlist", "Why", "Outreach", "Approvals"])

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
        "Cost has estimates": "yes" if "estimated" in (r["pass_price_prov"], r["booth_price_prov"], r["travel_est_prov"]) else "no",
    } for i, r in enumerate(rows)])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption("Ranked by ICP target accounts reached per $10k. Density = ICP accounts present / total ICP accounts.")

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
            st.info("No ICP accounts found at this event yet (sponsor/speaker lists may not be published).")
    with right:
        st.subheader("Cost breakdown")
        st.dataframe(pd.DataFrame([
            {"Item": "Passes", "USD": money(r["pass_price"]), "Source": badge(r["pass_price_prov"]), "Note": r["pass_price_note"]},
            {"Item": "Booth / sponsorship", "USD": money(r["booth_price"]), "Source": badge(r["booth_price_prov"]), "Note": r["booth_price_note"]},
            {"Item": "Travel", "USD": money(r["travel_est"]), "Source": badge(r["travel_est_prov"]), "Note": r["travel_est_note"]},
        ]), hide_index=True, use_container_width=True)
        st.markdown(f"**Simulated pipeline on present accounts:** {money(r['simulated_pipeline_usd'])} 🟣")
        st.markdown(f"[Event page]({r['url']}) · scraped {r['fetched_at']}")

# ---------- outreach ----------
with tab_outreach:
    top = rows[0]
    st.subheader(f"Outreach for #1: {top['event']}")
    st.caption("One draft per ICP account present. Each draft cites the graph path that justifies it.")
    batch_id = f"{top['event_id']}-outreach"
    batch = gate.get(batch_id)
    already_sent = bool(batch and batch["status"] == "sent")
    if already_sent:
        st.success(f"This event's batch was sent at {batch['sent_at']}; it can't be redrafted.")
    if st.button("Draft outreach with agent", disabled=not top["accounts"] or already_sent):
        opp_accts = {x["name"] for x in client.query(
            "MATCH (a:Account)-[:IN_PIPELINE]->(:Opportunity) WHERE a.name IN $names RETURN DISTINCT a.name AS name",
            {"names": top["accounts"]})}
        with st.spinner(f"Drafting {len(top['accounts'])} emails…"):
            drafts = draft_batch(top, opp_accts)
        batch = gate.submit(batch_id, top["event_id"], drafts)
        st.success("Drafts submitted for approval (Marketing + BD).")
    if batch:
        edited = []
        for i, d in enumerate(batch["drafts"]):
            with st.expander(f"{d['account']} · owner: {d.get('owner', '?')}"):
                if d.get("error"):
                    st.error(f"Draft failed: {d['error']}")
                st.markdown("**Evidence:** " + "; ".join(f"`{e}`" for e in d.get("evidence", [])))
                # keys include batch + version so text never carries over to another event or a newer draft
                k = f"{batch_id}-{batch['digest']}-{i}"
                subj = st.text_input("Subject", d["subject"], key=f"s-{k}", disabled=batch["status"] == "sent")
                body = st.text_area("Body", d["body"], key=f"b-{k}", height=180, disabled=batch["status"] == "sent")
                st.caption(d.get("rationale", ""))
                edited.append(dict(d, subject=subj, body=body))
        if batch["status"] != "sent" and st.button("Save edits (resets approvals if changed)"):
            gate.update_drafts(batch_id, edited)
            st.rerun()

# ---------- approvals ----------
with tab_approve:
    batch_id = f"{rows[0]['event_id']}-outreach"
    batch = gate.get(batch_id)
    if not batch:
        st.info("No outreach batch yet. Draft one in the Outreach tab.")
    else:
        st.subheader(f"Batch for {rows[0]['event']} · {len(batch['drafts'])} drafts · v{batch['digest']}")
        cols = st.columns(2)
        for col, (role, label) in zip(cols, [("marketing", "Marketing"), ("bd", "BD")]):
            with col:
                a = batch["approvals"].get(role)
                if a and a["digest"] == batch["digest"]:
                    st.success(f"✅ {label} approved by {a['by']} at {a['at']}")
                else:
                    who = st.text_input(f"{label} approver", key=f"who_{role}_{batch_id}")
                    if st.button(f"Approve as {label}", key=f"ap_{role}_{batch_id}",
                                 disabled=not who or batch["status"] == "sent"):
                        try:
                            gate.approve(batch_id, role, who, digest=batch["digest"])
                            st.rerun()
                        except (PermissionError, ValueError) as ex:
                            st.error(str(ex))
        sendable = gate.is_sendable(batch)
        if batch["status"] == "sent":
            st.success(f"Batch marked sent at {batch['sent_at']} (demo: no emails leave the system).")
        else:
            st.markdown("**Status:** " + ("🟢 sendable" if sendable else "🔒 locked: needs Marketing **and** BD"))
            if st.button("Send batch", type="primary", disabled=not sendable):
                gate.mark_sent(batch_id)
                st.rerun()
