# Hyderabad post — progress log

Brief: *ParamaSrota: Hyderabad Post Agent Brief (2026-09-29)* (founder's Drive), plus
`docs/STORY_ENGINE.md` and `docs/HYDERABAD_WEDGE.md`. Run in compressed "tonight mode".

## 2026-09-29 — tonight mode, steps a–f

| Step | Status | Where |
|---|---|---|
| a) Schema + source register | done | `core/record_schema.py` (via `core/db.py` migration), `record/load.py` |
| b) Sources: boomed → risks → next | done (search-level only) | `data/hyderabad/sources.json` — 76 story sources + 23 portals |
| c) Nodes, dated attributes, verifier | done; **0 of 37 nodes graded** | `record/verify.py`; `data/hyderabad/{nodes,entities,edges}.json` |
| d) DRAFT v0 | done (~2,700 words incl. tables and tags) | `data/hyderabad/post/DRAFT-v0.md` (private) |
| e) Wiki stubs | done — 65 pages | `record/wiki.py` → `data/hyderabad/wiki/` (private) |
| f) This log | done | here |

Not done (the brief's day 3–7 items): the timeline graphic, area map and quote-card images;
a corrections page; founder checkpoint on roles and weights.

### The one thing to know

**This session's container could not fetch any source except microsoft.com.** Direct HTTP gets a
403 from the environment's egress policy for every other host, including all Telangana
government sites, all news sites and Wikipedia. WebFetch is blocked the same way. Collection
therefore used **web search**, which returns URLs plus a model-written summary, *not* source text.

Consequences, following the brief's rule that there's no node without a located source span:

- Every node span is a **paraphrase** (`span_is_verbatim=0`) taken from a search summary. The
  verifier never counts a paraphrase as "located", so **all 37 nodes are unverified**, and
  every claim in the draft is tagged `[UNVERIFIED]`.
- **The one located span:** Microsoft's campus page supports "54 acres, three buildings", graded
  *reported*. The same page does **not** support "set up in 1998 / first outside the US". The
  verifier caught this, and the page was removed as a source for that node.
- Nothing was bypassed. No mirrors, archives or caches were used to get around the policy.

**To grade the nodes:** run the verifier from a machine with normal internet access
(the founder's Windows box):

```bash
python record/load.py data/hyderabad        # into sansad.db
python record/verify.py data/hyderabad      # fetch, cache, locate, grade
python record/wiki.py data/hyderabad/wiki --story hyd-post-1
```

For each span reported "paraphrase only; closest sentence …", paste the real passage into the
bundle with `verbatim: true` and rerun. That is the verifier-in-the-loop step. Alternatively,
widen this cloud environment's network access (environment settings → Network access) and
rerun here.

### Private data lives in the private repo

The repo is public and the brief says don't publish, so the research bundle, DRAFT v0 and wiki
stubs are in the **private** repo `bparlapalli/Sansad_research` (`hyderabad/`, pushed
2026-09-29). Put it at `sansad/data/hyderabad/` (gitignored here) to use it with the code in
this repo. `record.db` is never committed; `record/load.py` rebuilds it.

### What was collected

**Why areas boomed (13 nodes):** HITEC City (22 Nov 1998); Microsoft IDC (1998); Financial
District foundation (2001); RGIA opens (23 Mar 2008); first ORR stretch, Gachibowli–Shamshabad
(14 Nov 2008); ORR complete (Jul 2016); ICT Policy (Apr 2016); Metro Phase 1, Miyapur–Nagole
(28 Nov 2017); Amazon campus (21 Aug 2019); GRID policy (2020); Kokapet auctions (Jul 2021,
3 Aug 2023); Old City metro delay. Zone launch shares (ANAROCK Q1–Q3 2024) are stored as dated
attributes on `west-hyderabad` / `east-hyderabad`.

**Risks (11):** HYDRAA (GO 99, 19 Jul 2024), statutory ordinance (Sep 2024), N-Convention
demolition (24 Aug 2024), High Court restraint (**date unknown**), FTL portal (**date unknown**);
unsold stock of 1,42,722 units in H1 2026 (CRE Matrix via press); H-1B Proclamation 10973
(19 Sep 2025) → vacated (8 Jun 2026) → stay denied (24 Jul 2026); Kancha Gachibowli GO 54
(26 Jun 2024) → Supreme Court halt (Apr 2025).

**Next areas (10):** GO 111 (1996) → GO 69 (12 Apr 2022); Metro Phase 2 (central sanction
pending, "no fixed timeline"; ₹2,787 cr land acquisition approved Jan 2026); RRR North bids
(11 Nov 2025), RRR South pending; FCDA (Mar 2025); Musi ADB loan, a **disputed claim**
(state, 2 Jan 2026, vs Musi Jan Andolan, Mar 2026); HMDA expansion / Master Plan 2050.

**Quotes (3, all claims, none verbatim-checked):** Revanth Reddy on encroachers (Aug 2024);
Ranganath on buyers asking about FTL (12 Mar 2025); "Bye Bye Bangalore, Hello Hyderabad"
(attributed to Naidu; party website + Wikipedia only).

**Local data checked:** `sansad.db.bak` (Parliament statements, Dec 2025) has no usable
Hyderabad real-estate material, only statistical tables that mention Telangana. The MoHUA
"no fixed timeline" Metro Phase 2 answer in Parliament is a good candidate for a primary source
once that session is scraped.

### Blocked sources

All portals named in the brief returned an egress 403 from this container on 2026-09-29.
**Access and terms of use for each are still unchecked**, and must be checked before collecting.

| Portal | What we need from it | Status |
|---|---|---|
| rera.telangana.gov.in | Projects by area (Kollur/Tellapur counts especially) | blocked_env |
| goir.telangana.gov.in | GO 99/2024, GO 54/2024, GO 69/2022, GO 111/1996 texts | blocked_env |
| dsa.telangana.gov.in (GO bank) | GO 69 PDF (found via search) | blocked_env |
| hmda.gov.in | Master Plan 2050 status, Kokapet auction notices | blocked_env |
| registration.telangana.gov.in (IGRS) | Registration volumes — better lagging-area test than launch share | blocked_env |
| hydraa.telangana.gov.in | Notices, FTL portal, launch date | blocked_env |
| hmrl.co.in, ltmetro.com | Phase 1 dates, Old City stretch, Phase 2 DPR | blocked_env |
| it.telangana.gov.in | ICT Policy 2016 original, GRID GO, annual reports | blocked_env |
| tshc.gov.in, greentribunal.gov.in, indiankanoon.org | HYDRAA SOP order (date!), N-Convention stay, Kancha orders | blocked_env |
| anarock.com, knightfrank.co.in | Zone launch shares (PDF links found), H2 2025 report | blocked_env |
| uscis.gov, bls.gov | H-1B status on publish date | blocked_env |
| pib.gov.in | Union statements on Metro Phase 2 / RRR | blocked_env |
| All news sites + Wikipedia | Spans for every node | blocked_env |
| microsoft.com | IDC campus | **open**: 1 span located |

### Source register (story sources)

Generated from `rec_sources`. "used by" counts node and attribute links. Kinds: *reference*,
*listing* and *blog* are leads only and never count toward a grade.

| id | kind | publisher | published | access | used by |
|---|---|---|---|---|---|
| [bnp-kollur](https://booknewproperty.com/kollur-orr-exit-2-the-next-big-residential-growth-pocket-in-hyderabad/) | blog | BookNewProperty | 2026 | blocked_env | 0 nodes, 0 attrs |
| [hoinvestors-unsold](https://hoinvestors.com/intelligence/hyderabad-unsold-inventory-paradox/) | blog | House of Investors | 2026 | blocked_env | 1 nodes, 0 attrs |
| [metrorailguy-rrr](https://themetrorailguy.com/nhai-hyderabad-regional-ring-road-information-route-map-status/) | blog | The Metro Rail Guy | 2026 | blocked_env | 1 nodes, 0 attrs |
| [propnewz-metro2](https://www.propnewz.com/blog/hyderabad-metro-phase-2-airport-corridor-old-city-2026) | blog | PropNewz | 2026-04 | blocked_env | 1 nodes, 0 attrs |
| [1acre-fcda](https://1acre.in/map-layers/telangana/future_city) | listing | 1acre.in | ? | blocked_env | 1 nodes, 2 attrs |
| [99acres-grid](https://www.99acres.com/articles/all-about-the-grid-policy-in-hyderabad.html) | listing | 99acres | ? | blocked_env | 1 nodes, 0 attrs |
| [air-hydraa-cabinet](https://www.newsonair.gov.in/telangana-cabinet-grants-legal-sanctity-to-hydraa) | news | All India Radio News | 2024-09-21 | blocked_env | 1 nodes, 0 attrs |
| [air-kancha-sc](https://www.newsonair.gov.in/telangana-sc-halts-all-activities-on-controversial-400-acre-kancha-gachibowli-land) | news | All India Radio News | 2025-04-04 | blocked_env | 1 nodes, 0 attrs |
| [airporttech-rgia](https://www.airport-technology.com/projects/hypderbadindia/) | news | Airport Technology | ? | blocked_env | 1 nodes, 0 attrs |
| [bs-metro-2017](https://www.business-standard.com/article/economy-policy/pm-modi-flags-off-first-hyderabad-metro-train-from-miyapur-takes-a-ride-117112800541_1.html) | news | Business Standard | 2017-11-28 | blocked_env | 1 nodes, 4 attrs |
| [bs-musi-adb](https://www.business-standard.com/india-news/adb-gives-nod-to-extend-4-100-cr-loan-to-musi-river-development-minister-126010200276_1.html) | news | Business Standard | 2026-01-02 | blocked_env | 1 nodes, 2 attrs |
| [bs-ts-it-fy24](https://www.business-standard.com/industry/news/telangana-it-exports-clock-11-growth-rate-to-rs-2-68-trn-in-fy24-124080400504_1.html) | news | Business Standard | 2024-08-04 | blocked_env | 0 nodes, 0 attrs |
| [cc-musi-andolan](https://countercurrents.org/2026/03/musi-jan-andolan-seeks-halt-to-musi-riverfront-plan-calls-for-ecological-rejuvenation-without-evictions/) | news | Countercurrents | 2026-03 | blocked_env | 1 nodes, 0 attrs |
| [dc-go111-2022](https://www.deccanchronicle.com/nation/current-affairs/200422/restrictions-on-go-111-removed.html) | news | Deccan Chronicle | 2022-04-20 | blocked_env | 2 nodes, 3 attrs |
| [dc-hc-hydraa](https://www.deccanchronicle.com/southern-states/telangana/telangana-hc-slams-hydraas-unilateral-demolitions-1862411) | news | Deccan Chronicle | ? | blocked_env | 1 nodes, 0 attrs |
| [dc-hmda-10472](https://www.deccanchronicle.com/southern-states/telangana/hmda-grows-to-10472-sq-km-plans-new-master-plan-2050-1865943) | news | Deccan Chronicle | 2024 | blocked_env | 1 nodes, 0 attrs |
| [dc-musi-375](https://www.deccanchronicle.com/southern-states/telangana/telangana-govt-releases-rs-375-crore-for-musi-development-project-1955288) | news | Deccan Chronicle | 2026 | blocked_env | 0 nodes, 0 attrs |
| [dh-ts-it-313](https://www.deccanherald.com/business/telangana-it-exports-hit-rs-313-lakh-crore-amid-services-sector-surge-3939905) | news | Deccan Herald | 2025 | blocked_env | 0 nodes, 0 attrs |
| [domainb-rgia](https://www.domain-b.com/aviation-aerospace/airports/new-rajiv-gandhi-international-airport-at-shamshabad-commences-operations) | news | Domain-b | 2008-03-23 | blocked_env | 1 nodes, 0 attrs |
| [entrepreneur-ktr-2016](https://www.entrepreneur.com/en-in/news-and-trends/what-are-telanganas-it-minister-kt-raos-plans-for-silicon/276828) | news | Entrepreneur India | 2016 | blocked_env | 1 nodes, 1 attrs |
| [etv-kokapet-2023](https://www.etvbharat.com/english/state/telangana/at-rs-100-crore-per-acre-hmda-plot-at-neopolis-layout-kokapet-sells-for-record-price-in-hyderabad-real-estate-history/na20230804122043672672224) | news | ETV Bharat | 2023-08-04 | blocked_env | 1 nodes, 0 attrs |
| [forbes-h1b](https://www.forbes.com/sites/stuartanderson/2026/06/08/immigration-ruling-strikes-down-100000-h-1b-fee-whats-next/) | news | Forbes | 2026-06-08 | blocked_env | 2 nodes, 0 attrs |
| [greatandhra-unsold](https://www.greatandhra.com/politics/telangana-news/hyderabad-realty-warning-unsold-homes-jump-21/) | news | Great Andhra | 2026-07 | blocked_env | 1 nodes, 0 attrs |
| [gulf-kancha](https://gulfnews.com/world/asia/india/supreme-court-stays-tree-felling-on-land-near-hyderabad-university-2-1.500081561) | news | Gulf News | 2025-04 | blocked_env | 1 nodes, 0 attrs |
| [hansindia-metro2](https://www.thehansindia.com/amp/news/cities/hyderabad/hyderabad-metro-phase-2-gets-centre-support-1077549) | news | The Hans India | 2026 | blocked_env | 2 nodes, 2 attrs |
| [indiatv-nconv](https://www.indiatvnews.com/telangana/hyderabad-nagarjuna-controversial-n-convention-centre-demolished-hyderabad-authorities-hydra-ftl-thammidi-kunta-lake-madhapur-gandipet-lake-actor-2024-08-24-948481) | news | India TV | 2024-08-24 | blocked_env | 1 nodes, 0 attrs |
| [mrt-oldcity-polls](https://metrorailtoday.com/news/hyderabad-old-city-metro-project-progress-delayed-until-conclusion-of-lok-sabha-polls) | news | Metro Rail Today | 2024-03 | blocked_env | 1 nodes, 0 attrs |
| [munsif-mp2050](https://munsifdaily.com/telangana-govt-to-launch-hmda-master-plan-2050/) | news | Munsif Daily | 2026 | blocked_env | 1 nodes, 1 attrs |
| [munsif-oldcity-metro](https://munsifdaily.com/hyderabad-old-city-metro-finally-moving/) | news | Munsif Daily | ? | blocked_env | 1 nodes, 2 attrs |
| [newsmeter-kokapet-2021](https://newsmeter.in/hyderabad/kokapet-land-auction-gets-hmda-rs-2000-cr-680751) | news | NewsMeter | 2021-07 | blocked_env | 1 nodes, 0 attrs |
| [newsmeter-ranganath-ftl](https://newsmeter.in/hyderabad/people-now-verify-fti-buffer-zone-before-buying-land-thanks-to-hydraa-ranganath-745137) | news | NewsMeter | 2025-03 | blocked_env | 1 nodes, 0 attrs |
| [sakshi-go111](https://www.sakshipost.com/news/go-111-repeal-spells-death-hyderabads-twin-reservoirs-warn-experts-191505) | news | Sakshi Post | 2022 | blocked_env | 1 nodes, 0 attrs |
| [sakshi-ict-2021](https://www.sakshipost.com/news/telangana/ktr-launches-telanganas-2nd-ict-policy-check-speech-highlights-and-key-initiatives) | news | Sakshi Post | 2021 | blocked_env | 0 nodes, 0 attrs |
| [sakshi-revanth-lakes](https://www.sakshipost.com/news/telangana/revanth-reddys-ambitious-plan-reclaim-city-lakes-hyderabad-328418) | news | Sakshi Post | 2024 | blocked_env | 1 nodes, 0 attrs |
| [siasat-hydraa-portal](https://www.siasat.com/hydraa-launches-portal-to-check-ftl-before-buying-homes-3540671/) | news | Siasat | ? | blocked_env | 1 nodes, 0 attrs |
| [siasat-kokapet-2023](https://www.siasat.com/hyderabad-hmdas-kokapet-e-auction-sees-record-bidding-2658821/) | news | Siasat | 2023-08 | blocked_env | 1 nodes, 0 attrs |
| [siasat-ranganath-ftl](https://www.siasat.com/property-buyers-now-check-ftl-buffer-zones-first-hydraa-chief-3193721/) | news | Siasat | 2025-03-12 | blocked_env | 1 nodes, 0 attrs |
| [southfirst-nconv](https://thesouthfirst.com/telangana/hydra-pulls-down-actor-nagarjunas-property-for-encroaching-lake-area-in-hyderabad/) | news | The South First | 2024-08-24 | blocked_env | 1 nodes, 0 attrs |
| [statesman-revanth-hydraa](https://www.thestatesman.com/india/crackdown-on-encroachment-on-lakes-will-continue-telangana-cm-revanth-1503335719.html) | news | The Statesman | 2024-08 | blocked_env | 1 nodes, 1 attrs |
| [tnm-hydraa-powers](https://www.thenewsminute.com/telangana/telangana-govt-gives-hydraa-additional-powers-to-protect-public-assets-in-hyderabad) | news | The News Minute | 2024 | blocked_env | 1 nodes, 0 attrs |
| [tnm-kokapet-2023](https://www.thenewsminute.com/telangana/hyderabad-neopolis-land-sells-rs-100-cr-acre-record-auction-180623) | news | The News Minute | 2023-08 | blocked_env | 1 nodes, 0 attrs |
| [tribune-nconv](https://www.tribuneindia.com/news/top-headlines/hydra-starts-demolishing-convention-centre-owned-by-actor-nagarjuna/) | news | The Tribune | 2024-08-24 | blocked_env | 1 nodes, 0 attrs |
| [tt-grid](https://telanganatoday.com/telanganas-grid-policy-to-drive-growth-for-office-markets) | news | Telangana Today | ? | blocked_env | 1 nodes, 1 attrs |
| [tt-hc-hydraa](https://telanganatoday.com/telangana-hc-pulls-up-hydraa-halts-demolitions-except-for-encroachments-on-public-land) | news | Telangana Today | ? | blocked_env | 1 nodes, 0 attrs |
| [tt-kokapet-2021](https://telanganatoday.com/hyderabad-kokapet-land-attracts-record-bid-of-rs-60-crore-per-acre) | news | Telangana Today | 2021-07 | blocked_env | 1 nodes, 0 attrs |
| [tt-rrr-bids](https://telanganatoday.com/telanganas-rrr-progress-hinges-on-bids-pending-southern-part-clearance) | news | Telangana Today | 2026 | blocked_env | 2 nodes, 2 attrs |
| [ttnews-amazon](https://www.ttnews.com/articles/amazons-new-india-campus-its-largest) | news | Transport Topics (Bloomberg) | 2019-08-21 | blocked_env | 1 nodes, 0 attrs |
| [yourstory-amazon](https://yourstory.com/2019/08/amazon-largest-campus-hyderabad-india) | news | YourStory | 2019-08-21 | blocked_env | 1 nodes, 0 attrs |
| [hmrl-oldcity](https://hmrl.co.in/hyderabad-metro-expansion-brings-long-awaited-connectivity-to-the-old-city/) | official_statement | Hyderabad Metro Rail Ltd | ? | blocked_env | 1 nodes, 0 attrs |
| [ms-idc-hyd](https://www.microsoft.com/en-in/msidc/hyderabad-campus) | official_statement | Microsoft | ? | open | 0 nodes, 1 attrs |
| [tdp-hitec](https://gunturtdp.com/how-chandrababu-built-hitec-city/) | party_statement | Telugu Desam Party (district site) | ? | blocked_env | 2 nodes, 0 attrs |
| [go-69-2022-pdf](https://www.dsa.telangana.gov.in/GOs-Bank/go69%20MAUD%20go111.pdf) | primary | Govt of Telangana, MA&UD | 2022-04-12 | blocked_env | 1 nodes, 3 attrs |
| [hmrl-about](https://hmrl.co.in/about-hmrl/) | primary | Hyderabad Metro Rail Ltd | ? | blocked_env | 0 nodes, 0 attrs |
| [hydraa-about](https://hydraa.telangana.gov.in/about) | primary | HYDRAA | ? | blocked_env | 1 nodes, 0 attrs |
| [ict-policy-2016-pdf](https://www.cmai.asia/digitalindia/pdf/Telangana-ICT-Policy-Framework-2016.pdf) | primary | Govt of Telangana (via CMAI mirror) | 2016-04 | blocked_env | 1 nodes, 0 attrs |
| [uscis-h1b-faq](https://www.uscis.gov/newsroom/alerts/h-1b-faq) | primary | USCIS | ? | blocked_env | 0 nodes, 0 attrs |
| [aaroads-orr](https://wiki.aaroads.com/wiki/Outer_Ring_Road_%28Hyderabad,_India%29) | reference | AARoads Wiki | ? | blocked_env | 1 nodes, 0 attrs |
| [wp-financial-district](https://en.wikipedia.org/wiki/Financial_District,_Hyderabad) | reference | Wikipedia | ? | blocked_env | 1 nodes, 0 attrs |
| [wp-hitec-city](https://en.wikipedia.org/wiki/HITEC_City) | reference | Wikipedia | ? | blocked_env | 2 nodes, 4 attrs |
| [wp-hydraa](https://en.wikipedia.org/wiki/HYDRAA) | reference | Wikipedia | ? | blocked_env | 1 nodes, 4 attrs |
| [wp-ktr](https://en.wikipedia.org/wiki/K._T._Rama_Rao) | reference | Wikipedia | ? | blocked_env | 0 nodes, 2 attrs |
| [wp-orr](https://en.wikipedia.org/wiki/Outer_Ring_Road,_Hyderabad) | reference | Wikipedia | ? | blocked_env | 2 nodes, 3 attrs |
| [wp-pharmacity](https://en.wikipedia.org/wiki/Hyderabad_Pharma_City) | reference | Wikipedia | ? | blocked_env | 1 nodes, 0 attrs |
| [wp-rgia](https://en.wikipedia.org/wiki/Rajiv_Gandhi_International_Airport) | reference | Wikipedia | ? | blocked_env | 1 nodes, 2 attrs |
| [wp-software-telangana](https://en.wikipedia.org/wiki/Software_industry_in_Telangana) | reference | Wikipedia | ? | blocked_env | 1 nodes, 0 attrs |
| [anarock-hyd-q1-2024](https://websitemedia.anarock.com/media/Hyderabad_Q1_2024_Residential_Market_Viewpoints_e7b152c0ec.pdf) | research | ANAROCK | 2024-04 | blocked_env | 0 nodes, 2 attrs |
| [anarock-hyd-q1-2026](https://websitemedia.anarock.com/media/Hyderabad_Q1_2026_Residential_Market_Viewpoints_5fe7a00839.pdf) | research | ANAROCK | 2026-04 | blocked_env | 0 nodes, 0 attrs |
| [anarock-hyd-q2-2024](https://websitemedia.anarock.com/media/Hyderabad_Q2_2024_142b71eeaf.pdf) | research | ANAROCK | 2024-07 | blocked_env | 0 nodes, 2 attrs |
| [anarock-hyd-q3-2024](https://websitemedia.anarock.com/media/Hyderabad_Q3_2024_e02013b402.pdf) | research | ANAROCK | 2024-10 | blocked_env | 0 nodes, 1 attrs |
| [clarkhill-h1b-1cir](https://www.clarkhill.com/news-events/news/first-circuit-blocks-reinstatement-of-100k-h-1b-fee/) | research | Clark Hill | 2026-07 | blocked_env | 1 nodes, 1 attrs |
| [impri-hydraa](https://www.impriindia.com/insights/policy-update/hyderabad-disaster-response-and-asset-protection-agency-hydraa-2024-a-sustainable-urban-governance-model/) | research | IMPRI | ? | blocked_env | 0 nodes, 0 attrs |
| [kf-india-h2-2025](https://content.knightfrank.com/research/3070/documents/en/india-real-estate-office-and-residential-market-h2-2025-12597.pdf) | research | Knight Frank | 2026-01 | blocked_env | 0 nodes, 0 attrs |
| [klasko-h1b-aug](https://www.klaskolaw.com/august-2026-100000-h-1b-fee-blocked-again/) | research | Klasko Immigration Law | 2026-08 | blocked_env | 1 nodes, 0 attrs |
| [lcw-kancha](https://www.landconflictwatch.org/conflicts/students-residents-rally-to-save-400-acre-kancha-gachibowli-land-supreme-court-steps-in) | research | Land Conflict Watch | 2025 | blocked_env | 2 nodes, 1 attrs |
| [ogletree-h1b](https://ogletree.com/insights-resources/blog-posts/trump-administration-appeals-ruling-striking-down-100000-h-1b-fee-requirement/) | research | Ogletree Deakins | 2026-06 | blocked_env | 2 nodes, 2 attrs |
| [yale-h1b-extend](https://oiss.yale.edu/news/presidential-proclamation-extends-h-1b-100000-fee-policy-fee-remains-blocked-by-court-order) | research | Yale OISS | 2026 | blocked_env | 0 nodes, 0 attrs |

### Open questions / gaps (for the next session)

- Dates missing: High Court order restraining HYDRAA; HYDRAA FTL portal launch; HMDA area
  expansion (year only); Old City metro deferral (only month of one report).
- Primary documents to locate: GO 99/2024, GO 54/2024, GO 69/2022 text, ICT Policy 2016 original,
  GRID GO, the CRE Matrix H1-CY26 report, the MoHUA Parliament answer, the FCDA GO/Act.
- Kollur/Tellapur "growth" currently rests on developer marketing pages only; need RERA counts.
- H-1B: a Yale notice reports a *new proclamation extending* the policy, and one summary mentions
  a DHS proposed rule (25 Aug 2026). Both unconfirmed; recheck on the publish date.
- Graphics (timeline, area map, 3 quote cards) not started; they should render from `rec_nodes`.

### Founder decision list (all open)

1. **Lagging areas.** Proposed: **East Hyderabad (Uppal / LB Nagar)**, on ANAROCK 2024 launch
   share (east 5–8% vs west 51–79%), and the **Old City**, on the unbuilt Phase 1 metro stretch.
   Weakness: launch share measures developer activity, not prices; IGRS data would be better.
   Confirm, or pick others.
2. **Third next-growth candidate.** Proposed: the **former GO 111 villages** (next to Kokapet;
   trigger: GO 69 plus the pending Master Plan 2050 zoning). Alternative: **Bharat Future City**
   (weaker sources).
3. **Risk 3.** US visa/IT exposure (as drafted) or **Kancha Gachibowli litigation**. Or run four risks?
4. **Roles and weights.** All 37 are proposals. Contested ones to look at first:
   - Metro Phase 1 = spillover / *minor* (argued: present in both east and west)
   - HYDRAA = *roadblock* (a protective decision with side effects on buyers), not unblocker
   - ORR first stretch = *essential*, ORR completion = *minor* (the order-of-opening argument)
   - Unsold inventory = *roadblock* (it's a market condition, not a decision; *wildcard*?)
   - GRID policy = deliberate bet / *minor* (a deliberate bet that hasn't paid off so far)
5. **`[ANALYSIS]` sentences** in the draft (4) are inferences from comparisons. Keep them as
   editorial analysis, or cut them? (STORY_ENGINE §3.5: hypotheses stay internal; the visa →
   GCC → housing chain is already marked internal-only.)
6. **Claims the post relies on:** the Musi ADB loan (state claim vs Musi Jan Andolan; drafted as
   disputed); the "Bye Bye Bangalore" slogan (party website only). Use, or drop?
7. **Named people and developers:**
   - The N-Convention demolition names a private owner (a film actor), in reporting only.
     Draft describes it as "a convention centre" and leaves the name for you.
   - The Kokapet auctions' winning bidders (a developer) are in the sources but left out of the draft.
   - Officials named: Naidu, Vajpayee, KTR, Revanth Reddy, Ranganath, Modi, Trump, with role on
     date only and no characterisation.
8. ~~Preserving the private bundle~~ → done: private repo `Sansad_research`.
9. **Network**: widen this environment's egress, or run the verifier locally?
