// Rank events by ICP target accounts reached per $10k. Every hit carries its explaining path.
// Params: $regions, $from, $to (ISO date strings)
MATCH (icp:Account) WITH count(icp) AS total_icp
MATCH (e:Event)-[:IN_REGION]->(r:Region)
WHERE r.code IN $regions AND e.start_date >= $from AND e.start_date <= $to

// hop 1: account sponsors/exhibits (scraped) or attended last year (estimated)
OPTIONAL MATCH (a1:Account)-[d:SPONSORS|ATTENDS]->(e)
WITH e, r, total_icp,
     collect({acct: a1.name, prov: d.prov,
              path: a1.name + CASE WHEN d.as_name IS NULL OR toLower(d.as_name) STARTS WITH toLower(a1.name)
                                   THEN '' ELSE ' (as ' + d.as_name + ')' END
                    + ' -[' + type(d) + ']-> ' + e.name}) AS direct

// hop 2: someone from the account speaks
OPTIONAL MATCH (a2:Account)<-[:WORKS_AT]-(p:Person)-[s:SPEAKS_AT]->(e)
WITH e, r, total_icp, direct,
     collect({acct: a2.name, prov: s.prov,
              path: a2.name + ' <-[WORKS_AT]- ' + p.name + ' -[SPEAKS_AT]-> ' + e.name}) AS spk

WITH e, r, total_icp, [h IN direct + spk WHERE h.acct IS NOT NULL] AS hits
UNWIND (CASE WHEN size(hits) = 0 THEN [null] ELSE hits END) AS h
WITH e, r, total_icp, hits, collect(DISTINCT h.acct) AS accts

// simulated pipeline on the accounts present (secondary column, not the rank key)
OPTIONAL MATCH (a:Account)-[:IN_PIPELINE]->(o:Opportunity) WHERE a.name IN accts
WITH e, r, total_icp, hits, accts, sum(coalesce(o.amount_usd, 0)) AS sim_pipeline,
     coalesce(e.pass_price, 0) + coalesce(e.booth_price, 0) + coalesce(e.travel_est, 0) AS cost

RETURN e.event_id AS event_id, e.name AS event, e.series AS series, r.code AS region,
       e.start_date AS start_date, e.city AS city, e.url AS url, e.fetched_at AS fetched_at,
       size(accts) AS accounts_present, accts AS accounts,
       toFloat(size(accts)) / total_icp AS density,
       cost,
       e.pass_price AS pass_price, e.pass_price_prov AS pass_price_prov, e.pass_price_note AS pass_price_note,
       e.booth_price AS booth_price, e.booth_price_prov AS booth_price_prov, e.booth_price_note AS booth_price_note,
       e.travel_est AS travel_est, e.travel_est_prov AS travel_est_prov, e.travel_est_note AS travel_est_note,
       CASE WHEN cost > 0 THEN size(accts) * 10000.0 / cost ELSE null END AS reached_per_10k,
       sim_pipeline AS simulated_pipeline_usd,
       [h IN hits | h.path + ' (' + h.prov + ')'] AS why
ORDER BY reached_per_10k DESC
