# DataSays Evidence Workbench Exploration

Four static interaction concepts explore how an evidence-first analysis workspace should grow across repeated questions. They share the same Executive Business Snapshot and do not connect to the DataSays backend.

## Shared Product Principles

- Dataset, analysis result, and evidence are first-class workspace objects.
- Chat remains available but does not own the primary surface.
- Analysis results persist beyond a message and support follow-up work.
- Evidence, Plan, and Validation remain inspectable; developer traces stay secondary.
- The workspace is designed for extended desktop use, not a one-off report or dashboard builder.

## 01 · Analysis Canvas

1. **Concept:** Questions create linked analysis objects on a persistent spatial canvas.
2. **Why DataSays:** Makes analytical lineage visible while keeping the result central.
3. **First view:** Dataset nodes and a calm empty canvas with suggested starting questions.
4. **Chat:** A compact dock at the bottom; it acts as a canvas command rather than a transcript.
5. **Dataset:** Persistent left rail and visible source nodes before analysis begins.
6. **Result persistence:** Snapshot, chart, findings, and diagnosis remain movable conceptual objects.
7. **KPI / chart / table:** Bundled into a snapshot object; follow-ups add adjacent objects.
8. **Evidence:** Contextual inspector on the right follows the selected object.
9. **History:** Object list and branch hierarchy in the left rail.
10. **After follow-ups:** A diagnosis object is linked to its parent snapshot.
11. **New question:** Creates a new branch or an independent root object.
12. **Clutter control:** Auto-layout, branch collapse, object grouping, and canvas minimap.
13. **Desktop:** Three columns with the central canvas receiving most space.
14. **Narrow screen:** Canvas becomes a vertical object stream; inspector moves below.
15. **Typography:** Pragmatic sans with compact labels and strong numeric hierarchy.
16. **Color:** Neutral canvas, deep green structure, blue references, yellow selected points.
17. **Containers:** Functional 6–7px objects, light borders, minimal shadows.
18. **Charts:** Clean object-level charts with direct annotations.
19. **Difference from original 04:** Results grow spatially rather than staying in one fixed report layout.
20. **Strength:** Best expression of analytical lineage and exploratory branching.
21. **Risk:** Large canvases can become spatially demanding without excellent navigation.

## 02 · Analyst Desktop

1. **Concept:** A stable professional analysis application where each question becomes a document.
2. **Why DataSays:** Supports long work sessions, dense inspection, and predictable navigation.
3. **First view:** Project tree, document tabs, property inspector, and command bar.
4. **Chat:** A narrow command bar; roughly 5–8% of the interface.
5. **Dataset:** Expandable project tree with fields and saved views.
6. **Result persistence:** Each analysis becomes a named document tab and history item.
7. **KPI / chart / table:** Structured report sections with table-like precision.
8. **Evidence:** Right inspector displays the contract of the current document or selected result.
9. **History:** Ordered document tree plus open tabs.
10. **After follow-ups:** A new diagnosis tab opens without replacing the snapshot.
11. **New question:** User chooses a new tab or continues the current document.
12. **Clutter control:** Tab closing, archived documents, saved views, and project search.
13. **Desktop:** Dense three-pane software layout.
14. **Narrow screen:** Project, document, and inspector become sequential screens.
15. **Typography:** Compact desktop-software sans and tabular figures.
16. **Color:** Cool gray workspace, white documents, restrained blue and green states.
17. **Containers:** Mostly panes and table borders; 4–5px controls.
18. **Charts:** Analytical, axis-forward, and aligned with tables.
19. **Difference from original 04:** Treats analysis as documents and tabs, not a single central answer.
20. **Strength:** Most predictable and scalable for professional daily use.
21. **Risk:** Can feel conventional and less distinctly AI-native.

## 03 · Research Thread

1. **Concept:** Questions, evidence, findings, and limitations accumulate as a continuous analytical thread.
2. **Why DataSays:** Preserves reasoning context without turning the interface into a chat log.
3. **First view:** A research map, readable notebook, and evidence notes.
4. **Chat:** Inline at the end of the thread; about 8–10% of the workspace.
5. **Dataset:** Source cards remain in the outline and evidence margin.
6. **Result persistence:** Each completed analysis becomes a numbered notebook chapter.
7. **KPI / chart / table:** Embedded as figures and registers inside the relevant chapter.
8. **Evidence:** Numbered evidence notes and source references in the right margin.
9. **History:** A semantic chapter outline instead of message chronology.
10. **After follow-ups:** The question becomes a new chapter with its own evidence boundary.
11. **New question:** Appends to the thread or starts a separate research thread.
12. **Clutter control:** Chapter outline, collapsed sections, summaries, and separate threads.
13. **Desktop:** Narrow outline, readable central notebook, source margin.
14. **Narrow screen:** Single chronological document with evidence following each chapter.
15. **Typography:** Editorial serif for analysis voice, neutral sans for UI and data.
16. **Color:** Warm paper, charcoal, reference blue, annotation red, validation green.
17. **Containers:** Mostly unframed chapters with rules and citation blocks.
18. **Charts:** Report-like figures with captions and explicit analytical boundaries.
19. **Difference from original 04:** Organizes repeated analysis as an authored research narrative.
20. **Strength:** Best balance of AI exploration, business readability, and preserved context.
21. **Risk:** Long threads may become slower to scan during operational work.

## 04 · Artifact Studio

1. **Concept:** AI commands produce reusable analytical assets rather than conversational answers.
2. **Why DataSays:** Makes machine-readable Evidence and persistent outputs tangible product objects.
3. **First view:** Dataset shelf, command bar, and an empty artifact board.
4. **Chat:** Reduced to a command input, roughly 5% of the surface.
5. **Dataset:** Left asset shelf alongside saved metrics, charts, and bundles.
6. **Result persistence:** Metrics, charts, findings, and model results are saved independently.
7. **KPI / chart / table:** Separate artifacts arranged into lanes and reusable bundles.
8. **Evidence:** Inspector belongs to the selected artifact, not the whole conversation.
9. **History:** Artifact bundles and lineage view.
10. **After follow-ups:** A linked bundle adds driver metrics and a supported finding.
11. **New question:** Generates new assets, optionally referencing existing ones.
12. **Clutter control:** Bundles, lanes, library, search, lineage, and archival states.
13. **Desktop:** Asset shelf, large board, artifact inspector.
14. **Narrow screen:** Artifact list with filters; inspector opens as a detail view.
15. **Typography:** Neutral product sans with strong labels and tabular data.
16. **Color:** Cool gray, dark ink, evidence green, reference blue, restrained orange.
17. **Containers:** 6px functional artifacts, thin borders, no decorative nesting.
18. **Charts:** Compact, composable, and consistent across artifact types.
19. **Difference from original 04:** Decomposes a result into persistent reusable objects rather than one answer page.
20. **Strength:** Strongest long-term model for reuse, composition, and product extensibility.
21. **Risk:** Users may need to understand the artifact model before it feels natural.

## Suggested Comparison Order

1. Research Thread
2. Analyst Desktop
3. Artifact Studio
4. Analysis Canvas

This is a productization recommendation, not a final visual choice. The best eventual direction may combine the Research Thread's context, the Analyst Desktop's navigation, and the Artifact Studio's reusable outputs.
