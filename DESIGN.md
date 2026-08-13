# DataSays Interface System

DataSays is an Operate-mode product UI. It should feel precise, restrained, and work-focused. Scanability, evidence, and clear state are more important than decorative expression.

## Structure

- Persistent top navigation switches between Verified Analysis, Comparison Lab, and Data Dashboard.
- Analysis keeps the existing conversation sidebar and data context panel.
- Comparison and Dashboard use the full workspace width and retain the same top navigation.
- Verified answers use one primary result surface; technical evidence remains progressively disclosed.

## Visual Language

- Cool neutral surfaces with blue for primary actions and selection.
- Emerald communicates verified success; amber communicates warnings; red communicates failure.
- One compact sans-serif UI family, fixed type scale, dense spacing, and 8px-or-less card radii.
- Motion is limited to state feedback and 150-250ms transitions.
- Charts use an accessible multi-hue palette and never rely on color alone.

## Responsive Behavior

- Side panels become overlays below desktop width.
- Top navigation remains horizontally scrollable rather than truncating labels.
- Dashboard controls stack on mobile; charts retain stable height and tables scroll horizontally.
- Long labels, filenames, code, and evidence must wrap or truncate without changing control dimensions.
