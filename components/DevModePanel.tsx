import { useState } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Badge } from "./ui/badge";
import { X, Download, Play, Loader2 } from "lucide-react";
import { devEval, DevEvalResponse, DevEvalResult } from "../lib/client";
import { MODEL_LABELS, MODEL_OPTIONS } from "../lib/modelOptions";
import { toast } from "sonner";
import { useI18n } from "../lib/i18n";

interface FileInfo {
  id: string;
  name: string;
}

interface DevModePanelProps {
  activeFiles: FileInfo[];
  onExit: () => void;
}

export function DevModePanel({ activeFiles, onExit }: DevModePanelProps) {
  const { language, t } = useI18n();
  const [question, setQuestion] = useState("");
  const [selectedFileId, setSelectedFileId] = useState<string>(activeFiles[0]?.id || "");
  const [isLoading, setIsLoading] = useState(false);
  const [evalResult, setEvalResult] = useState<DevEvalResponse | null>(null);

  const handleRunEvaluation = async () => {
    if (!question.trim() || !selectedFileId) {
      toast.error(language === "zh" ? "请输入问题并选择数据文件" : "Please enter a question and select a file");
      return;
    }

    setIsLoading(true);
    try {
      const result = await devEval({
        question: question,
        csv_id: selectedFileId,
        models: MODEL_OPTIONS.map((model) => model.value),
        prompts: ["zero", "zero_cot", "sub_question"],
      });
      setEvalResult(result);
      toast.success(language === "zh" ? "对比执行完成" : "Comparison completed");
    } catch (error: any) {
      console.error("Evaluation error:", error);
      toast.error(error.message || (language === "zh" ? "对比执行失败" : "Comparison failed"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadReport = () => {
    if (!evalResult) return;

    const report = {
      ...evalResult,
      generated_at: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dev-eval-report-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
      toast.success(language === "zh" ? "报告已下载" : "Report downloaded");
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return "bg-green-500";
    if (score >= 60) return "bg-yellow-500";
    if (score >= 40) return "bg-orange-500";
    return "bg-red-500";
  };

  const getModelDisplayName = (model: string) => {
    return MODEL_LABELS[model] || model;
  };

  const getPromptDisplayName = (style: string) => {
    const names: Record<string, string> = {
      zero: "Zero-shot",
      zero_cot: "Zero-shot CoT",
      sub_question: "Sub-Question Decomposition",
    };
    return names[style] || style;
  };

  return (
    <div className="flex-1 flex flex-col bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t("compareTitle")}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t("compareDescription")}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onExit}>
            <X className="h-4 w-4 mr-2" />
            {t("backToAnalysis")}
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Input Section */}
          <Card>
            <CardHeader>
              <CardTitle>{language === "zh" ? "对比配置" : "Comparison configuration"}</CardTitle>
              <CardDescription>{language === "zh" ? "同一问题将运行全部 3×3 组合。当前分数反映执行成功情况，不代表正式 Benchmark 质量。" : "The same question runs across all 3×3 combinations. Current scores reflect execution success, not benchmark quality."}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="question">{language === "zh" ? "分析问题" : "Question"}</Label>
                <Textarea
                  id="question"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={language === "zh" ? "输入要对比的问题…" : "Enter the question to compare…"}
                  rows={3}
                  disabled={isLoading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="file-select">{language === "zh" ? "数据文件（CSV）" : "Data file (CSV)"}</Label>
                <Select value={selectedFileId} onValueChange={setSelectedFileId} disabled={isLoading}>
                  <SelectTrigger id="file-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {activeFiles.map((file) => (
                      <SelectItem key={file.id} value={file.id}>
                        {file.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                onClick={handleRunEvaluation}
                disabled={isLoading || !question.trim() || !selectedFileId}
                className="w-full"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    {language === "zh" ? "正在运行 9 个组合…" : "Running 9 combinations…"}
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    {language === "zh" ? "开始 3×3 对比" : "Start 3×3 comparison"}
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Results Section */}
          {evalResult && (
            <div className="space-y-6">
              {/* Summary */}
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>{language === "zh" ? "执行汇总" : "Execution summary"}</CardTitle>
                      <CardDescription>{language === "zh" ? "模型与提示策略组合的运行统计" : "Run statistics for model and prompt combinations"}</CardDescription>
                    </div>
                    <Button onClick={handleDownloadReport} variant="outline" size="sm">
                      <Download className="h-4 w-4 mr-2" />
                      {language === "zh" ? "下载 JSON 报告" : "Download JSON report"}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-gray-900 dark:text-white">
                        {evalResult.summary.total_combinations}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">{language === "zh" ? "组合总数" : "Total combinations"}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-600">
                        {evalResult.summary.successful}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">{language === "zh" ? "成功" : "Successful"}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-600">
                        {evalResult.summary.failed}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">{language === "zh" ? "失败" : "Failed"}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600">
                        {evalResult.summary.average_score.toFixed(1)}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">{language === "zh" ? "平均执行分" : "Average score"}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Tabs for different views */}
              <Tabs defaultValue="table" className="w-full">
                <TabsList>
                  <TabsTrigger value="table">{language === "zh" ? "结果表" : "Results"}</TabsTrigger>
                  <TabsTrigger value="leaderboard">{language === "zh" ? "排行榜" : "Leaderboard"}</TabsTrigger>
                  <TabsTrigger value="heatmap">{language === "zh" ? "热力图" : "Heatmap"}</TabsTrigger>
                  <TabsTrigger value="best">{language === "zh" ? "最佳结果" : "Best result"}</TabsTrigger>
                </TabsList>

                {/* Results Table */}
                <TabsContent value="table" className="space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>{language === "zh" ? "全部组合结果" : "All combination results"}</CardTitle>
                      <CardDescription>{language === "zh" ? "3 个模型 × 3 种提示策略的执行详情" : "Execution details for all model × prompt combinations"}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>{t("model")}</TableHead>
                              <TableHead>{t("prompt")}</TableHead>
                              <TableHead>{language === "zh" ? "执行分" : "Score"}</TableHead>
                              <TableHead>{language === "zh" ? "状态" : "Status"}</TableHead>
                              <TableHead>{language === "zh" ? "耗时（秒）" : "Time (s)"}</TableHead>
                              <TableHead>{language === "zh" ? "输出预览" : "Output preview"}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {[...evalResult.results]
                              // Sort by score (descending), then by execution time (ascending) if scores are equal
                              .sort((a, b) => {
                                if (b.score !== a.score) {
                                  return b.score - a.score;
                                }
                                return a.exec_time - b.exec_time;
                              })
                              .map((result: DevEvalResult, idx: number) => (
                              <TableRow key={idx}>
                                <TableCell className="font-medium">
                                  {getModelDisplayName(result.model)}
                                </TableCell>
                                <TableCell>{getPromptDisplayName(result.prompt_style)}</TableCell>
                                <TableCell>
                                  <div className="flex items-center gap-2">
                                    <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                      <div
                                        className={`h-full ${getScoreColor(result.score)}`}
                                        style={{ width: `${result.score}%` }}
                                      />
                                    </div>
                                    <span className="text-sm font-medium">{result.score.toFixed(1)}</span>
                                  </div>
                                </TableCell>
                                <TableCell>
                                  <Badge
                                    variant={result.status === "success" ? "default" : "destructive"}
                                  >
                                    {result.status}
                                  </Badge>
                                </TableCell>
                                <TableCell>{result.exec_time.toFixed(2)}</TableCell>
                                <TableCell className="max-w-xs truncate">
                                  {result.stdout || result.error || "No output"}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Leaderboard */}
                <TabsContent value="leaderboard" className="space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>{language === "zh" ? "执行排行榜" : "Execution leaderboard"}</CardTitle>
                      <CardDescription>{language === "zh" ? "按当前执行分排序，不代表答案质量基准" : "Sorted by execution score, not answer-quality benchmark"}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {evalResult.leaderboard.map((result: DevEvalResult, idx: number) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between p-4 border border-gray-200 dark:border-gray-700 rounded-lg"
                          >
                            <div className="flex items-center gap-4">
                              <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center font-bold text-blue-600 dark:text-blue-300">
                                {idx + 1}
                              </div>
                              <div>
                                <div className="font-medium text-gray-900 dark:text-white">
                                  {getModelDisplayName(result.model)} + {getPromptDisplayName(result.prompt_style)}
                                </div>
                                <div className="text-sm text-gray-500 dark:text-gray-400">
                                  {language === "zh" ? "执行耗时" : "Execution time"}: {result.exec_time.toFixed(2)}s
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-4">
                              <div className="text-right">
                                <div className="text-lg font-bold text-gray-900 dark:text-white">
                                  {result.score.toFixed(1)}
                                </div>
                                <div className="text-xs text-gray-500 dark:text-gray-400">Score</div>
                              </div>
                              <Badge variant={result.status === "success" ? "default" : "destructive"}>
                                {result.status}
                              </Badge>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Heatmap */}
                <TabsContent value="heatmap" className="space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>{language === "zh" ? "执行热力图" : "Execution heatmap"}</CardTitle>
                      <CardDescription>{language === "zh" ? "模型 × 提示策略执行分矩阵" : "Model × prompt execution-score matrix"}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <table className="w-full border-collapse">
                          <thead>
                            <tr>
                              <th className="border border-gray-300 dark:border-gray-700 p-2 text-left">
                                Model \ Prompt
                              </th>
                              {["zero", "zero_cot", "sub_question"].map((style) => (
                                <th
                                  key={style}
                                  className="border border-gray-300 dark:border-gray-700 p-2 text-center"
                                >
                                  {getPromptDisplayName(style)}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {MODEL_OPTIONS.map((modelOption) => modelOption.value).map(
                              (model) => (
                                <tr key={model}>
                                  <td className="border border-gray-300 dark:border-gray-700 p-2 font-medium">
                                    {getModelDisplayName(model)}
                                  </td>
                                  {["zero", "zero_cot", "sub_question"].map((style) => {
                                    const score = evalResult.heatmap[model]?.[style] || 0;
                                    return (
                                      <td
                                        key={style}
                                        className="border border-gray-300 dark:border-gray-700 p-4 text-center"
                                      >
                                        <div
                                          className={`inline-block px-3 py-1 rounded text-white font-medium ${getScoreColor(
                                            score
                                          )}`}
                                        >
                                          {score.toFixed(1)}
                                        </div>
                                      </td>
                                    );
                                  })}
                                </tr>
                              )
                            )}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Best Result */}
                <TabsContent value="best" className="space-y-4">
                  {evalResult.best && (
                    <Card>
                      <CardHeader>
                        <CardTitle>{language === "zh" ? "当前最佳执行结果" : "Best execution result"}</CardTitle>
                        <CardDescription>
                          {getModelDisplayName(evalResult.best.model)} +{" "}
                          {getPromptDisplayName(evalResult.best.prompt_style)}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">{language === "zh" ? "执行分" : "Score"}</div>
                            <div className="text-2xl font-bold text-gray-900 dark:text-white">
                              {evalResult.best.score.toFixed(1)}
                            </div>
                          </div>
                          <div>
                            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">{language === "zh" ? "执行耗时" : "Execution time"}</div>
                            <div className="text-2xl font-bold text-gray-900 dark:text-white">
                              {evalResult.best.exec_time.toFixed(2)}s
                            </div>
                          </div>
                          <div>
                            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">{language === "zh" ? "状态" : "Status"}</div>
                            <Badge
                              variant={evalResult.best.status === "success" ? "default" : "destructive"}
                              className="text-lg px-3 py-1"
                            >
                              {evalResult.best.status}
                            </Badge>
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">{language === "zh" ? "生成代码" : "Generated code"}</div>
                          <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg overflow-x-auto text-sm">
                            {evalResult.best.code || "No code"}
                          </pre>
                        </div>
                        <div>
                          <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">{language === "zh" ? "执行输出" : "Execution output"}</div>
                          <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg overflow-x-auto text-sm">
                            {evalResult.best.stdout || evalResult.best.error || "No output"}
                          </pre>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
