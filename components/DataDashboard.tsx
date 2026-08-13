import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BarChart3,
  Box,
  Database,
  Grid3X3,
  Lightbulb,
  LineChart as LineChartIcon,
  PieChart as PieChartIcon,
  ScatterChart as ScatterChartIcon,
  Table2,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart as RechartsScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { useI18n } from "../lib/i18n";
import { getDashboardModel, type DashboardPayload } from "../lib/appTypes";
import type { VisualizationDataset, VisualizationSpec, VisualizationType } from "../lib/client";
import { formatDisplayValue, formatFixedNumber } from "../lib/numberFormat";

interface DataDashboardProps {
  payload: DashboardPayload | null;
  onOpenAnalysis: () => void;
}

type DisplayMode = "chart" | "table";
type SortMode = "original" | "desc" | "asc";

const COLORS = ["#2563eb", "#0f766e", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#65a30d"];

const TYPE_ICONS: Record<VisualizationType, typeof BarChart3> = {
  bar: BarChart3,
  line: LineChartIcon,
  pie: PieChartIcon,
  scatter: ScatterChartIcon,
  histogram: BarChart3,
  box: Box,
  heatmap: Grid3X3,
  table: Table2,
};

function asNumber(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const parsed = Number(String(value ?? "").replace(/[,%$¥￥,]/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function isNumericValue(value: unknown): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  const normalized = String(value ?? "").replace(/[,%$¥￥,]/g, "").trim();
  return normalized !== "" && Number.isFinite(Number(normalized));
}

function getDataset(spec: VisualizationSpec | undefined, datasets: VisualizationDataset[]) {
  return datasets.find((dataset) => dataset.id === spec?.dataset_id) || datasets[0];
}

function localizeGeneratedLabel(value: string, language: "zh" | "en") {
  if (language !== "zh") return value;
  const exact: Record<string, string> = {
    "Count of Implausible Zero Values": "不合理零值数量",
    "Correlation Matrix": "相关性矩阵",
    "Box Plot Statistics for Key Variables": "关键变量箱线图统计",
  };
  if (exact[value]) return exact[value];

  const distribution = value.match(/^Distribution of (.+) by (.+)$/i);
  if (distribution) return `按 ${distribution[2]} 分组的 ${distribution[1]} 分布`;
  const featureCorrelation = value.match(/^Feature Correlation with (.+)$/i);
  if (featureCorrelation) return `特征与 ${featureCorrelation[1]} 的相关性`;
  const correlation = value.match(/^Correlation with (.+)$/i);
  if (correlation) return `与 ${correlation[1]} 的相关性`;
  return value;
}

function pivotSeries(rows: Array<Record<string, unknown>>, spec: VisualizationSpec) {
  if (!spec.x || !spec.y || !spec.series) return { rows, series: [] as string[] };
  const series = [...new Set(rows.map((row) => String(row[spec.series!] ?? "-")))];
  const grouped = new Map<string, Record<string, unknown>>();
  rows.forEach((row) => {
    const key = String(row[spec.x!] ?? "-");
    const current = grouped.get(key) || { [spec.x!]: row[spec.x!] };
    current[String(row[spec.series!] ?? "-")] = asNumber(row[spec.y!]);
    grouped.set(key, current);
  });
  return { rows: [...grouped.values()], series };
}

function DataTable({ dataset }: { dataset: VisualizationDataset }) {
  const keys = dataset.rows.length > 0 ? Object.keys(dataset.rows[0]) : [];
  const numericKeys = new Set(keys.filter((key) => dataset.rows.some((row) => isNumericValue(row[key]))));
  return (
    <div className="max-h-[520px] overflow-auto rounded-md border border-gray-200 dark:border-gray-700">
      <table className="w-full min-w-[680px] text-sm">
        <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
          <tr>{keys.map((key) => <th key={key} className="border-b border-gray-200 px-3 py-2 text-left font-medium text-gray-600 dark:border-gray-700 dark:text-gray-300">{key}</th>)}</tr>
        </thead>
        <tbody>
          {dataset.rows.map((row, index) => (
            <tr key={index} className="border-b border-gray-100 last:border-0 dark:border-gray-800">
              {keys.map((key) => <td key={key} className="px-3 py-2 text-gray-800 tabular-nums dark:text-gray-200">{formatDisplayValue(row[key], numericKeys.has(key))}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BoxPlot({ rows, spec }: { rows: Array<Record<string, unknown>>; spec: VisualizationSpec }) {
  const bounds = rows.flatMap((row) => [asNumber(row[spec.lower!]), asNumber(row[spec.upper!])]);
  const min = Math.min(...bounds);
  const max = Math.max(...bounds);
  const span = max - min || 1;
  const position = (value: unknown) => `${((asNumber(value) - min) / span) * 100}%`;

  return (
    <div className="space-y-4 py-3">
      <div className="ml-28 flex justify-between text-xs tabular-nums text-gray-400"><span>{formatFixedNumber(min)}</span><span>{formatFixedNumber(max)}</span></div>
      {rows.map((row, index) => {
        const lower = asNumber(row[spec.lower!]);
        const upper = asNumber(row[spec.upper!]);
        const q1 = asNumber(row[spec.q1!]);
        const q3 = asNumber(row[spec.q3!]);
        const median = asNumber(row[spec.median!]);
        return (
          <div key={index} className="grid grid-cols-[6.25rem_1fr] items-center gap-3">
            <div className="truncate text-right text-xs font-medium text-gray-700 dark:text-gray-200" title={String(row[spec.x!] ?? "-")}>{String(row[spec.x!] ?? "-")}</div>
            <div className="relative h-8" title={`Min ${formatFixedNumber(lower)} · Q1 ${formatFixedNumber(q1)} · Median ${formatFixedNumber(median)} · Q3 ${formatFixedNumber(q3)} · Max ${formatFixedNumber(upper)}`}>
              <div className="absolute top-1/2 h-px -translate-y-1/2 bg-gray-400" style={{ left: position(lower), width: `calc(${position(upper)} - ${position(lower)})` }} />
              <div className="absolute top-1/2 h-5 -translate-y-1/2 border border-blue-500 bg-blue-100 dark:bg-blue-950" style={{ left: position(q1), width: `calc(${position(q3)} - ${position(q1)})` }} />
              <div className="absolute top-1/2 h-6 w-0.5 -translate-y-1/2 bg-blue-700" style={{ left: position(median) }} />
              <div className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-gray-500" style={{ left: position(lower) }} />
              <div className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-gray-500" style={{ left: position(upper) }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Heatmap({ rows, spec }: { rows: Array<Record<string, unknown>>; spec: VisualizationSpec }) {
  const xs = [...new Set(rows.map((row) => String(row[spec.x!] ?? "-")))];
  const ys = [...new Set(rows.map((row) => String(row[spec.y!] ?? "-")))];
  const lookup = new Map(rows.map((row) => [`${String(row[spec.x!] ?? "-")}\u0000${String(row[spec.y!] ?? "-")}`, asNumber(row[spec.value!])]));
  const values = [...lookup.values()];
  const maxAbs = Math.max(...values.map(Math.abs), 1);
  const color = (value: number) => {
    const intensity = Math.min(Math.abs(value) / maxAbs, 1);
    return value >= 0 ? `rgba(37, 99, 235, ${0.1 + intensity * 0.8})` : `rgba(220, 38, 38, ${0.1 + intensity * 0.8})`;
  };

  return (
    <div className="overflow-auto pb-2">
      <div className="grid min-w-max gap-1" style={{ gridTemplateColumns: `7rem repeat(${xs.length}, minmax(4rem, 1fr))` }}>
        <div />
        {xs.map((x) => <div key={x} className="max-w-20 truncate px-1 pb-1 text-center text-xs text-gray-500" title={x}>{x}</div>)}
        {ys.flatMap((y) => [
          <div key={`${y}-label`} className="flex items-center justify-end truncate pr-2 text-xs text-gray-500" title={y}>{y}</div>,
          ...xs.map((x) => {
            const value = lookup.get(`${x}\u0000${y}`) ?? 0;
            return <div key={`${x}-${y}`} className="flex h-12 items-center justify-center rounded-sm text-xs font-medium tabular-nums text-gray-950" style={{ backgroundColor: color(value), color: Math.abs(value) / maxAbs > 0.55 ? "white" : undefined }} title={`${x} × ${y}: ${formatFixedNumber(value)}`}>{formatFixedNumber(value)}</div>;
          }),
        ])}
      </div>
    </div>
  );
}

function ChartView({ dataset, spec, sortMode }: { dataset: VisualizationDataset; spec: VisualizationSpec; sortMode: SortMode }) {
  const sourceRows = [...dataset.rows];
  const sortedRows = sortMode === "original" || !spec.y
    ? sourceRows
    : sourceRows.sort((a, b) => (sortMode === "desc" ? -1 : 1) * (asNumber(a[spec.y!]) - asNumber(b[spec.y!])));
  const pivoted = pivotSeries(sortedRows, spec);
  const chartRows = pivoted.rows;
  const yKeys = pivoted.series.length ? pivoted.series : (spec.y ? [spec.y] : []);
  const tooltipFormatter = (value: unknown) => formatDisplayValue(value);
  const scatterSeries = spec.series
    ? [...new Set(sortedRows.map((row) => String(row[spec.series!] ?? "-")))]
    : [];

  if (spec.type === "table") return <DataTable dataset={{ ...dataset, rows: sortedRows }} />;
  if (spec.type === "box") return <BoxPlot rows={sortedRows} spec={spec} />;
  if (spec.type === "heatmap") return <Heatmap rows={sortedRows} spec={spec} />;

  return (
    <div className="h-[380px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        {spec.type === "scatter" ? (
          <RechartsScatterChart margin={{ top: 12, right: 18, left: 4, bottom: 22 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey={spec.x} name={spec.x} tickFormatter={(value) => formatFixedNumber(Number(value))} />
            <YAxis type="number" dataKey={spec.y} name={spec.y} tickFormatter={(value) => formatFixedNumber(Number(value))} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={tooltipFormatter} />
            {scatterSeries.length > 0
              ? scatterSeries.map((series, index) => <Scatter key={series} name={series} dataKey={spec.y!} data={sortedRows.filter((row) => String(row[spec.series!] ?? "-") === series)} fill={COLORS[index % COLORS.length]} />)
              : <Scatter dataKey={spec.y!} data={sortedRows} fill={COLORS[0]} />}
            {scatterSeries.length > 0 && <Legend />}
          </RechartsScatterChart>
        ) : spec.type === "pie" ? (
          <PieChart>
            <Pie data={sortedRows} dataKey={spec.y!} nameKey={spec.x!} cx="50%" cy="50%" outerRadius={125} label={({ name, value }) => `${name}: ${formatDisplayValue(value)}`}>
              {sortedRows.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={tooltipFormatter} />
            <Legend />
          </PieChart>
        ) : spec.type === "line" ? (
          <LineChart data={chartRows} margin={{ top: 12, right: 18, left: 4, bottom: 22 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={spec.x} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => formatFixedNumber(Number(value))} />
            <Tooltip formatter={tooltipFormatter} />
            {yKeys.map((key, index) => <Line key={key} type="monotone" dataKey={key} stroke={COLORS[index % COLORS.length]} strokeWidth={2} dot={{ r: 3 }} />)}
            {yKeys.length > 1 && <Legend />}
          </LineChart>
        ) : (
          <BarChart data={chartRows} margin={{ top: 12, right: 18, left: 4, bottom: 28 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={spec.x} tick={{ fontSize: 11 }} angle={chartRows.length > 10 ? -25 : 0} textAnchor={chartRows.length > 10 ? "end" : "middle"} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => formatFixedNumber(Number(value))} />
            <Tooltip formatter={tooltipFormatter} />
            {yKeys.map((key, index) => <Bar key={key} dataKey={key} fill={COLORS[index % COLORS.length]} radius={[4, 4, 0, 0]} />)}
            {yKeys.length > 1 && <Legend />}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export function DataDashboard({ payload, onOpenAnalysis }: DataDashboardProps) {
  const { language, t } = useI18n();
  const model = useMemo(() => getDashboardModel(payload?.response), [payload]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("chart");
  const [sortMode, setSortMode] = useState<SortMode>("original");

  useEffect(() => {
    setSelectedIndex(0);
    setDisplayMode("chart");
    setSortMode("original");
  }, [payload]);

  const spec = model?.visualizations[selectedIndex] || model?.visualizations[0];
  const dataset = model && getDataset(spec, model.datasets);

  if (!payload || !model || !spec || !dataset) {
    return (
      <main className="flex flex-1 items-center justify-center bg-gray-50 px-6 py-12 dark:bg-gray-950">
        <div className="max-w-lg text-center">
          <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-gray-200 text-gray-500 dark:bg-gray-800 dark:text-gray-400"><BarChart3 className="h-6 w-6" /></div>
          <h1 className="text-xl font-semibold text-gray-950 dark:text-white">{t("noDashboard")}</h1>
          <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">{t("noDashboardDescription")}</p>
          <Button onClick={onOpenAnalysis} className="mt-6 bg-blue-600 hover:bg-blue-700"><ArrowLeft className="h-4 w-4" /> {t("openAnalysis")}</Button>
        </div>
      </main>
    );
  }

  const ActiveIcon = TYPE_ICONS[spec.type];
  const activeTitle = localizeGeneratedLabel(spec.title, language);
  const sortable = ["bar", "pie", "histogram"].includes(spec.type);
  const typeLabel = (type: VisualizationType) => language === "zh"
    ? ({ bar: "柱状图", line: "折线图", pie: "饼图", scatter: "散点图", histogram: "直方图", box: "箱线图", heatmap: "热力图", table: "数据表" } as Record<VisualizationType, string>)[type]
    : ({ bar: "Bar", line: "Line", pie: "Pie", scatter: "Scatter", histogram: "Histogram", box: "Box plot", heatmap: "Heatmap", table: "Table" } as Record<VisualizationType, string>)[type];

  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-950">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
        <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold text-gray-950 dark:text-white">{t("dashboardTitle")}</h1>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t("dashboardDescription")}</p>
          </div>
          <Button variant="outline" onClick={onOpenAnalysis} className="self-start lg:self-auto"><ArrowLeft className="h-4 w-4" /> {t("backToAnalysis")}</Button>
        </div>

        <div className="mb-6 border-l border-blue-500 pl-4">
          <div className="text-xs text-gray-500 dark:text-gray-400">{t("sourceQuestion")}</div>
          <div className="mt-1 text-sm font-medium text-gray-900 dark:text-white">{payload.question}</div>
        </div>

        {model.insights.length > 0 && (
          <section className="mb-6 border-y border-gray-200 py-4 dark:border-gray-800">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white"><Lightbulb className="h-4 w-4 text-amber-600" />{language === "zh" ? "值得关注的发现" : "Key findings"}</div>
            <div className="grid gap-x-8 gap-y-2 md:grid-cols-2">
              {model.insights.map((insight, index) => <div key={index} className="flex gap-2 text-sm leading-6 text-gray-700 dark:text-gray-300"><span className="font-medium text-blue-600">{index + 1}.</span><span>{insight.replace(/^\s*\d+[.、)]\s*/, "")}</span></div>)}
            </div>
          </section>
        )}

        <div className="grid gap-5 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <aside className="min-w-0">
            <div className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">{language === "zh" ? `图表目录 · ${model.visualizations.length}` : `Visuals · ${model.visualizations.length}`}</div>
            <div className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible">
              {model.visualizations.map((visualization, index) => {
                const Icon = TYPE_ICONS[visualization.type];
                const active = index === selectedIndex;
                return (
                  <button key={`${visualization.dataset_id}-${index}`} type="button" onClick={() => { setSelectedIndex(index); setDisplayMode(visualization.type === "table" ? "table" : "chart"); setSortMode("original"); }} className={`flex min-w-52 items-start gap-3 rounded-md border p-3 text-left transition-colors lg:min-w-0 ${active ? "border-blue-300 bg-blue-50 text-blue-950 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-100" : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"}`}>
                    <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${active ? "text-blue-600" : "text-gray-400"}`} />
                    <span className="min-w-0"><span className="block text-sm font-medium leading-5">{localizeGeneratedLabel(visualization.title, language)}</span><span className="mt-1 block text-xs text-gray-500 dark:text-gray-400">{typeLabel(visualization.type)} · {model.datasets.find((item) => item.id === visualization.dataset_id)?.rows.length || 0} {language === "zh" ? "个数据点" : "points"}</span></span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="min-w-0 rounded-md border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <div className="flex flex-col gap-3 border-b border-gray-200 p-4 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2"><ActiveIcon className="h-4 w-4 flex-shrink-0 text-blue-600" /><h2 className="truncate text-base font-semibold text-gray-950 dark:text-white">{activeTitle}</h2></div>
                {spec.description && <p className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">{spec.description}</p>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {sortable && displayMode === "chart" && (
                  <Select value={sortMode} onValueChange={(value) => setSortMode(value as SortMode)}><SelectTrigger className="h-8 w-32 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="original">{language === "zh" ? "原始顺序" : "Original"}</SelectItem><SelectItem value="desc">{t("descending")}</SelectItem><SelectItem value="asc">{t("ascending")}</SelectItem></SelectContent></Select>
                )}
                <div className="flex rounded-md border border-gray-200 p-0.5 dark:border-gray-700">
                  <button type="button" disabled={spec.type === "table"} onClick={() => setDisplayMode("chart")} className={`flex h-7 items-center gap-1 rounded px-2 text-xs ${displayMode === "chart" ? "bg-gray-100 font-medium text-gray-900 dark:bg-gray-800 dark:text-white" : "text-gray-500"}`}><BarChart3 className="h-3.5 w-3.5" />{language === "zh" ? "图表" : "Chart"}</button>
                  <button type="button" onClick={() => setDisplayMode("table")} className={`flex h-7 items-center gap-1 rounded px-2 text-xs ${displayMode === "table" ? "bg-gray-100 font-medium text-gray-900 dark:bg-gray-800 dark:text-white" : "text-gray-500"}`}><Table2 className="h-3.5 w-3.5" />{language === "zh" ? "数据" : "Data"}</button>
                </div>
              </div>
            </div>
            <div className="p-4 sm:p-6">
              {displayMode === "table" ? <DataTable dataset={dataset} /> : <ChartView dataset={dataset} spec={spec} sortMode={sortMode} />}
              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400"><span><Database className="mr-1 inline h-3.5 w-3.5" />{localizeGeneratedLabel(dataset.name, language)}</span><span>{dataset.rows.length} {language === "zh" ? "行" : "rows"}</span>{model.generatedFromLegacyRows && <span>{language === "zh" ? "兼容旧版结果自动生成" : "Generated from a legacy result"}</span>}</div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
