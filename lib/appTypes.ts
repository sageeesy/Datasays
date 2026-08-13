import type { ResponseData, VisualizationDataset, VisualizationSpec } from "./client";

export type AppPage = "analysis" | "comparison" | "dashboard";

export interface ChatMessage {
  id: string;
  type: "user" | "ai";
  content: string;
  code?: string;
  status?: "success" | "error" | "autofix";
  timestamp: string;
  output?: ResponseData["output"];
  filesUsed?: string[];
  llmResponse?: ResponseData;
  sandboxResponse?: ResponseData;
}

export interface DashboardPayload {
  question: string;
  timestamp: string;
  response: ResponseData;
}

export interface DashboardModel {
  datasets: VisualizationDataset[];
  visualizations: VisualizationSpec[];
  insights: string[];
  generatedFromLegacyRows: boolean;
}

export function getDashboardRows(response?: ResponseData): Record<string, unknown>[] {
  if (!response) return [];

  const structuredRows = response.metadata?.analysis_result?.rows;
  if (Array.isArray(structuredRows) && structuredRows.length > 0) {
    return structuredRows.filter(
      (row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row),
    );
  }

  if (response.output?.type === "table") {
    const headers = response.output.data?.headers;
    const rows = response.output.data?.rows;
    if (Array.isArray(headers) && Array.isArray(rows)) {
      return rows.map((row: unknown[]) =>
        Object.fromEntries(headers.map((header: string, index: number) => [header, row[index]])),
      );
    }
  }

  if (response.output?.type === "chart" && Array.isArray(response.output.data?.data)) {
    return response.output.data.data;
  }

  return [];
}

function isNumericValue(value: unknown): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  const normalized = String(value ?? "").replace(/[,%$¥￥,]/g, "").trim();
  return normalized !== "" && Number.isFinite(Number(normalized));
}

export function getDashboardModel(response?: ResponseData): DashboardModel | null {
  if (!response) return null;
  const result = response.metadata?.analysis_result || response.output?.analysis_result;
  const datasets = Array.isArray(result?.datasets)
    ? result.datasets.filter((dataset) => dataset && dataset.id && Array.isArray(dataset.rows) && dataset.rows.length > 0)
    : [];
  const datasetIds = new Set(datasets.map((dataset) => dataset.id));
  const visualizations = Array.isArray(result?.visualizations)
    ? result.visualizations.filter((visualization) => visualization && datasetIds.has(visualization.dataset_id))
    : [];

  if (datasets.length > 0 && visualizations.length > 0) {
    return {
      datasets,
      visualizations,
      insights: Array.isArray(result?.insights) ? result.insights.filter(Boolean).slice(0, 8) : [],
      generatedFromLegacyRows: false,
    };
  }

  const rows = getDashboardRows(response);
  if (rows.length === 0) return null;
  const keys = Object.keys(rows[0]);
  if (keys.length < 2) return null;
  const numericKeys = keys.filter((key) => rows.some((row) => isNumericValue(row[key])));
  const dimensionKey = keys.find((key) => !numericKeys.includes(key)) || keys[0];
  const measureKey = numericKeys.find((key) => key !== dimensionKey);
  if (!measureKey) return null;

  const fallbackDataset: VisualizationDataset = { id: "result", name: "Result data", rows };
  const fallbackVisualization: VisualizationSpec = {
    type: response.metadata?.plan?.intent === "trend" ? "line" : "bar",
    title: result?.summary || "Analysis result",
    dataset_id: fallbackDataset.id,
    x: dimensionKey,
    y: measureKey,
  };
  return {
    datasets: [fallbackDataset],
    visualizations: [fallbackVisualization],
    insights: Array.isArray(result?.insights) ? result.insights.filter(Boolean).slice(0, 8) : [],
    generatedFromLegacyRows: true,
  };
}

export function isDashboardReady(response?: ResponseData): boolean {
  return getDashboardModel(response) !== null;
}
