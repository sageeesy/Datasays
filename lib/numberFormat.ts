import type { ResultEvidence } from "./client";

export function formatFixedNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

type DisplayLanguage = "zh" | "en";

interface EvidenceFormatOptions {
  language: DisplayLanguage;
  projectId?: string | null;
}

const PERCENT_SEMANTIC_PATTERN = /(rate|share|accuracy|precision|recall|f1|conversion|retention|churn|delivery|占比|比率|率|准确率|精确率|召回率)/i;
const ZERO_TO_ONE_SEMANTIC_PATTERN = /(auc|correlation|coefficient|r[_ -]?squared|r2|effect[_ -]?size|相关|系数|效应量)/i;

function evidenceSemanticText(evidence: ResultEvidence): string {
  return `${evidence.plan_metric_key || ""} ${evidence.label || ""}`;
}

function currencyCode(evidence: ResultEvidence, projectId?: string | null): string | null {
  const unit = String(evidence.unit || "").trim().toLowerCase();
  if (unit === "brl" || unit === "r$") return "BRL";
  if (unit === "usd" || unit === "$") return "USD";
  if (unit === "cny" || unit === "rmb" || unit === "¥" || unit === "￥") return "CNY";
  if (unit === "currency" && projectId === "olist") return "BRL";
  return null;
}

function shouldRenderFractionAsPercent(evidence: ResultEvidence): boolean {
  const semantic = evidenceSemanticText(evidence);
  if (ZERO_TO_ONE_SEMANTIC_PATTERN.test(semantic)) return false;
  return PERCENT_SEMANTIC_PATTERN.test(semantic);
}

export function formatEvidenceValue(
  evidence: ResultEvidence,
  { language, projectId }: EvidenceFormatOptions,
): string {
  const value = evidence.value;
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "-");

  const locale = language === "zh" ? "zh-CN" : "en-US";
  const currency = currencyCode(evidence, projectId);
  if (currency) {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }

  if (evidence.value_scale === "percent") {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value)}%`;
  }

  if (evidence.value_scale === "fraction") {
    if (shouldRenderFractionAsPercent(evidence)) {
      return `${new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value * 100)}%`;
    }
    return new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value);
  }

  if (Number.isInteger(value)) {
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
  }

  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatEvidenceUnit(
  evidence: ResultEvidence,
  { language, projectId }: EvidenceFormatOptions,
): string | null {
  if (!evidence.unit || currencyCode(evidence, projectId)) return null;
  const normalized = evidence.unit.trim().toLowerCase();
  if (["count", "proportion", "ratio", "fraction", "percent"].includes(normalized)) return null;
  if (normalized === "currency") return language === "zh" ? "货币" : "Currency";
  return evidence.unit;
}

export function formatDisplayValue(value: unknown, fixed = true): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return fixed ? formatFixedNumber(value) : String(value);
  }

  if (fixed && typeof value === "string") {
    const match = value.trim().match(/^([$¥￥]?)(-?\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?)(%?)$/);
    if (match) {
      const numericValue = Number(match[2].replace(/,/g, ""));
      if (Number.isFinite(numericValue)) {
        return `${match[1]}${formatFixedNumber(numericValue)}${match[3]}`;
      }
    }
  }

  return String(value ?? "-");
}

export function formatProseDecimals(content: string): string {
  return content
    .split(/(```[\s\S]*?```|`[^`]*`)/g)
    .map((part, index) => {
      if (index % 2 === 1) return part;
      return part.replace(/(?<![\w-])-?\d+\.\d{3,}(?:[eE][+-]?\d+)?/g, (match) => {
        const value = Number(match);
        return Number.isFinite(value) ? value.toFixed(2) : match;
      });
    })
    .join("");
}
