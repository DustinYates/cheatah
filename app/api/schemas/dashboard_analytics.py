"""Pydantic schemas for admin dashboard analytics endpoints."""

from datetime import datetime
from pydantic import BaseModel


# --- Communications Health ---

class ChannelMetrics(BaseModel):
    total: int = 0
    inbound: int = 0
    outbound: int = 0


class CallDurationMetrics(BaseModel):
    total_minutes: float = 0.0
    avg_seconds: float = 0.0
    median_seconds: float = 0.0
    short_call_pct: float = 0.0  # <30s
    long_call_pct: float = 0.0  # >10min
    total_calls: int = 0


class BotHumanWorkload(BaseModel):
    bot_handled_pct: float = 0.0
    human_handled_pct: float = 0.0
    escalated_pct: float = 0.0
    bot_resolution_rate: float = 0.0
    escalation_rate: float = 0.0
    avg_time_to_escalation_seconds: float = 0.0


class ReliabilityMetrics(BaseModel):
    dropped_calls: int = 0
    failed_calls: int = 0
    failed_sms: int = 0
    bounced_emails: int = 0
    api_errors: int = 0


class TrendComparison(BaseModel):
    current: int = 0
    previous: int = 0
    change_pct: float | None = None


class CommunicationsHealthResponse(BaseModel):
    calls: ChannelMetrics = ChannelMetrics()
    sms: ChannelMetrics = ChannelMetrics()
    email: ChannelMetrics = ChannelMetrics()
    total_interactions: int = 0
    channel_mix: dict[str, float] = {}  # {"calls": 0.4, "sms": 0.5, "email": 0.1}
    trend: TrendComparison = TrendComparison()
    call_duration: CallDurationMetrics = CallDurationMetrics()
    bot_human: BotHumanWorkload = BotHumanWorkload()
    reliability: ReliabilityMetrics = ReliabilityMetrics()


class HeatmapCell(BaseModel):
    day: int  # 0=Monday, 6=Sunday
    hour: int  # 0-23
    calls: int = 0
    sms: int = 0


class HeatmapResponse(BaseModel):
    cells: list[HeatmapCell] = []


class YearlyActivityCell(BaseModel):
    date: str  # YYYY-MM-DD
    calls: int = 0
    sms: int = 0
    emails: int = 0


class YearlyActivityResponse(BaseModel):
    cells: list[YearlyActivityCell] = []


# --- Anomaly Alerts ---

class AnomalyAlertResponse(BaseModel):
    id: int
    alert_type: str
    severity: str
    metric_name: str
    current_value: float
    baseline_value: float
    threshold_percent: float
    details: dict | None = None
    status: str
    detected_at: datetime


class AnomalyAlertListResponse(BaseModel):
    alerts: list[AnomalyAlertResponse] = []
    active_count: int = 0


# --- CHI ---

class CHISignalItem(BaseModel):
    name: str
    weight: int
    detail: str = ""


class CHISummaryResponse(BaseModel):
    avg_chi_today: float | None = None
    avg_chi_7d: float | None = None
    trend_pct: float | None = None  # vs prior 7d
    conversations_scored: int = 0


class CHIByHandler(BaseModel):
    handler: str  # "bot" or human name
    handler_type: str  # "bot" or "human"
    avg_chi: float
    conversation_count: int


class CHIDistributionBucket(BaseModel):
    bucket: str  # "0-20", "20-40", etc.
    count: int
    pct: float


class FrustrationDriver(BaseModel):
    signal: str
    count: int
    avg_impact: float


class ImprovementOpportunity(BaseModel):
    recommendation: str
    supporting_count: int
    estimated_chi_impact: float


class CHIAnalyticsResponse(BaseModel):
    summary: CHISummaryResponse = CHISummaryResponse()
    by_handler: list[CHIByHandler] = []
    distribution: list[CHIDistributionBucket] = []
    top_frustration_drivers: list[FrustrationDriver] = []
    repeat_contact_rate_48h: float = 0.0
    improvement_opportunities: list[ImprovementOpportunity] = []


class CHIDetailResponse(BaseModel):
    conversation_id: int
    score: float
    computed_at: datetime | None = None
    frustration_score: float = 0.0
    satisfaction_score: float = 0.0
    outcome_score: float = 0.0
    signals: list[CHISignalItem] = []


# --- SMS Burst ---

class SmsBurstSummary(BaseModel):
    total_incidents_24h: int = 0
    numbers_impacted: int = 0
    total_messages_in_bursts: int = 0
    worst_offender_number: str | None = None
    worst_offender_count: int = 0
    active_critical_count: int = 0


class SmsBurstIncidentResponse(BaseModel):
    id: int
    tenant_id: int
    to_number_masked: str  # e.g. "***-***-1234"
    message_count: int
    first_message_at: datetime
    last_message_at: datetime
    time_window_seconds: int
    avg_gap_seconds: float
    severity: str
    has_identical_content: bool
    content_similarity_score: float | None = None
    likely_cause: str | None = None
    handler: str | None = None
    status: str
    auto_blocked: bool
    notes: str | None = None
    detected_at: datetime


class SmsBurstDashboardResponse(BaseModel):
    summary: SmsBurstSummary = SmsBurstSummary()
    incidents: list[SmsBurstIncidentResponse] = []


class SmsBurstConfigResponse(BaseModel):
    enabled: bool = True
    time_window_seconds: int = 180
    message_threshold: int = 3
    high_severity_threshold: int = 5
    rapid_gap_min_seconds: int = 5
    rapid_gap_max_seconds: int = 29
    identical_content_threshold: int = 2
    similarity_threshold: float = 0.9
    auto_block_enabled: bool = False
    auto_block_threshold: int = 10
    excluded_flows: list[str] = []


class SmsBurstConfigUpdate(BaseModel):
    enabled: bool | None = None
    time_window_seconds: int | None = None
    message_threshold: int | None = None
    high_severity_threshold: int | None = None
    rapid_gap_min_seconds: int | None = None
    rapid_gap_max_seconds: int | None = None
    identical_content_threshold: int | None = None
    similarity_threshold: float | None = None
    auto_block_enabled: bool | None = None
    auto_block_threshold: int | None = None
    excluded_flows: list[str] | None = None
