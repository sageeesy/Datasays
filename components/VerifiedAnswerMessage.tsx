import { useState } from "react";
import {
  BarChart3,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Code2,
  Database,
  Route,
  ShieldCheck,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ResponseData } from "../lib/client";
import { isDashboardReady } from "../lib/appTypes";
import { formatDisplayValue, formatProseDecimals } from "../lib/numberFormat";
import { useI18n } from "../lib/i18n";
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
  select_skills: { zh: "选择分析 Skill", en: "Select analysis Skills" },
  retrieve_metrics: { zh: "检索指标定义", en: "Retrieve metric definitions" },
  plan_analysis: { zh: "制定分析计划", en: "Plan analysis" },
  request_clarification: { zh: "请求补充信息", en: "Request clarification" },
  generate_code: { zh: "生成分析代码", en: "Generate analysis code" },
  execute_code: { zh: "沙箱执行", en: "Sandbox execution" },
  validate_result: { zh: "验证执行结果", en: "Validate result" },
  repair_code: { zh: "修复并重试", en: "Repair and retry" },
  final_report: { zh: "生成可信答案", en: "Generate verified answer" },
};

const CHECK_LABELS: Record<string, { zh: string; en: string }> = {
  sandbox_execution: { zh: "沙箱执行", en: "Sandbox execution" },
  required_columns: { zh: "计划字段", en: "Required columns" },
  structured_result: { zh: "结构化结果", en: "Structured result" },
  metric_grounding: { zh: "指标依据", en: "Metric grounding" },
  result_metric_grounding: { zh: "结果指标依据", en: "Result metric grounding" },
  reported_columns: { zh: "证据字段", en: "Reported columns" },
  primary_value: { zh: "主结果类型", en: "Primary value" },
  numeric_faithfulness: { zh: "数值忠实度", en: "Numeric faithfulness" },
  visualization_contract: { zh: "可视化数据契约", en: "Visualization contract" },
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

export function VerifiedAnswerMessage({ response, timestamp, onOpenDashboard }: VerifiedAnswerMessageProps) {
  const { language, t } = useI18n();
  const [evidenceOpen, setEvidenceOpen] = useState(true);
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

  const localizedCheck = (check: any) => {
    if (language === "en") return check.message;
    const messages: Record<string, Record<string, string>> = {
      sandbox_execution: { pass: "沙箱代码执行成功。", fail: "沙箱代码执行失败。" },
      required_columns: { pass: "分析计划所需字段均存在。", fail: "分析计划引用了不存在的字段。" },
      structured_result: { pass: "沙箱返回了有效的结构化结果。", fail: "沙箱未按约定返回结构化结果。" },
      metric_grounding: { pass: "计划中的指标均有定义依据。", fail: "计划引用了没有定义依据的指标。" },
      result_metric_grounding: { pass: "结果指标与检索定义一致。", fail: "结果引用了没有定义依据的指标。" },
      reported_columns: { pass: "证据字段均来自上传数据。", fail: "结果报告了上传数据中不存在的字段。" },
      primary_value: { pass: "主结果与答案类型一致。", fail: "主结果与答案类型不匹配。" },
      numeric_faithfulness: { pass: "答案数值均可追溯到执行结果。", fail: "答案包含无法追溯的数值。" },
      visualization_contract: { pass: "数据看板契约完整。", fail: "可视化数据或图表规格不完整。" },
    };
    return messages[check.name]?.[check.status] || check.message;
  };

  const traceDescription = (step: any) => {
    if (language === "en") return step.thought;
    if (step.node === "select_skills") {
      const names = skills.map((skill) => skill.name).join("、") || "通用分析 Skill";
      const terms = skills.flatMap((skill) => skill.matched_terms || []);
      return `选择 ${names}。${terms.length ? `问题命中了“${terms.join("、")}”等特征词。` : "未命中专用模式，因此使用通用分析规则。"}`;
    }
    if (step.node === "retrieve_metrics") {
      return metrics.length
        ? `检索到 ${metrics.map((metric: any) => metric.name).join("、")}，用于约束计算口径和字段绑定。`
        : "本题不需要预定义业务指标，按数据字段直接计算。";
    }
    if (step.node === "plan_analysis") {
      const parts = [
        `分析意图：${plan?.intent || "other"}`,
        `字段：${plan?.required_columns?.join("、") || "无"}`,
        `分组：${plan?.dimensions?.join("、") || "无"}`,
        `聚合：${plan?.aggregation || "按问题确定"}`,
      ];
      return `${parts.join("；")}。执行时先校验字段，再计算并输出结构化结果。`;
    }
    if (step.node === "execute_code") return `第 ${Number(step.args?.attempt || 0) + 1} 次在隔离沙箱中运行分析代码。`;
    if (step.node === "validate_result") {
      const passed = checks.filter((check: any) => check.status === "pass").length;
      const failed = checks.filter((check: any) => check.status === "fail").length;
      return `检查执行、字段、指标和结果契约：${passed} 项通过，${failed} 项失败。`;
    }
    if (step.node === "repair_code") return `根据执行错误和验证反馈进行第 ${step.args?.attempt || 1} 次代码修复。`;
    return step.thought;
  };

  const output = response.output;
  const tableHeaders: string[] = output?.type === "table" ? output.data?.headers || [] : [];
  const tableRows: unknown[][] = output?.type === "table" ? output.data?.rows || [] : [];

  return (
    <div className="space-y-2">
      <Card className="overflow-hidden border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="p-4 sm:p-5">
          <div className="mb-4 flex min-w-0 items-center gap-2">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-blue-600">
              <ShieldCheck className="h-4 w-4 text-white" />
            </div>
            <span className="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{t("verifiedAnswer")}</span>
            <Badge className={`ml-auto flex-shrink-0 text-xs ${response.status === "success" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300" : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"}`}>
              {response.status === "success" ? t("verified") : t("failed")}
            </Badge>
          </div>

          <div className="prose prose-sm max-w-none break-words text-gray-900 dark:prose-invert dark:text-white">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{formatProseDecimals(response.content)}</ReactMarkdown>
          </div>

          {output?.type === "number" && (
            <div className="mt-4 border-y border-gray-200 py-4 text-center dark:border-gray-700">
              <div className="text-3xl font-semibold tabular-nums text-blue-600">{formatDisplayValue(output.data?.value)}</div>
              <div className="mt-1 text-sm text-gray-500">{output.data?.unit || output.data?.label}</div>
            </div>
          )}

          {tableRows.length > 0 && (
            <div className="mt-4 max-h-[420px] overflow-auto rounded-md border border-gray-200 dark:border-gray-700">
              <Table>
                <TableHeader>
                  <TableRow>{tableHeaders.map((header) => <TableHead key={header}>{header}</TableHead>)}</TableRow>
                </TableHeader>
                <TableBody>
                  {tableRows.map((row, rowIndex) => (
                    <TableRow key={rowIndex}>
                      {row.map((cell, cellIndex) => <TableCell key={cellIndex} className={cellIndex ? "tabular-nums" : "font-medium"}>{formatDisplayValue(cell, cellIndex > 0)}</TableCell>)}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {isDashboardReady(response) && onOpenDashboard && (
            <Button variant="outline" onClick={onOpenDashboard} className="mt-4 border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-900 dark:text-blue-300">
              <BarChart3 className="h-4 w-4" /> {t("viewDashboard")}
            </Button>
          )}
        </div>

        {metadata?.agent_mode && (
          <Collapsible open={evidenceOpen} onOpenChange={setEvidenceOpen} className="border-t border-gray-200 dark:border-gray-700">
            <SectionTrigger open={evidenceOpen} icon={<ShieldCheck className="h-4 w-4 text-emerald-600" />} label={t("evidence")} />
            <CollapsibleContent className="space-y-4 px-4 pb-4 text-sm sm:px-5">
              {metrics.length > 0 && (
                <section>
                  <h4 className="mb-2 flex items-center gap-2 font-medium text-gray-800 dark:text-gray-100"><Database className="h-4 w-4" />{t("metricDefinitions")}</h4>
                  <div className="space-y-2">
                    {metrics.map((metric: any) => (
                      <div key={metric.id} className="border-l-2 border-blue-500 pl-3 text-gray-600 dark:text-gray-300">
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
                    <div><dt className="inline font-medium">{t("intent")}：</dt><dd className="inline">{plan.intent}</dd></div>
                    <div><dt className="inline font-medium">{t("aggregation")}：</dt><dd className="inline">{plan.aggregation || t("unspecified")}</dd></div>
                    <div className="sm:col-span-2"><dt className="inline font-medium">{t("columns")}：</dt><dd className="inline">{plan.required_columns?.join("、") || t("none")}</dd></div>
                    <div className="sm:col-span-2"><dt className="inline font-medium">{t("filters")}：</dt><dd className="inline">{plan.filters?.join("；") || t("none")}</dd></div>
                  </dl>
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
                </section>
              )}
              {(result?.assumptions?.length || 0) > 0 && (
                <p className="text-gray-600 dark:text-gray-300">
                  <strong>{t("assumptions")}：</strong>{result?.assumptions?.join("；")}
                </p>
              )}
            </CollapsibleContent>
          </Collapsible>
        )}

        {steps.length > 0 && (
          <Collapsible open={traceOpen} onOpenChange={setTraceOpen} className="border-t border-gray-200 dark:border-gray-700">
            <SectionTrigger open={traceOpen} icon={<Route className="h-4 w-4 text-blue-600" />} label={t("workflowTrace")} />
            <CollapsibleContent className="space-y-2 px-4 pb-4 sm:px-5">
              {steps.map((step) => (
                <div key={`${step.step}-${step.node}`} className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{step.step}</Badge>
                    <span className="font-medium text-gray-900 dark:text-white">{TRACE_LABELS[step.node]?.[language] || step.node}</span>
                    {step.duration_ms != null && <span className="ml-auto text-xs text-gray-400">{step.duration_ms}ms</span>}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">{traceDescription(step)}</p>
                  <details className="mt-2 text-xs text-gray-500">
                    <summary className="cursor-pointer font-medium">{t("traceObservation")}</summary>
                    <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-gray-50 p-2 dark:bg-gray-900">{step.observation}</pre>
                  </details>
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>
        )}

        {response.thinking_process?.trim() && (
          <Collapsible open={reasoningOpen} onOpenChange={setReasoningOpen} className="border-t border-gray-200 dark:border-gray-700">
            <SectionTrigger open={reasoningOpen} icon={<CheckCircle className="h-4 w-4 text-gray-500" />} label={t("reasoningSummary")} />
            <CollapsibleContent className="px-4 pb-4 text-sm leading-6 text-gray-600 dark:text-gray-300 sm:px-5">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.thinking_process}</ReactMarkdown>
            </CollapsibleContent>
          </Collapsible>
        )}

        {response.code && (
          <Collapsible open={codeOpen} onOpenChange={setCodeOpen} className="border-t border-gray-200 dark:border-gray-700">
            <SectionTrigger open={codeOpen} icon={<Code2 className="h-4 w-4 text-gray-500" />} label={t("generatedCode")} />
            <CollapsibleContent className="px-4 pb-4 sm:px-5">
              <pre className="max-h-[480px] overflow-auto rounded-md bg-gray-950 p-4 text-xs leading-5 text-gray-100"><code>{response.code}</code></pre>
            </CollapsibleContent>
          </Collapsible>
        )}
      </Card>
      <div className="text-center text-xs text-gray-400">{timestamp}</div>
    </div>
  );
}
