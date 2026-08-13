import { Send, Cog, CheckCircle, Circle, Loader2, Upload, Table2, Sparkles } from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { FileChip } from "./FileChip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Label } from "./ui/label";
import { lazy, Suspense, useState, useRef, useEffect } from "react";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../lib/modelOptions";
import { useI18n } from "../lib/i18n";
import type { ChatMessage, DashboardPayload } from "../lib/appTypes";

const ConversationalMessage = lazy(() =>
  import("./ConversationalMessage").then((module) => ({ default: module.ConversationalMessage }))
);
const VerifiedAnswerMessage = lazy(() =>
  import("./VerifiedAnswerMessage").then((module) => ({ default: module.VerifiedAnswerMessage }))
);

interface FileInfo {
  id: string;
  name: string;
}

interface ConversationalChatAreaProps {
  messages: ChatMessage[];
  onSendMessage: (message: string, fileIds: string[], model?: string, promptStyle?: string) => void;
  onOpenDashboard: (payload: DashboardPayload) => void;
  isLoading: boolean;
  activeFiles: FileInfo[];
  onUpload: () => void;
}

export function ConversationalChatArea({ 
  messages, 
  onSendMessage,
  onOpenDashboard,
  isLoading,
  activeFiles,
  onUpload,
}: ConversationalChatAreaProps) {
  const { language, t } = useI18n();
  const [inputValue, setInputValue] = useState("");
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>(DEFAULT_MODEL);
  const [selectedPromptStyle, setSelectedPromptStyle] = useState<string>("zero");
  const [runningSeconds, setRunningSeconds] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-select all active files when they change
  useEffect(() => {
    setSelectedFileIds(activeFiles.map(f => f.id));
  }, [activeFiles]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading, runningSeconds]);

  useEffect(() => {
    if (!isLoading) {
      setRunningSeconds(0);
      return;
    }

    const intervalId = window.setInterval(() => {
      setRunningSeconds((seconds) => seconds + 1);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isLoading]);

  const handleSend = () => {
    if (inputValue.trim() && selectedFileIds.length > 0) {
      onSendMessage(inputValue, selectedFileIds, selectedModel, selectedPromptStyle);
      setInputValue("");
    }
  };

  const renderRunningSteps = (steps: string[]) => {
    const activeIndex = Math.min(
      steps.length - 1,
      Math.max(0, Math.floor(runningSeconds / 5))
    );

    return (
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-4 shadow-sm min-w-0">
        <div className="flex items-center gap-2 mb-3 min-w-0">
          <div
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-blue-600"
          >
            <Cog className="h-4 w-4 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
              {t("analysisProgress")}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {runningSeconds < 2 ? t("starting") : t("elapsed", { seconds: runningSeconds })}
            </div>
          </div>
          <Loader2
            className="h-4 w-4 flex-shrink-0 animate-spin text-blue-600"
          />
        </div>

        <div className="space-y-2">
          {steps.map((step, index) => {
            const isDone = index < activeIndex;
            const isActive = index === activeIndex;
            return (
              <div
                key={step}
                className={`flex items-start gap-2 rounded-md px-2 py-2 transition-colors ${
                  isActive ? "bg-blue-50 dark:bg-blue-950/30" : ""
                }`}
              >
                {isDone ? (
                  <CheckCircle className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
                ) : isActive ? (
                  <Loader2
                    className="mt-0.5 h-4 w-4 flex-shrink-0 animate-spin text-blue-600"
                  />
                ) : (
                  <Circle className="h-4 w-4 text-gray-300 dark:text-gray-600 mt-0.5 flex-shrink-0" />
                )}
                <span
                  className={`text-sm leading-snug ${
                    isDone || isActive
                      ? "text-gray-800 dark:text-gray-100"
                      : "text-gray-400 dark:text-gray-500"
                  }`}
                >
                  {step}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderRunningProcess = () => (
    <div className="space-y-3">
      <div className="rounded-lg border border-blue-100 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/20 px-4 py-3">
        <div className="text-sm font-medium text-blue-900 dark:text-blue-100">
          {t("analysisProgress")}
        </div>
        <div className="text-xs text-blue-700 dark:text-blue-300 mt-1">
          {t("progressHint")}
        </div>
      </div>
      {renderRunningSteps(language === "zh" ? [
        "读取问题并检查数据画像",
        "检索指标定义并选择分析技能",
        "生成结构化分析计划",
        "生成 Python 代码",
        "在沙箱中执行代码",
        "验证结果，必要时自动修复",
        "整理可信答案与证据",
      ] : [
        "Reading the question and dataset profile",
        "Retrieving metrics and selecting skills",
        "Building a structured analysis plan",
        "Generating Python code",
        "Executing code in the sandbox",
        "Validating and repairing if needed",
        "Preparing the verified answer and evidence",
      ])}
    </div>
  );

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleFile = (fileId: string) => {
    setSelectedFileIds(prev => 
      prev.includes(fileId) 
        ? prev.filter(id => id !== fileId)
        : [...prev, fileId]
    );
  };

  return (
    <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-[#f8fafc] dark:bg-gray-950">
      {/* Model & Prompt Selection Area - Fixed at top */}
      {activeFiles.length > 0 && (
        <div className="flex flex-shrink-0 flex-col gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-900 sm:flex-row sm:items-center sm:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
            <Label htmlFor="model-select" className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              {t("model")}:
            </Label>
            <Select value={selectedModel} onValueChange={setSelectedModel} disabled={isLoading}>
              <SelectTrigger id="model-select" className="h-9 min-w-0 flex-1 sm:w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_OPTIONS.map((model) => (
                  <SelectItem key={model.value} value={model.value}>
                    {model.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
            <Label htmlFor="prompt-select" className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              {t("prompt")}:
            </Label>
            <Select value={selectedPromptStyle} onValueChange={setSelectedPromptStyle} disabled={isLoading}>
              <SelectTrigger id="prompt-select" className="h-9 min-w-0 flex-1 sm:w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="zero">Zero-shot</SelectItem>
                <SelectItem value="zero_cot">Zero-shot CoT</SelectItem>
                <SelectItem value="sub_question">Sub-Question Decomposition</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Scrollable Messages Area */}
      <div 
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-8"
        style={{ scrollBehavior: 'smooth' }}
      >
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center py-8">
            <div className="w-full max-w-xl text-center">
              <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 shadow-lg shadow-blue-600/20">
                <Sparkles className="h-6 w-6 text-white" />
              </div>
              <h2 className="mb-3 text-2xl font-semibold tracking-[-0.02em] text-gray-950 dark:text-white sm:text-3xl">
                {t("emptyTitle")}
              </h2>
              <p className="mx-auto mb-6 max-w-lg text-sm leading-6 text-gray-600 dark:text-gray-300 sm:text-base">
                {activeFiles.length > 0
                  ? t("emptyReady")
                  : t("emptyUpload")
                }
              </p>
              {activeFiles.length === 0 ? (
                <div className="flex flex-col items-center gap-3">
                  <Button onClick={onUpload} size="lg" className="h-11 bg-blue-600 px-5 hover:bg-blue-700">
                    <Upload className="h-4 w-4" />
                    {t("uploadFirst")}
                  </Button>
                  <span className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                    <Table2 className="h-3.5 w-3.5" /> {t("csvLimit")}
                  </span>
                </div>
              ) : (
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {t("examples")}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="max-w-5xl mx-auto space-y-6">
            <Suspense fallback={<div className="py-8 text-center text-sm text-gray-500">Loading response…</div>}>
              {messages.map((message, index) => {
                if (message.type === "user") {
                  return <ConversationalMessage key={message.id} {...message} />;
                } else if (message.sandboxResponse) {
                  const sourceQuestion = [...messages.slice(0, index)].reverse().find((item) => item.type === "user")?.content || "";
                  return (
                    <VerifiedAnswerMessage
                      key={message.id}
                      response={message.sandboxResponse}
                      timestamp={message.timestamp}
                      onOpenDashboard={() => onOpenDashboard({ question: sourceQuestion, timestamp: message.timestamp, response: message.sandboxResponse! })}
                    />
                  );
                } else {
                  return <ConversationalMessage key={message.id} {...message} />;
                }
              })}
            </Suspense>
            {isLoading && renderRunningProcess()}
          </div>
        )}
        {/* Bottom padding for scroll area */}
        <div className="h-6"></div>
      </div>

      {/* Gradient overlay hint for scrolling */}
      {messages.length > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-gray-50 dark:from-gray-900 via-gray-50/50 dark:via-gray-900/50 to-transparent pointer-events-none z-0"></div>
      )}
      
      {/* Fixed Input Area at Bottom */}
      <div className="relative z-10 border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        {/* Divider with label */}
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 pb-1 pt-3">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400">
            {messages.length > 0 ? t("followUp") : t("askDataSays")}
          </div>
          <span className="hidden text-[11px] text-gray-400 sm:inline">{t("sendHint")}</span>
        </div>
        
        <div className="max-w-5xl mx-auto px-4 pb-3 sm:pb-4">
          {/* File Chips Row */}
          {activeFiles.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2 items-center">
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {t("usingFiles")}:
              </span>
              {activeFiles.map((file) => (
                <FileChip
                  key={file.id}
                  fileName={file.name}
                  selected={selectedFileIds.includes(file.id)}
                  removable={selectedFileIds.includes(file.id)}
                  onClick={() => toggleFile(file.id)}
                  onRemove={() => toggleFile(file.id)}
                />
              ))}
            </div>
          )}
          
          <div className="flex gap-3">
            <Textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder={activeFiles.length > 0 ? t("askPlaceholder") : t("uploadPlaceholder")}
              aria-label="Ask a question about your data"
              className="min-h-[52px] max-h-[200px] flex-1 resize-none rounded-xl border-gray-300 bg-gray-50/70 px-4 py-3 shadow-none focus-visible:bg-white dark:border-gray-700 dark:bg-gray-950/60 dark:focus-visible:bg-gray-950"
              disabled={isLoading || activeFiles.length === 0}
              rows={1}
            />
            <Button 
              onClick={handleSend}
              className="h-[52px] w-[52px] rounded-xl bg-blue-600 px-0 hover:bg-blue-700"
              disabled={isLoading || !inputValue.trim() || selectedFileIds.length === 0}
              aria-label="Send question"
              title="Send question"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}
