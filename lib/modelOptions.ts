export const MODEL_OPTIONS = [
  { value: "qwen/qwen3.6-flash", label: "Qwen3.6 Flash" },
  { value: "openai/gpt-5.4-mini", label: "GPT-5.4 Mini" },
  { value: "moonshotai/kimi-k2.5", label: "Kimi K2.5" },
] as const;

export const DEFAULT_MODEL = MODEL_OPTIONS[0].value;

export const MODEL_LABELS = Object.fromEntries(
  MODEL_OPTIONS.map((model) => [model.value, model.label])
) as Record<string, string>;
