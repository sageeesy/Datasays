# DataSays Visual Direction Lab

These static demos compare four possible visual languages for the same evidence-first analysis result. They do not call the DataSays backend and do not modify the product UI.

## Shared Scenario

- Delivered orders: 14,429
- Payment GMV: R$ 2.32M
- AOV: R$ 160.82
- Delivery Rate: 96.19%
- Monthly trend, three findings, and an evidence entry point

## Directions

### A. Audit Working Paper

- **Concept:** audited ledger, working paper, reconciliation marks.
- **Audience:** finance, operations, analytics governance, metric owners.
- **First impression:** rigorous, calm, accountable.
- **Layout:** report index, metric ledger, trend worksheet, evidence docket.
- **Type:** compact sans for navigation, report serif for titles and major figures.
- **Color:** paper white, deep ink, muted green status, restrained rust annotation.
- **Containers:** ruled sections instead of floating cards; 2-4px radii only.
- **Charts:** annotated axes, direct labels, reference lines, no decorative fills.
- **Workspace:** question becomes a report header; analysis replaces chat as the primary surface.
- **KPI / Evidence / Trace:** KPIs are ledger rows; evidence is a persistent right docket; trace is a numbered audit trail.
- **Fit:** makes DataSays's metric semantics and reproducibility legible without technical spectacle.
- **Risk:** can feel formal or slow for exploratory users.

### B. Operating Signal Bench

- **Concept:** instrument panel, oscilloscope, live operating signal.
- **Audience:** operations teams monitoring recurring performance and anomalies.
- **First impression:** focused, immediate, technically confident.
- **Layout:** channel rail, dominant trend field, measurement controls, evidence console.
- **Type:** compact sans plus tabular/monospace figures only where measurement requires it.
- **Color:** near-black instrument surface, phosphor green, cyan second channel, amber warnings.
- **Containers:** hairline pane seams, no floating cards, almost no radius.
- **Charts:** graticule grid, channel colors, cursor annotations, explicit scales.
- **Workspace:** question selects the signal; chat is a compact command line rather than a conversation feed.
- **KPI / Evidence / Trace:** KPIs are channel readouts; Evidence is a lower console; trace is a timed acquisition log.
- **Fit:** turns evidence-first analysis into a visible measurement process.
- **Risk:** dark instrument language may intimidate occasional business users and can overemphasize monitoring.

### C. Editorial Decision Brief

- **Concept:** management brief, analytical editorial, annotated report.
- **Audience:** operators, product managers, and executives who consume analysis more than they configure it.
- **First impression:** clear, composed, decision-oriented.
- **Layout:** narrative lead, horizontal metric register, large trend figure, margin findings, footnoted evidence.
- **Type:** editorial serif for the report voice; neutral sans for data and controls.
- **Color:** white, charcoal, cobalt, coral, and semantic green.
- **Containers:** mostly unframed sections; borders only for registers and evidence notes.
- **Charts:** publication-style figure with direct annotations and a restrained multi-hue palette.
- **Workspace:** analysis is a readable document; the original question appears as the brief's mandate.
- **KPI / Evidence / Trace:** KPIs form a register; evidence uses numbered citations; trace stays behind a secondary appendix.
- **Fit:** communicates business value quickly while preserving a path to verification.
- **Risk:** less efficient for repeated operational querying and dense multi-table inspection.

### D. Evidence Workbench

- **Concept:** analyst desk, split workspace, evidence pins.
- **Audience:** analysts, product operators, and technical business users who iterate through follow-up questions.
- **First impression:** capable, collaborative, inspectable.
- **Layout:** compact query rail, central analysis canvas, persistent evidence rail.
- **Type:** one pragmatic sans family with strong data hierarchy.
- **Color:** cool white, dark green-black, teal, yellow highlight, orange caveat.
- **Containers:** functional panels, 6-8px radii, no nested decorative cards.
- **Charts:** analysis canvas favors linked chart/table states and clear selection.
- **Workspace:** chat remains visible as input history, but the verified result owns the center.
- **KPI / Evidence / Trace:** compact KPI strip, evidence objects on the right, trace as a collapsible execution timeline.
- **Fit:** closest to DataSays's current workflow while making the evidence contract a first-class workspace object.
- **Risk:** highest information density and therefore the greatest need for careful progressive disclosure.

Open [`index.html`](index.html) to compare all four directions together.
