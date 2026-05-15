import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Database,
  FileText,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  api,
  type GatewayConsumeStatus,
  type GatewayMessageEventDetailResponse,
  type GatewayMessageEventQuery,
  type GatewayMessageEventSummary,
  type GatewayProjectionStatus,
  type GatewaySourceStatus,
} from "@/lib/api";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { FilterGroup, Segmented } from "@nous-research/ui/ui/components/segmented";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ProfileSelector } from "@/components/ProfileSelector";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";

const DEFAULT_TEXT = {
  title: "MessageEvents",
  subtitle: "Gateway inbound events projected to Hermes MessageEvent",
  autoRefresh: "Auto refresh",
  sourceCategory: "Source category",
  consumeStatus: "Consume status",
  projectionStatus: "Projection",
  subject: "Subject",
  eventType: "Event type",
  query: "Search",
  limit: "Rows",
  all: "All",
  clearFilters: "Clear filters",
  loadMore: "Load more",
  noRecords: "No event projection records found for this profile.",
  noMatch: "No records match the current filters.",
  selectRecord: "Select an event to inspect the raw payload and MessageEvent.",
  detail: "Projection detail",
  rawPayload: "Raw inbound payload",
  showPayload: "Show payload",
  hidePayload: "Hide payload",
  messageEvent: "Hermes MessageEvent",
  transitions: "Transitions",
  sourceStatus: "Gateway",
  linzWorld: "Linz World/NATS",
  updated: "Updated",
  latest: "Latest",
  source: "Source",
  payloadUnavailable: "Raw payload unavailable",
  failedToLoad: "Failed to load event projections",
};

const SOURCE_CATEGORIES = ["all", "linz_world_nats", "telegram", "discord", "slack", "webhook", "api_server"] as const;
const CONSUME_STATUSES: Array<"all" | GatewayConsumeStatus> = [
  "all",
  "received",
  "processing",
  "handled",
  "failed",
  "duplicate",
  "ignored",
  "unauthorized",
];
const PROJECTION_STATUSES: Array<"all" | GatewayProjectionStatus> = [
  "all",
  "pending",
  "projected",
  "failed",
];
const LIMITS = [50, 100, 200, 500] as const;
type BadgeTone = "success" | "destructive" | "warning" | "secondary" | "outline";

const WORLD_EVENTS_DEMO_RECORDS: GatewayMessageEventSummary[] = [
  {
    record_id: "linz_world_nats:demo",
    event_id: "demo",
    source_category: "linz_world_nats",
    platform: "linz_world",
    subject: "wsp.chat.message.sent",
    event_type: "message.sent",
    consumed_at: "2026-05-15T00:00:00+00:00",
    updated_at: "2026-05-15T00:00:02+00:00",
    payload_summary: "text=hello",
    source_summary: "linz_world / chat=world / user=Linz World",
    consume_status: "handled",
    projection_status: "projected",
    message_event_id: "demo",
    message_event_summary: "[Linz World chat] text=hello",
    session_id: "demo-session",
  },
];

const options = (values: readonly string[], text = DEFAULT_TEXT) =>
  values.map((value) => ({
    value,
    label: value === "all" ? text.all : value,
  }));

function statusTone(status: string): BadgeTone {
  if (status === "handled" || status === "projected" || status === "running" || status === "connected") return "success";
  if (status === "failed" || status === "unauthorized") return "destructive";
  if (status === "processing" || status === "pending" || status === "duplicate") return "warning";
  return "secondary";
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function compactJson(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function Field({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="min-w-0 border-b border-border/40 pb-2 last:border-b-0 last:pb-0">
      <p className="text-[10px] tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="break-words font-mono-ui text-xs text-foreground">{value || "-"}</p>
    </div>
  );
}

function EventRow({
  record,
  selected,
  onSelect,
}: {
  record: GatewayMessageEventSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full border border-border/70 bg-card/50 p-3 text-left transition-colors",
        "hover:border-primary/40 hover:bg-secondary/20",
        selected && "border-primary/70 bg-primary/10",
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Badge tone={statusTone(record.consume_status)} className="text-[10px]">
          {record.consume_status}
        </Badge>
        <Badge tone={statusTone(record.projection_status)} className="text-[10px]">
          {record.projection_status}
        </Badge>
        <span className="min-w-0 break-all font-mono-ui text-xs text-foreground">
          {record.event_id || record.message_event_id || record.record_id}
        </span>
      </div>
      <div className="mt-2 grid gap-1">
        <p className="break-words text-xs text-muted-foreground">
          {record.source_category}
          {record.subject ? ` / ${record.subject}` : ""}
          {record.event_type ? ` / ${record.event_type}` : ""}
        </p>
        <p className="line-clamp-2 break-words font-mono-ui text-xs">
          {record.payload_summary || record.message_event_summary || "-"}
        </p>
        <p className="truncate text-[11px] text-muted-foreground">
          {formatTime(record.consumed_at)} {record.session_id ? `/ ${record.session_id}` : ""}
        </p>
      </div>
    </button>
  );
}

function SourceStatusBadge({ status }: { status: GatewaySourceStatus | null }) {
  const gateway = status?.gateway_state || "unknown";
  const linz = status?.linz_world?.state ? String(status.linz_world.state) : "";
  return (
    <span className="flex flex-wrap items-center gap-2">
      <Badge tone={statusTone(gateway)} className="text-[10px]">
        {DEFAULT_TEXT.sourceStatus}: {gateway}
      </Badge>
      {linz && (
        <Badge tone={statusTone(linz)} className="text-[10px]">
          {DEFAULT_TEXT.linzWorld}: {linz}
        </Badge>
      )}
    </span>
  );
}

function DetailPanel({
  detail,
  loading,
  payloadExpanded,
  setPayloadExpanded,
}: {
  detail: GatewayMessageEventDetailResponse | null;
  loading: boolean;
  payloadExpanded: boolean;
  setPayloadExpanded: (expanded: boolean) => void;
}) {
  if (loading) {
    return (
      <Card className="min-h-[360px]">
        <CardContent className="flex min-h-[360px] items-center justify-center gap-2 text-sm text-muted-foreground">
          <Spinner />
          {DEFAULT_TEXT.detail}
        </CardContent>
      </Card>
    );
  }

  if (!detail) {
    return (
      <Card className="min-h-[360px]">
        <CardContent className="flex min-h-[360px] items-center justify-center text-center text-sm text-muted-foreground">
          {DEFAULT_TEXT.selectRecord}
        </CardContent>
      </Card>
    );
  }

  const record = detail.record;
  const projection = detail.projection;
  const payloadText = record.raw_payload_available
    ? compactJson(record.raw_payload)
    : record.raw_payload_error || DEFAULT_TEXT.payloadUnavailable;

  return (
    <Card className="min-w-0">
      <CardHeader className="px-4 py-3">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <FileText className="h-4 w-4 shrink-0" />
            <span className="truncate">{DEFAULT_TEXT.detail}</span>
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(record.consume_status)} className="text-[10px]">
              {record.consume_status}
            </Badge>
            <Badge tone={statusTone(record.projection_status)} className="text-[10px]">
              {record.projection_status}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid min-w-0 gap-4">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="record_id" value={record.record_id} />
          <Field label="event_id" value={record.event_id} />
          <Field label="source_category" value={record.source_category} />
          <Field label="platform" value={record.platform} />
          <Field label="subject" value={record.subject} />
          <Field label="event_type" value={record.event_type} />
          <Field label="sequence_key" value={record.sequence_key} />
          <Field label="nats_sequence" value={record.nats_sequence} />
          <Field label="consumed_at" value={formatTime(record.consumed_at)} />
          <Field label="updated_at" value={formatTime(record.updated_at)} />
        </div>

        <div className="grid gap-2">
          <p className="text-[10px] tracking-[0.14em] text-muted-foreground">payload_summary</p>
          <p className="break-words font-mono-ui text-xs">{record.payload_summary || "-"}</p>
        </div>

        <div className="border border-border/70 bg-secondary/10 p-3">
          <div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-3">
            <p className="flex min-w-0 items-center gap-2 text-xs">
              <Database className="h-4 w-4 shrink-0" />
              <span className="truncate">{DEFAULT_TEXT.messageEvent}</span>
            </p>
            {projection?.message_event_id && (
              <Badge tone="secondary" className="text-[10px]">
                {projection.message_event_id}
              </Badge>
            )}
          </div>
          {projection ? (
            <div className="grid gap-2">
              <Field label="message_type" value={projection.message_type} />
              <Field label="session_id" value={projection.session_id} />
              <Field label="session_key" value={projection.session_key} />
              <Field label="session_message_ref" value={projection.session_message_ref} />
              <Field label="projected_at" value={formatTime(projection.projected_at)} />
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words border border-border/50 bg-background/40 p-3 font-mono-ui text-xs">
                {projection.text_summary || projection.raw_message_summary || "-"}
              </pre>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No projection recorded.</p>
          )}
        </div>

        <div className="border border-border/70">
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-b border-border/70 p-3">
            <p className="text-xs">{DEFAULT_TEXT.rawPayload}</p>
            <Button
              type="button"
              size="sm"
              outlined
              onClick={() => setPayloadExpanded(!payloadExpanded)}
              prefix={payloadExpanded ? <ChevronUp /> : <ChevronDown />}
            >
              {payloadExpanded ? DEFAULT_TEXT.hidePayload : DEFAULT_TEXT.showPayload}
            </Button>
          </div>
          {payloadExpanded && (
            <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap break-words p-3 font-mono-ui text-xs leading-5 normal-case">
              {payloadText}
            </pre>
          )}
        </div>

        <div className="grid gap-2">
          <p className="text-xs">{DEFAULT_TEXT.transitions}</p>
          <div className="grid gap-2">
            {detail.transitions.map((transition) => (
              <div
                key={transition.transition_id}
                className="grid gap-1 border border-border/50 bg-secondary/10 p-2 text-xs"
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <Badge tone={statusTone(transition.to_status)} className="text-[10px]">
                    {transition.to_status}
                  </Badge>
                  <span className="text-muted-foreground">{formatTime(transition.at)}</span>
                </div>
                {(transition.reason || transition.error) && (
                  <p className="break-words font-mono-ui text-[11px] text-muted-foreground">
                    {transition.reason || transition.error}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function WorldEventsPage() {
  const { t } = useI18n();
  const { setAfterTitle, setEnd } = usePageHeader();
  const [records, setRecords] = useState<GatewayMessageEventSummary[]>([]);
  const [sourceStatus, setSourceStatus] = useState<GatewaySourceStatus | null>(null);
  const [profile, setProfile] = useState("current");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GatewayMessageEventDetailResponse | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [sourceCategory, setSourceCategory] = useState<string>("all");
  const [consumeStatus, setConsumeStatus] = useState<"all" | GatewayConsumeStatus>("all");
  const [projectionStatus, setProjectionStatus] = useState<"all" | GatewayProjectionStatus>("all");
  const [limit, setLimit] = useState<(typeof LIMITS)[number]>(100);
  const [subject, setSubject] = useState("");
  const [eventType, setEventType] = useState("");
  const [query, setQuery] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [payloadExpanded, setPayloadExpanded] = useState(false);
  const text = DEFAULT_TEXT;

  const activeFilterCount = useMemo(
    () =>
      [
        sourceCategory !== "all",
        consumeStatus !== "all",
        projectionStatus !== "all",
        subject.trim(),
        eventType.trim(),
        query.trim(),
      ].filter(Boolean).length,
    [consumeStatus, eventType, projectionStatus, query, sourceCategory, subject],
  );

  const buildParams = useCallback(
    (cursor?: string | null): GatewayMessageEventQuery => ({
      limit,
      profile,
      cursor: cursor || undefined,
      source_category: sourceCategory === "all" ? undefined : sourceCategory,
      consume_status: consumeStatus === "all" ? undefined : consumeStatus,
      projection_status: projectionStatus === "all" ? undefined : projectionStatus,
      subject: subject.trim() || undefined,
      event_type: eventType.trim() || undefined,
      q: query.trim() || undefined,
    }),
    [consumeStatus, eventType, limit, profile, projectionStatus, query, sourceCategory, subject],
  );

  const loadRecords = useCallback(
    (opts: { append?: boolean; cursor?: string | null } = {}) => {
      setLoading(true);
      setError(null);
      api
        .getGatewayMessageEvents(buildParams(opts.cursor))
        .then((resp) => {
          setSourceStatus(resp.source_status);
          setNextCursor(resp.next_cursor);
          setLastRefresh(new Date());
          setRecords((current) => (opts.append ? [...current, ...resp.records] : resp.records));
          if (!opts.append) {
            setSelectedId((current) =>
              current && resp.records.some((record) => record.record_id === current)
                ? current
                : resp.records[0]?.record_id ?? null,
            );
          }
        })
        .catch((err) => setError(String(err)))
        .finally(() => setLoading(false));
    },
    [buildParams],
  );

  useEffect(() => {
    const timeout = window.setTimeout(() => loadRecords(), 0);
    return () => window.clearTimeout(timeout);
  }, [loadRecords]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = window.setInterval(() => loadRecords(), 5000);
    return () => window.clearInterval(interval);
  }, [autoRefresh, loadRecords]);

  useEffect(() => {
    if (!selectedId) {
      const timeout = window.setTimeout(() => setDetail(null), 0);
      return () => window.clearTimeout(timeout);
    }
    const timeout = window.setTimeout(() => {
      setDetailLoading(true);
      api
        .getGatewayMessageEventDetail(selectedId, profile)
        .then(setDetail)
        .catch((err) => {
          setDetail(null);
          setError(String(err));
        })
        .finally(() => setDetailLoading(false));
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [profile, selectedId]);

  useLayoutEffect(() => {
    setAfterTitle(
      <span className="flex min-w-0 items-center gap-2">
        {loading && <Spinner className="shrink-0 text-base text-primary" />}
        <Badge tone="secondary" className="text-[10px]">
          {records.length} / {limit}
        </Badge>
        <SourceStatusBadge status={sourceStatus} />
      </span>,
    );
    setEnd(
      <div className="flex w-full min-w-0 flex-nowrap items-center justify-end gap-1.5 sm:gap-2">
        <ProfileSelector
          value={profile}
          onChange={(nextProfile) => {
            setProfile(nextProfile);
            setRecords([]);
            setSelectedId(null);
            setDetail(null);
            setNextCursor(null);
          }}
        />
        <div className="flex shrink-0 items-center gap-1.5">
          <Switch
            checked={autoRefresh}
            onCheckedChange={setAutoRefresh}
            id="events-auto-refresh"
          />
          <Label htmlFor="events-auto-refresh" className="cursor-pointer text-xs">
            {text.autoRefresh}
          </Label>
          {autoRefresh && (
            <Badge tone="success" className="text-[10px]">
              <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              {t.common.live}
            </Badge>
          )}
        </div>
        {lastRefresh && (
          <Badge tone="outline" className="text-[10px]">
            {text.updated}: {lastRefresh.toLocaleTimeString()}
          </Badge>
        )}
        <Button
          type="button"
          size="sm"
          outlined
          onClick={() => loadRecords()}
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
    lastRefresh,
    limit,
    loadRecords,
    loading,
    profile,
    records.length,
    setAfterTitle,
    setEnd,
    sourceStatus,
    t.common.live,
    t.common.refresh,
    text.autoRefresh,
    text.updated,
  ]);

  const clearFilters = () => {
    setSourceCategory("all");
    setConsumeStatus("all");
    setProjectionStatus("all");
    setSubject("");
    setEventType("");
    setQuery("");
  };

  const emptyText = activeFilterCount ? text.noMatch : text.noRecords;

  return (
    <div className="flex min-w-0 flex-col gap-4" data-demo-records={WORLD_EVENTS_DEMO_RECORDS.length}>
      <PluginSlot name="world-events:top" />

      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Database className="h-4 w-4 shrink-0" />
          <span className="break-words">{text.subtitle}</span>
        </div>
      </div>

      <div role="toolbar" aria-label={text.title} className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <FilterGroup label={text.sourceCategory}>
          <Segmented
            value={sourceCategory}
            onChange={setSourceCategory}
            options={options(SOURCE_CATEGORIES, text)}
          />
        </FilterGroup>

        <FilterGroup label={text.consumeStatus}>
          <Segmented
            value={consumeStatus}
            onChange={(value) => setConsumeStatus(value as "all" | GatewayConsumeStatus)}
            options={options(CONSUME_STATUSES, text)}
          />
        </FilterGroup>

        <FilterGroup label={text.projectionStatus}>
          <Segmented
            value={projectionStatus}
            onChange={(value) => setProjectionStatus(value as "all" | GatewayProjectionStatus)}
            options={options(PROJECTION_STATUSES, text)}
          />
        </FilterGroup>

        <FilterGroup label={text.limit}>
          <Segmented
            value={String(limit)}
            onChange={(value) => setLimit(Number(value) as (typeof LIMITS)[number])}
            options={LIMITS.map((value) => ({ value: String(value), label: String(value) }))}
          />
        </FilterGroup>

        <label className="grid min-w-[180px] gap-1">
          <span className="text-[10px] tracking-[0.14em] text-muted-foreground">{text.subject}</span>
          <input
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            className="h-8 border border-border bg-background/50 px-2 font-mono-ui text-xs outline-none focus:border-primary"
          />
        </label>

        <label className="grid min-w-[180px] gap-1">
          <span className="text-[10px] tracking-[0.14em] text-muted-foreground">{text.eventType}</span>
          <input
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            className="h-8 border border-border bg-background/50 px-2 font-mono-ui text-xs outline-none focus:border-primary"
          />
        </label>

        <label className="grid min-w-[220px] flex-1 gap-1">
          <span className="text-[10px] tracking-[0.14em] text-muted-foreground">{text.query}</span>
          <span className="flex h-8 items-center border border-border bg-background/50 px-2 focus-within:border-primary">
            <Search className="mr-2 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent font-mono-ui text-xs outline-none"
            />
          </span>
        </label>

        <Button
          type="button"
          size="sm"
          outlined
          onClick={clearFilters}
          disabled={!activeFilterCount}
          prefix={<X />}
        >
          {text.clearFilters}
        </Button>
      </div>

      {error && (
        <div className="flex min-w-0 items-start gap-2 border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="break-words">{text.failedToLoad}: {error}</span>
        </div>
      )}

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.35fr)]">
        <div className="grid min-w-0 content-start gap-3">
          {records.length === 0 && !loading ? (
            <Card>
              <CardContent className="flex min-h-[240px] items-center justify-center text-center text-sm text-muted-foreground">
                {emptyText}
              </CardContent>
            </Card>
          ) : (
            records.map((record) => (
              <EventRow
                key={record.record_id}
                record={record}
                selected={selectedId === record.record_id}
                onSelect={() => {
                  setPayloadExpanded(false);
                  setSelectedId(record.record_id);
                }}
              />
            ))
          )}

          {loading && records.length === 0 && (
            <Card>
              <CardContent className="flex min-h-[240px] items-center justify-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                {t.common.loading}
              </CardContent>
            </Card>
          )}

          {nextCursor && (
            <Button
              type="button"
              outlined
              onClick={() => loadRecords({ append: true, cursor: nextCursor })}
              disabled={loading}
              prefix={loading ? <Spinner /> : <ChevronDown />}
              className="justify-center"
            >
              {text.loadMore}
            </Button>
          )}
        </div>

        <DetailPanel
          detail={detail}
          loading={detailLoading}
          payloadExpanded={payloadExpanded}
          setPayloadExpanded={setPayloadExpanded}
        />
      </div>
    </div>
  );
}
