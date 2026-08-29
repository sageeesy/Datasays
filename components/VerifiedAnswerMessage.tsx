import { useState } from "react";
import {
  BarChart3,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Code2,
  Database,
  Lightbulb,
  Route,
  ShieldCheck,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ResponseData, ResultEvidence } from "../lib/client";
import { isDashboardReady } from "../lib/appTypes";
import {
  formatDisplayValue,
  formatEvidenceUnit,
  formatEvidenceValue,
  formatProseDecimals,
} from "../lib/numberFormat";
import { useI18n, type Language } from "../lib/i18n";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

interface VerifiedAnswerMessageProps {
  response: ResponseData;
  timestamp: string;
  onOpenDashboard?: () => void;
}

const TRACE_LABELS: Record<string, { zh: string; en: string }> = {
  profile_data: { zh: "生成数据画像", en: "Profile data" },
  load_memory: { zh: "加载分析上下文", en: "Load analysis context" },
  select_skill: { zh: "选择分析方法", en: "Select analysis method" },
  select_skills: { zh: "选择分析方法", en: "Select analysis methods" },
  retrieve_metrics: { zh: "匹配指标口径", en: "Ground metric definitions" },
  plan_analysis: { zh: "制定分析计划", en: "Plan analysis" },
  request_clarification: { zh: "请求补充信息", en: "Request clarification" },
  generate_code: { zh: "生成分析代码", en: "Generate analysis code" },
  repair_visualization_policy: { zh: "修正可视化协议", en: "Repair visualization contract" },
  execute_code: { zh: "执行分析", en: "Execute analysis" },
  validate_result: { zh: "检查分析结果", en: "Check analysis result" },
  repair_code: { zh: "修复并重试", en: "Repair and retry" },
  finalize_response: { zh: "生成最终回答", en: "Prepare final answer" },
  final_report: { zh: "生成最终回答", en: "Prepare final answer" },
};

const CHECK_LABELS: Record<string, { zh: string; en: string }> = {
  sandbox_execution: { zh: "代码执行", en: "Code execution" },
  required_columns: { zh: "计划字段", en: "Required columns" },
  structured_result: { zh: "结构化结果", en: "Structured result" },
  metric_grounding: { zh: "指标依据", en: "Metric grounding" },
  result_metric_grounding: { zh: "结果指标依据", en: "Result metric grounding" },
  reported_columns: { zh: "引用字段", en: "Referenced fields" },
  primary_value: { zh: "主结果类型", en: "Primary value" },
  numeric_faithfulness: { zh: "数值忠实度", en: "Numeric faithfulness" },
  visualization_contract: { zh: "可视化数据契约", en: "Visualization contract" },
  result_evidence_coverage: { zh: "Evidence 覆盖", en: "Evidence coverage" },
};

const INTENT_LABELS: Record<string, { zh: string; en: string }> = {
  lookup: { zh: "查询与筛选", en: "Lookup and filtering" },
  aggregation: { zh: "汇总分析", en: "Aggregation" },
  ranking: { zh: "排名分析", en: "Ranking" },
  trend: { zh: "趋势分析", en: "Trend analysis" },
  cohort: { zh: "分群分析", en: "Cohort analysis" },
  data_quality: { zh: "数据质量分析", en: "Data quality analysis" },
  metric_diagnostic: { zh: "指标诊断", en: "Metric diagnostics" },
  modeling: { zh: "建模分析", en: "Modeling" },
};

function SectionTrigger({ open, icon, label }: { open: boolean; icon: React.ReactNode; label: string }) {
  return (
    <CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-900">
      {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
      {icon}
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-800 dark:text-gray-100">{label}</span>
    </CollapsibleTrigger>
  );
}

function formatFilterValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item)).join("、");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function formatPlanFilter(filter: any, language: Language): string {
  const field = String(filter?.column || "-");
  const value = formatFilterValue(filter?.value);
  const operators: Record<string, { zh: string; en: string }> = {
    eq: { zh: "等于", en: "equals" },
    ne: { zh: "不等于", en: "does not equal" },
    gt: { zh: "大于", en: "is greater than" },
    gte: { zh: "大于等于", en: "is at least" },
    lt: { zh: "小于", en: "is less than" },
    lte: { zh: "小于等于", en: "is at most" },
    in: { zh: "属于", en: "is in" },
    not_in: { zh: "不属于", en: "is not in" },
    between: { zh: "介于", en: "is between" },
    is_null: { zh: "为空", en: "is null" },
    not_null: { zh: "不为空", en: "is not null" },
  };
  const operator = operators[filter?.operator]?.[language] || String(filter?.operator || "");
  if (["is_null", "not_null"].includes(filter?.operator)) return `${field} ${operator}`;
  if (filter?.operator === "between" && Array.isArray(filter?.value) && filter.value.length >= 2) {
    return language === "zh"
      ? `${field} 在 ${filter.value[0]} 至 ${filter.value[1]} 之间`
      : `${field} is between ${filter.value[0]} and ${filter.value[1]}`;
  }
  return `${field} ${operator} ${value}`.trim();
}

function EvidenceKpiGrid({
  evidence,
  language,
  projectId,
}: {
  evidence: ResultEvidence[];
  language: Language;
  projectId?: string | null;
}) {
  if (evidence.length === 0) return null;
  return (
    <section className="mt-4" aria-label={language === "zh" ? "核心指标" : "Headline metrics"}>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {evidence.map((item, index) => {
          const unit = formatEvidenceUnit(item, { language, projectId });
          return (
            <div key={`${item.plan_metric_key || item.label || "metric"}-${index}`} className="min-w-0 rounded-md border border-gray-200 bg-gray-50 px-3 py-3 dark:border-gray-700 dark:bg-gray-900/60">
              <div className="min-h-10 break-words text-xs leading-5 text-gray-500 dark:text-gray-400">
                {item.label || item.plan_metric_key || (language === "zh" ? "指标" : "Metric")}
              </div>
              <div className="mt-1 break-words text-xl font-semibold tabular-nums text-gray-950 dark:text-white">
                {formatEvidenceValue(item, { language, projectId })}
              </div>
              {unit && <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{unit}</div>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function VerifiedAnswerMessage({ response, timestamp, onOpenDashboard }: VerifiedAnswerMessageProps) {
  const { language, t } = useI18n();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [methodologyOpen, setMethodologyOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [codeOpen, setCodeOpen] = useState(false);

  const metadata = response.metadata;
  const result = metadata?.analysis_result;
  const plan = metadata?.plan;
  const validation = metadata?.validation_report;
  const checks = validation?.checks || [];
  const metrics = metadata?.retrieved_metrics || [];
  const skills = metadata?.selected_skills || [];
  const steps = metadata?.agent_steps || [];
  const evidence = result?.evidence || [];
  const scalarEvidence = evidence.filter((item) => item.kind === "scalar" && item.value != null);
  const insights = (result?.insights || []).filter(Boolean).slice(0, 3);
  const hasFailures = response.status !== "success"
    || validation?.passed === false
    || checks.some((check: any) => check.status === "fail");
  const hasWarnings = checks.some((check: any) => check.status === "warning");
  const verificationText = hasFailures
    ? t("verificationFailed")
    : hasWarnings
      ? t("verificationWarning")
      : t("verified");
  const verificationClass = hasFailures
    ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
    : hasWarnings
      ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
      : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300";

  const localizedCheck = (check: any) => {
    if (language === "en") return check.message;
    const messages: Record<string, Record<string, string>> = {
      sandbox_execution: { pass: "分析代码执行成功。", fail: "分析代码执行失败。" },
      required_columns: { pass: "分析计划所需字段均存在。", fail: "分析计划引用了不存在的字段。" },
      structured_result: { pass: "返回了有效的结构化结果。", fail: "没有按约定返回结构化结果。" },
      metric_grounding: { pass: "计划中的指标均有定义依据。", fail: "计划引用了没有定义依据的指标。" },
      result_metric_grounding: { pass: "结果指标与检索定义一致。", fail: "结果引用了没有定义依据的指标。" },
      reported_columns: { pass: "结果引用的字段均来自上传数据。", fail: "结果报告了上传数据中不存在的字段。" },
      primary_value: { pass: "主结果与答案类型一致。", fail: "主结果与答案类型不匹配。" },
      numeric_faithfulness: { pass: "答案数值均可追溯到执行结果。", fail: "答案包含无法追溯的数值。" },
      visualization_contract: { pass: "数据看板契约完整。", fail: "可视化数据或图表规格不完整。" },
      result_evidence_coverage: { pass: "每个计划指标都有机器可读 Evidence。", warning: "部分计划指标缺少完整 Evidence。", fail: "Evidence 覆盖检查未通过。" },
    };
    return messages[check.name]?.[check.status] || check.message;
  };

  const traceDescription = (step: any) => {
    if (language === "en") return step.thought;
    if (step.node === "profile_data") return "读取字段类型、缺失情况、日期范围和候选键，为后续分析建立数据画像。";
    if (step.node === "select_skills") {
      const names = skills.map((skill) => skill.name).join("、") || "通用分析方法";
      const terms = skills.flatMap((skill) => skill.matched_terms || []);
      return `选择 ${names}。${terms.length ? `问题命中了“${terms.join("、")}”等特征词。` : "未命中专用模式，因此使用通用分析规则。"}`;
    }
    if (step.node === "load_memory") {
      const memory = metadata?.memory;
      return memory?.used
        ? `加载 ${memory.recent_message_count || 0} 条近期消息和 ${memory.verified_finding_count || 0} 条已检查结论。`
        : "当前没有可复用的历史上下文，本轮按独立问题处理。";
    }
    if (step.node === "retrieve_metrics") {
      return metrics.length
        ? `匹配到 ${metrics.map((metric: any) => metric.name).join("、")}，用于约束计算口径和字段绑定。`
        : "本题不需要预定义业务指标，按数据字段直接计算。";
    }
    if (step.node === "plan_analysis") {
      const parts = [
        `分析类型：${INTENT_LABELS[plan?.intent]?.zh || plan?.intent || "未指定"}`,
        `字段：${plan?.required_columns?.join("、") || "无"}`,
        `分组：${plan?.dimensions?.join("、") || "无"}`,
      ];
      return `${parts.join("；")}。计划通过完整性检查后才会进入计算。`;
    }
    if (step.node === "generate_code") return "已根据结构化计划生成 Python 分析代码。";
    if (step.node === "repair_visualization_policy") return "已将图像生成改为结构化可视化数据输出。";
    if (step.node === "execute_code") return `第 ${Number(step.args?.attempt || 0) + 1} 次在隔离沙箱中执行分析。`;
    if (step.node === "validate_result") {
      const passed = checks.filter((check: any) => check.status === "pass").length;
      const failed = checks.filter((check: any) => check.status === "fail").length;
      return `检查代码执行、字段、指标和结果契约：${passed} 项通过，${failed} 项失败。`;
    }
    if (step.node === "repair_code") return `根据执行错误和检查反馈进行第 ${step.args?.attempt || 1} 次修复。`;
    if (step.node === "request_clarification") return "当前信息会影响分析口径，因此在计算前请求补充说明。";
    if (["finalize_response", "final_report"].includes(step.node)) return "已将计算结果整理为用户回答，并检查最终文字中的数值是否可追溯。";
    return "该内部步骤已完成。原始记录可在下方展开查看。";
  };

  const output = response.output;
  const tableHeaders: string[] = output?.type === "table" ? output.data?.headers || [] : [];
  const tableRows: unknown[][] = output?.type === "table" ? output.data?.rows || [] : [];
  const answerSummary = result?.summary || response.content;

  return (
    <div className="space-y-2">
      <Card className="overflow-hidden border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="p-4 sm:p-5">
          <div className="mb-4 flex min-w-0 items-start gap-2">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-blue-600">
              <ShieldCheck className="h-4 w-4 text-white" />
            </div>
            <span className="min-w-0 flex-1 pt-1 text-sm font-medium text-gray-800 dark:text-gray-100">{t("verifiedAnswer")}</span>
            <Badge className={`max-w-44 flex-shrink-0 whitespace-normal text-center text-[11px] leading-4 sm:max-w-none ${verificationClass}`}>
              {verificationText}
            </Badge>
          </div>

          <div className="prose prose-sm max-w-none break-words text-gray-900 dark:prose-invert dark:text-white">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{formatProseDecimals(answerSummary)}</ReactMarkdown>
          </div>

          <EvidenceKpiGrid evidence={scalarEvidence} language={language} projectId={metadata?.project_id} />

          {insights.length > 0 && (
            <section className="mt-5 border-t border-gray-100 pt-4 dark:border-gray-700">
              <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
                <Lightbulb className="h-4 w-4 text-amber-600" />{t("keyFindings")}
              </h4>
              <ul className="space-y-2 text-sm leading-6 text-gray-700 dark:text-gray-300">
                {insights.map((insight, index) => <li key={index} className="flex gap-2"><span className="font-medium text-blue-600">{index + 1}.</span><span>{formatProseDecimals(insight.replace(/^\s*\d+[.、)]\s*/, ""))}</span></li>)}
              </ul>
            </section>
          )}

          {isDashboardReady(response) && onOpenDashboard && (
            <Button variant="outline" onClick={onOpenDashboard} className="mt-4 border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-900 dark:text-blue-300">
              <BarChart3 className="h-4 w-4" /> {t("viewDashboard")}
            </Button>
          )}

          {output?.type === "number" && scalarEvidence.length === 0 && (
            <div className="mt-4 border-y border-gray-200 py-4 text-center dark:border-gray-700">
              <div className="text-3xl font-semibold tabular-nums text-blue-600">{formatDisplayValue(output.data?.value)}</div>
              <div className="mt-1 text-sm text-gray-500">{output.data?.unit || output.data?.label}</div>
            </div>
          )}

          {tableRows.length > 0 && (
            <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen} className="mt-4 overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
              <SectionTrigger open={detailsOpen} icon={<Database className="h-4 w-4 text-gray-500" />} label={`${t("resultDetails")} · ${tableRows.length}`} />
              <CollapsibleContent className="border-t border-gray-200 dark:border-gray-700">
                <div className="max-h-[420px] overflow-auto">
                  <Table>
                    <TableHeader><TableRow>{tableHeaders.map((header) => <TableHead key={header}>{header}</TableHead>)}</TableRow></TableHeader>
                    <TableBody>
                      {tableRows.map((row, rowIndex) => (
                        <TableRow key={rowIndex}>{row.map((cell, cellIndex) => <TableCell key={cellIndex} className={cellIndex ? "tabular-nums" : "font-medium"}>{formatDisplayValue(cell, cellIndex > 0)}</TableCell>)}</TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}

          {(result?.assumptions?.length || 0) > 0 && (
            <Collapsible open={methodologyOpen} onOpenChange={setMethodologyOpen} className="mt-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
              <SectionTrigger open={methodologyOpen} icon={<CheckCircle className="h-4 w-4 text-gray-500" />} label={t("methodologyAndLimits")} />
              <CollapsibleContent className="border-t border-gray-200 px-4 py-3 dark:border-gray-700">
                <ul className="space-y-2 text-sm leading-6 text-gray-600 dark:text-gray-300">
                  {result?.assumptions?.map((assumption, index) => <li key={index} className="flex gap-2"><span>•</span><span>{assumption}</span></li>)}
                </ul>
              </CollapsibleContent>
            </Collapsible>
          )}
        </div>

        {metadata?.agent_mode && (
          <Collapsible open={evidenceOpen} onOpenChange={setEvidenceOpen} className="border-t border-gray-200 dark:border-gray-700">
            <SectionTrigger open={evidenceOpen} icon={<ShieldCheck className="h-4 w-4 text-emerald-600" />} label={t("evidence")} />
            <CollapsibleContent className="space-y-5 px-4 pb-4 text-sm sm:px-5">
              {metrics.length > 0 && (
                <section>
                  <h4 className="mb-2 flex items-center gap-2 font-medium text-gray-800 dark:text-gray-100"><Database className="h-4 w-4" />{t("metricDefinitions")}</h4>
                  <div className="space-y-2">
                    {metrics.map((metric: any) => (
                      <div key={metric.id} className="border-l border-blue-500 pl-3 text-gray-600 dark:text-gray-300">
                        <div className="font-medium text-gray-900 dark:text-white">{metric.name}</div>
                        <div>{metric.formula}</div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {plan && (
                <section>
                  <h4 className="mb-2 font-medium text-gray-800 dark:text-gray-100">{t("analysisPlan")}</h4>
                  <dl className="grid grid-cols-1 gap-2 text-gray-600 dark:text-gray-300 sm:grid-cols-2">
                    <div><dt className="inline font-medium">{t("intent")}：</dt><dd className="inline">{INTENT_LABELS[plan.intent]?.[language] || plan.intent}</dd></div>
                    {plan.time_field && <div><dt className="inline font-medium">{language === "zh" ? "时间" : "Time"}：</dt><dd className="inline">{plan.time_field}{plan.time_grain ? ` · ${plan.time_grain}` : ""}</dd></div>}
                    {plan.analysis_scope && <div className="sm:col-span-2"><dt className="inline font-medium">{language === "zh" ? "分析范围" : "Scope"}：</dt><dd className="inline">{plan.analysis_scope}</dd></div>}
                    {plan.entity_grain && <div className="sm:col-span-2"><dt className="inline font-medium">{language === "zh" ? "数据粒度" : "Grain"}：</dt><dd className="inline">{plan.entity_grain}</dd></div>}
                    <div className="sm:col-span-2"><dt className="inline font-medium">{t("columns")}：</dt><dd className="inline">{plan.required_columns?.join("、") || t("none")}</dd></div>
                    <div className="sm:col-span-2"><dt className="inline font-medium">{t("filters")}：</dt><dd className="inline">{plan.filters?.length ? plan.filters.map((filter: any) => formatPlanFilter(filter, language)).join("；") : t("none")}</dd></div>
                  </dl>
                </section>
              )}

              {evidence.length > 0 && (
                <section>
                  <h4 className="mb-2 font-medium text-gray-800 dark:text-gray-100">{t("resultEvidence")}</h4>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {evidence.map((item, index) => (
                      <div key={`${item.plan_metric_key || item.label || "evidence"}-${index}`} className="min-w-0 rounded-md border border-gray-200 px-3 py-2 dark:border-gray-700">
                        <div className="font-medium text-gray-900 dark:text-white">{item.label || item.plan_metric_key || t("adHoc")}</div>
                        <div className="mt-1 break-words text-xs text-gray-500 dark:text-gray-400">
                          {item.kind === "scalar"
                            ? formatEvidenceValue(item, { language, projectId: metadata?.project_id })
                            : `${item.dataset_id || "-"} · ${item.value_field || "-"}`}
                        </div>
                        {item.plan_metric_key && <code className="mt-1 block break-all text-[11px] text-gray-400">{item.plan_metric_key}</code>}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {checks.length > 0 && (
                <section>
                  <h4 className="mb-2 font-medium text-gray-800 dark:text-gray-100">{t("checks")}</h4>
                  <div className="space-y-2">
                    {checks.map((check: any) => (
                      <div key={check.name} className="flex items-start gap-2 text-gray-600 dark:text-gray-300">
                        <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${check.status === "pass" ? "bg-emerald-500" : check.status === "warning" ? "bg-amber-500" : "bg-red-500"}`} />
                        <span><strong className="text-gray-800 dark:text-gray-100">{CHECK_LABELS[check.name]?.[language] || check.name}：</strong>{localizedCheck(check)}</span>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-xs leading-5 text-gray-500 dark:text-gray-400">{t("verificationScope")}</p>
                </section>
              )}

              {(steps.length > 0 || response.thinking_process?.trim() || response.code) && (
                <section className="border-t border-gray-200 pt-4 dark:border-gray-700">
                  <h4 className="mb-2 text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{t("developerDetails")}</h4>
                  <div className="space-y-2">
                    {steps.length > 0 && (
                      <Collapsible open={traceOpen} onOpenChange={setTraceOpen} className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
                        <SectionTrigger open={traceOpen} icon={<Route className="h-4 w-4 text-blue-600" />} label={t("workflowTrace")} />
                        <CollapsibleContent className="space-y-2 border-t border-gray-200 px-3 py-3 dark:border-gray-700">
                          {steps.map((step) => (
                            <div key={`${step.step}-${step.node}`} className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
                              <div className="flex items-center gap-2">
                                <Badge variant="outline">{step.step}</Badge>
                                <span className="font-medium text-gray-900 dark:text-white">{TRACE_LABELS[step.node]?.[language] || (language === "zh" ? "内部步骤" : "Internal step")}</span>
                                {step.duration_ms != null && <span className="ml-auto text-xs text-gray-400">{step.duration_ms}ms</span>}
                              </div>
                              <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">{traceDescription(step)}</p>
                              <details className="mt-2 text-xs text-gray-500">
                                <summary className="cursor-pointer font-medium">{t("traceObservation")} · <code>{step.node}</code></summary>
                                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-gray-50 p-2 dark:bg-gray-900">{step.observation}</pre>
                              </details>
                            </div>
                          ))}
                        </CollapsibleContent>
                      </Collapsible>
                    )}

                    {response.thinking_process?.trim() && (
                      <Collapsible open={reasoningOpen} onOpenChange={setReasoningOpen} className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
                        <SectionTrigger open={reasoningOpen} icon={<CheckCircle className="h-4 w-4 text-gray-500" />} label={t("reasoningSummary")} />
                        <CollapsibleContent className="border-t border-gray-200 px-4 py-3 text-sm leading-6 text-gray-600 dark:border-gray-700 dark:text-gray-300">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.thinking_process}</ReactMarkdown>
                        </CollapsibleContent>
                      </Collapsible>
                    )}

                    {response.code && (
                      <Collapsible open={codeOpen} onOpenChange={setCodeOpen} className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
                        <SectionTrigger open={codeOpen} icon={<Code2 className="h-4 w-4 text-gray-500" />} label={t("generatedCode")} />
                        <CollapsibleContent className="border-t border-gray-200 p-3 dark:border-gray-700">
                          <pre className="max-h-[480px] overflow-auto rounded-md bg-gray-950 p-4 text-xs leading-5 text-gray-100"><code>{response.code}</code></pre>
                        </CollapsibleContent>
                      </Collapsible>
                    )}
                  </div>
                </section>
              )}
            </CollapsibleContent>
          </Collapsible>
        )}
      </Card>
      <div className="text-center text-xs text-gray-400">{timestamp}</div>
    </div>
  );
}
