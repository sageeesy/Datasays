# DataSays Visualization Contract

DataSays separates calculation from rendering:

- The Python sandbox calculates chart-ready values only.
- The frontend renders interactive charts from validated JSON.
- Sandbox code must not import plotting or image libraries or create image files.

## Supported charts

| Type | Required fields | Typical use |
|---|---|---|
| `bar` | `x`, `y`; optional `series` | Group comparisons, feature importance |
| `line` | `x`, `y`; optional `series` | Time trends, model curves |
| `pie` | `x`, `y` | Small-part composition |
| `scatter` | `x`, `y`; optional `series` | Relationships and regression diagnostics |
| `histogram` | `x`, `y` | Precomputed bins and counts |
| `box` | `x`, `lower`, `q1`, `median`, `q3`, `upper` | Precomputed five-number summaries |
| `heatmap` | `x`, `y`, `value` | Correlation and matrix results |
| `table` | None | Detailed records |

## Result example

```json
{
  "answer_type": "table",
  "summary": "Outcome 1 has a higher mean glucose value.",
  "rows": [{"Outcome": 0, "Glucose": 109.92}],
  "columns_used": ["Outcome", "Glucose"],
  "insights": ["Glucose has the strongest relationship with Outcome."],
  "datasets": [
    {
      "id": "outcome_means",
      "name": "Mean glucose by outcome",
      "rows": [
        {"Outcome": 0, "mean": 109.92},
        {"Outcome": 1, "mean": 140.18}
      ]
    }
  ],
  "visualizations": [
    {
      "type": "bar",
      "title": "Mean glucose by outcome",
      "dataset_id": "outcome_means",
      "x": "Outcome",
      "y": "mean"
    }
  ]
}
```

The schema accepts at most 12 visualizations, 12 referenced datasets, 500 rows per dataset, and 2,000 visualization rows in total. Common omitted mappings for histogram, box plot, and heatmap results are normalized when the dataset fields make the mapping unambiguous. Unknown chart types, missing datasets, and invalid field references fail validation and enter the code repair loop.
