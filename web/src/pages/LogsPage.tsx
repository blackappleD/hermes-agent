import {
  useEffect,
  useLayoutEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  FileText,
  RefreshCw,
} from "lucide-react";
import {
  api,
  type OSRuntimeLogsResponse,
  type RuntimeModuleSnapshot,
  type RuntimeParameterReading,
} from "@/lib/api";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { FilterGroup, Segmented } from "@nous-research/ui/ui/components/segmented";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ProfileSelector } from "@/components/ProfileSelector";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";

const FILES = ["agent", "errors", "gateway"] as const;
const LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"] as const;
const COMPONENTS = ["all", "gateway", "agent", "tools", "cli", "cron"] as const;
const LINE_COUNTS = [50, 100, 200, 500] as const;

const DEFAULT_OS_RUNTIME_TEXT = {
  toggle: "OS_RUNTIME",
  title: "OS_RUNTIME",
  rawLines: "Raw Lines",
  showRaw: "Show Raw",
  hideRaw: "Hide Raw",
  noData: "No OS_RUNTIME log lines found for the current profile.",
  moduleNoData: "No data",
  updated: "Updated",
  source: "Source",
  parseErrors: "Parse errors",
  partial: "Partial",
  empty: "Empty",
  renderedPrompt: "Rendered Prompt",
  structuredFields: "Structured Fields",
  change: {
    up: "Up",
    down: "Down",
    unchanged: "Flat",
    changed: "Changed",
    unknown: "New",
  },
  modules: {
    life_state: "Life State",
    tension_field: "Tension Field",
    action_potential: "Action Potential",
    self_prompt: "SelfPrompt",
    open_intent: "OpenIntent",
    arbitration: "Arbitration",
    runtime_driver: "Runtime Driver",
  },
  fields: {
    energy: "Energy",
    fatigue: "Fatigue",
    health: "Health",
    wakefulness: "Wakefulness",
    curiosity: "Curiosity",
    boredom: "Boredom",
    creative_pressure: "Creative Pressure",
    social_hunger: "Social Hunger",
    silence_pressure: "Silence Pressure",
    restraint: "Restraint",
    life_cycle: "Life Cycle",
    recovery_cycle: "Recovery Cycle",
    generated_intent_count: "Generated Intent Count",
    active_tensions: "Active Tensions",
    top_tension_id: "Top Tension ID",
    top_tension_type: "Top Tension Type",
    intensity: "Intensity",
    activation: "Activation",
    trend: "Trend",
    trend_slope: "Trend Slope",
    confidence: "Confidence",
    baseline: "Baseline",
    propagation_edges: "Propagation Edges",
    value_potential: "Value Potential",
    mutual_benefit_potential: "Mutual Benefit Potential",
    learning_potential: "Learning Potential",
    risk_cost: "Risk Cost",
    overall_score: "Overall Score",
    recommended_depth: "Recommended Depth",
    rationale: "Rationale",
    prompt_id: "Prompt ID",
    state_summary: "State Summary",
    tension_summary: "Tension Summary",
    potential_summary: "Potential Summary",
    environment_scope: "Environment Scope",
    intent_id: "Intent ID",
    description: "Description",
    action_family: "Action Family",
    risk_level: "Risk Level",
    success_condition: "Success Condition",
    decision: "Decision",
    verdict: "Verdict",
    risk: "Risk",
    requires_approval: "Requires Approval",
    status: "Status",
    should_continue: "Should Continue",
    reason: "Reason",
    turns_used: "Turns Used",
    max_turns: "Max Turns",
    paused_reason: "Paused Reason",
  },
  values: {
    true: "true",
    false: "false",
    unknown: "unknown",
    active: "Active",
    stable: "Stable",
    none: "None",
    continue_turn: "Continue Turn",
    report_only: "Report Only",
    draft_only: "Draft Only",
    execute: "Execute",
    skip: "Skip",
    allow: "Allow",
    block: "Block",
    defer: "Defer",
    approve: "Approve",
    approved: "Approved",
    reject: "Reject",
    rejected: "Rejected",
    low: "Low",
    medium: "Medium",
    high: "High",
    critical: "Critical",
    paused: "Paused",
    running: "Running",
    idle: "Idle",
    ok: "OK",
  },
};

type RuntimeText = Omit<typeof DEFAULT_OS_RUNTIME_TEXT, "fields" | "values"> & {
  fields: Record<string, string>;
  values: Record<string, string>;
};

function classifyLine(line: string): "error" | "warning" | "info" | "debug" {
  const upper = line.toUpperCase();
  if (
    upper.includes("ERROR") ||
    upper.includes("CRITICAL") ||
    upper.includes("FATAL")
  )
    return "error";
  if (upper.includes("WARNING") || upper.includes("WARN")) return "warning";
  if (upper.includes("DEBUG")) return "debug";
  return "info";
}

const LINE_COLORS: Record<string, string> = {
  error: "text-destructive",
  warning: "text-warning",
  info: "text-foreground",
  debug: "text-muted-foreground/60",
};

const toOptions = <T extends string>(values: readonly T[]) =>
  values.map((v) => ({ value: v, label: v }));

function formatValue(value: RuntimeParameterReading["value"]): string {
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? String(value)
      : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "unknown";
  if (typeof value === "string") return value || "unknown";
  return JSON.stringify(value);
}

function normalizeRuntimeValue(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function localizeRuntimeInlineText(value: string, text: RuntimeText): string {
  return value
    .replace(/\b([A-Za-z][A-Za-z0-9_]*)\s*=/g, (match, key: string) => {
      const localizedKey = text.fields[normalizeRuntimeValue(key)];
      return localizedKey ? `${localizedKey}=` : match;
    })
    .replace(/=\s*([A-Za-z][A-Za-z0-9_-]*)\b/g, (match, rawValue: string) => {
      const localizedValue = text.values[normalizeRuntimeValue(rawValue)];
      return localizedValue ? `=${localizedValue}` : match;
    });
}

function formatRuntimeValue(
  value: RuntimeParameterReading["value"],
  text: RuntimeText,
): string {
  if (typeof value === "boolean") {
    return text.values[String(value)] ?? formatValue(value);
  }
  if (value === null || value === undefined) {
    return text.values.unknown ?? formatValue(value);
  }
  if (typeof value === "string") {
    if (!value) return text.values.unknown ?? formatValue(value);
    return (
      text.values[normalizeRuntimeValue(value)] ??
      localizeRuntimeInlineText(value, text)
    );
  }
  return formatValue(value);
}

function changeTone(change: RuntimeParameterReading["change"]) {
  if (change === "up") return "success";
  if (change === "down") return "warning";
  if (change === "changed") return "secondary";
  return "secondary";
}

function changeLabel(param: RuntimeParameterReading, text: RuntimeText): string {
  const base = text.change[param.change] ?? text.change.unknown;
  if (typeof param.delta === "number" && param.delta !== 0) {
    const sign = param.delta > 0 ? "+" : "";
    return `${base} ${sign}${formatValue(param.delta)}`;
  }
  return base;
}

function parameterLabel(
  param: RuntimeParameterReading,
  text: RuntimeText,
): string {
  return text.fields[param.key] ?? param.label;
}

function moduleTitle(module: RuntimeModuleSnapshot, text: RuntimeText): string {
  const key = module.module_id as keyof RuntimeText["modules"];
  return text.modules[key] ?? module.title;
}

function moduleSummary(module: RuntimeModuleSnapshot, text: RuntimeText): string {
  if (
    module.module_id === "life_state" ||
    module.module_id === "tension_field" ||
    module.module_id === "action_potential"
  ) {
    return module.parameters
      .slice(0, 3)
      .map(
        (param) =>
          `${parameterLabel(param, text)} ${formatRuntimeValue(param.value, text)}`,
      )
      .join(", ");
  }
  return module.summary;
}

function emptyReason(reason: string, text: RuntimeText): string {
  return reason === DEFAULT_OS_RUNTIME_TEXT.noData ? text.noData : reason;
}

function metadataString(module: RuntimeModuleSnapshot, key: string): string {
  const value = module.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function RuntimeModuleCard({
  module,
  text,
}: {
  module: RuntimeModuleSnapshot;
  text: RuntimeText;
}) {
  const isEmpty = module.status === "empty" || module.parameters.length === 0;
  const renderedPrompt =
    module.module_id === "self_prompt"
      ? metadataString(module, "rendered_prompt")
      : "";
  const summary = moduleSummary(module, text);
  return (
    <Card>
      <CardHeader className="px-4 py-3">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <Activity className="h-4 w-4 shrink-0" />
            <span className="truncate">{moduleTitle(module, text)}</span>
          </CardTitle>
          {module.status !== "ok" && (
            <Badge tone={module.status === "partial" ? "warning" : "secondary"} className="text-[10px]">
              {module.status === "partial" ? text.partial : text.empty}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span>
            {text.updated}: {module.updated_at || text.moduleNoData}
          </span>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-0">
        {summary && (
          <p className="mb-3 break-words text-xs text-muted-foreground">
            {summary}
          </p>
        )}
        {renderedPrompt && (
          <div className="mb-3 border border-border/60 bg-secondary/10 p-3">
            <p className="mb-2 text-[11px] font-medium uppercase text-muted-foreground">
              {text.renderedPrompt}
            </p>
            <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono-ui text-xs leading-5 text-foreground">
              {renderedPrompt}
            </pre>
          </div>
        )}
        {isEmpty ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            {text.moduleNoData}
          </p>
        ) : (
          <div className="grid gap-2">
            {renderedPrompt && (
              <p className="text-[11px] font-medium uppercase text-muted-foreground">
                {text.structuredFields}
              </p>
            )}
            {module.parameters.map((param) => (
              <div
                key={`${module.module_id}-${param.key}`}
                className="grid min-h-9 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border/40 pb-2 last:border-b-0 last:pb-0"
              >
                <div className="min-w-0">
                  <p className="truncate text-xs text-muted-foreground">
                    {parameterLabel(param, text)}
                  </p>
                  <p className="break-words font-mono-ui text-sm text-foreground">
                    {formatRuntimeValue(param.value, text)}
                  </p>
                </div>
                <Badge tone={changeTone(param.change)} className="text-[10px]">
                  {changeLabel(param, text)}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function LogsPage() {
  const [file, setFile] = useState<(typeof FILES)[number]>("agent");
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("ALL");
  const [component, setComponent] =
    useState<(typeof COMPONENTS)[number]>("all");
  const [lineCount, setLineCount] = useState<(typeof LINE_COUNTS)[number]>(100);
  const [profile, setProfile] = useState("current");
  const [autoRefresh, setAutoRefresh] = useState(true);
  // Switch acceptance: OS_RUNTIME sits before auto refresh, preserves normal filters, and shares auto refresh.
  const [osRuntimeMode, setOsRuntimeMode] = useState(false);
  const [rawExpanded, setRawExpanded] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [runtimeData, setRuntimeData] = useState<OSRuntimeLogsResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rawScrollRef = useRef<HTMLDivElement>(null);
  const stickRawToBottomRef = useRef(true);
  const { t } = useI18n();
  const runtimeText: RuntimeText = {
    ...DEFAULT_OS_RUNTIME_TEXT,
    ...(t.logs.osRuntime ?? {}),
    change: {
      ...DEFAULT_OS_RUNTIME_TEXT.change,
      ...(t.logs.osRuntime?.change ?? {}),
    },
    modules: {
      ...DEFAULT_OS_RUNTIME_TEXT.modules,
      ...(t.logs.osRuntime?.modules ?? {}),
    },
    fields: {
      ...DEFAULT_OS_RUNTIME_TEXT.fields,
      ...(t.logs.osRuntime?.fields ?? {}),
    },
    values: {
      ...DEFAULT_OS_RUNTIME_TEXT.values,
      ...(t.logs.osRuntime?.values ?? {}),
    },
  };
  const { setAfterTitle, setEnd } = usePageHeader();

  const scrollNormalLogToBottom = useCallback(() => {
    setTimeout(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, 50);
  }, []);

  const scrollRawLogToBottom = useCallback(() => {
    setTimeout(() => {
      if (rawScrollRef.current && stickRawToBottomRef.current) {
        rawScrollRef.current.scrollTop = rawScrollRef.current.scrollHeight;
      }
    }, 50);
  }, []);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    setError(null);
    if (osRuntimeMode) {
      if (rawScrollRef.current) {
        const el = rawScrollRef.current;
        stickRawToBottomRef.current =
          el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      }
      api
        .getOsRuntimeLogs({ lines: lineCount, includeRaw: true, profile })
        .then((resp) => {
          setRuntimeData(resp);
          scrollRawLogToBottom();
        })
        .catch((err) => setError(String(err)))
        .finally(() => setLoading(false));
      return;
    }

    api
      .getLogs({ file, lines: lineCount, level, component, profile })
      .then((resp) => {
        setLines(resp.lines);
        scrollNormalLogToBottom();
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [
    component,
    file,
    level,
    lineCount,
    osRuntimeMode,
    profile,
    scrollNormalLogToBottom,
    scrollRawLogToBottom,
  ]);

  useLayoutEffect(() => {
    setAfterTitle(
      <span className="flex items-center gap-2">
        {loading && <Spinner className="shrink-0 text-base text-primary" />}
        <Badge tone="secondary" className="text-[10px]">
          {osRuntimeMode
            ? `${runtimeText.title} · ${lineCount}`
            : `${file} · ${level} · ${component}`}
        </Badge>
      </span>,
    );
    setEnd(
      <div className="flex w-full min-w-0 flex-nowrap items-center justify-end gap-1.5 sm:gap-2">
        <ProfileSelector
          value={profile}
          onChange={(nextProfile) => {
            setProfile(nextProfile);
            setLines([]);
            setRuntimeData(null);
          }}
        />
        <div className="flex shrink-0 items-center gap-1.5">
          <Switch
            checked={osRuntimeMode}
            onCheckedChange={setOsRuntimeMode}
            id="logs-os-runtime"
          />
          <Label htmlFor="logs-os-runtime" className="cursor-pointer text-xs">
            {runtimeText.toggle}
          </Label>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Switch
            checked={autoRefresh}
            onCheckedChange={setAutoRefresh}
            id="logs-auto-refresh"
          />
          <Label htmlFor="logs-auto-refresh" className="cursor-pointer text-xs">
            {t.logs.autoRefresh}
          </Label>
          {autoRefresh && (
            <Badge tone="success" className="text-[10px]">
              <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              {t.common.live}
            </Badge>
          )}
        </div>
        <Button
          type="button"
          size="sm"
          outlined
          onClick={fetchLogs}
          disabled={loading}
          prefix={loading ? <Spinner /> : <RefreshCw />}
        >
          {t.common.refresh}
        </Button>
      </div>,
    );
    return () => {
      setAfterTitle(null);
      setEnd(null);
    };
  }, [
    autoRefresh,
    component,
    fetchLogs,
    file,
    level,
    lineCount,
    loading,
    osRuntimeMode,
    profile,
    runtimeText.title,
    runtimeText.toggle,
    setAfterTitle,
    setEnd,
    t.common.live,
    t.common.refresh,
    t.logs.autoRefresh,
  ]);

  useEffect(() => {
    const timeout = window.setTimeout(fetchLogs, 0);
    return () => window.clearTimeout(timeout);
  }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  return (
    <div className="flex flex-col gap-4">
      <PluginSlot name="logs:top" />
      <div
        role="toolbar"
        aria-label={t.logs.title}
        className="flex flex-wrap items-center gap-x-6 gap-y-2"
      >
        {!osRuntimeMode && (
          <>
            <FilterGroup label={t.logs.file}>
              <Segmented
                value={file}
                onChange={setFile}
                options={toOptions(FILES)}
              />
            </FilterGroup>

            <FilterGroup label={t.logs.level}>
              <Segmented
                value={level}
                onChange={setLevel}
                options={toOptions(LEVELS)}
              />
            </FilterGroup>

            <FilterGroup label={t.logs.component}>
              <Segmented
                value={component}
                onChange={setComponent}
                options={toOptions(COMPONENTS)}
              />
            </FilterGroup>
          </>
        )}

        <FilterGroup label={t.logs.lines}>
          <Segmented
            value={String(lineCount)}
            onChange={(v) =>
              setLineCount(Number(v) as (typeof LINE_COUNTS)[number])
            }
            options={LINE_COUNTS.map((n) => ({
              value: String(n),
              label: String(n),
            }))}
          />
        </FilterGroup>

        {osRuntimeMode && runtimeData?.source_files.length ? (
          <Badge tone="secondary" className="text-[10px]">
            {runtimeText.source}: {runtimeData.source_files.join(", ")}
          </Badge>
        ) : null}
      </div>

      {osRuntimeMode ? (
        <div className="flex flex-col gap-4">
          {error && (
            <div className="border border-destructive/20 bg-destructive/10 p-3">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          {runtimeData?.empty_reason && !loading && (
            <div className="border border-border bg-secondary/10 p-4 text-sm text-muted-foreground">
              {emptyReason(runtimeData.empty_reason, runtimeText)}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {(runtimeData?.modules ?? []).map((module) => (
              <RuntimeModuleCard
                key={module.module_id}
                module={module}
                text={runtimeText}
              />
            ))}
          </div>

          {runtimeData && (
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              {runtimeData.updated_at && (
                <span>
                  {runtimeText.updated}: {runtimeData.updated_at}
                </span>
              )}
              <span>
                {runtimeText.rawLines}: {runtimeData.raw_line_count}
              </span>
              {runtimeData.parse_error_count > 0 && (
                <Badge tone="warning" className="text-[10px]">
                  {runtimeText.parseErrors}: {runtimeData.parse_error_count}
                </Badge>
              )}
            </div>
          )}

          <Card>
            <CardHeader className="px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <FileText className="h-4 w-4" />
                  {runtimeText.rawLines}
                </CardTitle>
                <Button
                  type="button"
                  size="sm"
                  outlined
                  onClick={() => setRawExpanded((current) => !current)}
                  prefix={rawExpanded ? <ChevronUp /> : <ChevronDown />}
                >
                  {rawExpanded ? runtimeText.hideRaw : runtimeText.showRaw}
                </Button>
              </div>
            </CardHeader>
            {rawExpanded && (
              <CardContent className="p-0">
                <div
                  ref={rawScrollRef}
                  className="max-h-[min(38vh,360px)] min-h-[180px] overflow-auto p-4 font-mono-ui text-xs leading-5"
                >
                  {runtimeData?.raw_lines.length ? (
                    runtimeData.raw_lines.map((line, i) => {
                      const cls = classifyLine(line);
                      return (
                        <div
                          key={i}
                          className={`${LINE_COLORS[cls]} break-words px-1 -mx-1 hover:bg-secondary/20`}
                        >
                          {line}
                        </div>
                      );
                    })
                  ) : (
                    <p className="py-8 text-center text-muted-foreground">
                      {t.logs.noLogLines}
                    </p>
                  )}
                </div>
              </CardContent>
            )}
          </Card>
        </div>
      ) : (
        <Card>
          <CardHeader className="px-4 py-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4" />
              {file}.log
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {error && (
              <div className="border-b border-destructive/20 bg-destructive/10 p-3">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            <div
              ref={scrollRef}
              className="max-h-[calc(100vh-220px)] min-h-[400px] overflow-auto p-4 font-mono-ui text-xs leading-5"
            >
              {lines.length === 0 && !loading && (
                <p className="py-8 text-center text-muted-foreground">
                  {t.logs.noLogLines}
                </p>
              )}
              {lines.map((line, i) => {
                const cls = classifyLine(line);
                return (
                  <div
                    key={i}
                    className={`${LINE_COLORS[cls]} px-1 -mx-1 hover:bg-secondary/20`}
                  >
                    {line}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
      <PluginSlot name="logs:bottom" />
    </div>
  );
}
