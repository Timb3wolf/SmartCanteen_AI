/**
 * API client service for SmartCanteen AI
 */

import {
  AnalyticsSummary,
  DistributionData,
  FilterState,
  HealthStatus,
  Metadata,
  ModelMetrics,
  PaginatedRecords,
  PredictionHistory,
  PredictionRequest,
  PredictionResult,
  RecommendationsResponse,
} from '../types';

const API_BASE = '/api';

function buildQuery(params: Record<string, string | number | string[] | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      if (value.length > 0) {
        query.append(key, value.join(','));
      }
    } else {
      query.append(key, String(value));
    }
  }
  const qs = query.toString();
  return qs ? `?${qs}` : '';
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Failed to retrieve system health');
  return res.json();
}

export async function fetchMetadata(): Promise<Metadata> {
  const res = await fetch(`${API_BASE}/metadata`);
  if (!res.ok) throw new Error('Failed to retrieve canteen metadata');
  return res.json();
}

export async function fetchAnalyticsSummary(filters: FilterState): Promise<AnalyticsSummary> {
  const qs = buildQuery({
    start_date: filters.startDate,
    end_date: filters.endDate,
    meal: filters.meals,
    canteen_section: filters.sections,
    food_category: filters.categories,
  });
  const res = await fetch(`${API_BASE}/analytics/summary${qs}`);
  if (!res.ok) throw new Error('Failed to fetch analytics summary');
  return res.json();
}

export async function fetchAnalyticsDistribution(filters: FilterState): Promise<DistributionData> {
  const qs = buildQuery({
    start_date: filters.startDate,
    end_date: filters.endDate,
    meal: filters.meals,
    canteen_section: filters.sections,
    food_category: filters.categories,
  });
  const res = await fetch(`${API_BASE}/analytics/distribution${qs}`);
  if (!res.ok) throw new Error('Failed to fetch distribution analytics');
  return res.json();
}

export async function fetchAnalyticsRecommendations(filters: FilterState): Promise<RecommendationsResponse> {
  const qs = buildQuery({
    start_date: filters.startDate,
    end_date: filters.endDate,
    meal: filters.meals,
    canteen_section: filters.sections,
    food_category: filters.categories,
  });
  const res = await fetch(`${API_BASE}/analytics/recommendations${qs}`);
  if (!res.ok) throw new Error('Failed to fetch recommendations');
  return res.json();
}

export async function fetchRecords(
  filters: FilterState,
  search: string = '',
  sortBy: string = 'Date',
  sortOrder: 'asc' | 'desc' = 'desc',
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedRecords> {
  const qs = buildQuery({
    start_date: filters.startDate,
    end_date: filters.endDate,
    meal: filters.meals,
    canteen_section: filters.sections,
    food_category: filters.categories,
    search: search.trim() || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
    page,
    page_size: pageSize,
  });
  const res = await fetch(`${API_BASE}/analytics/records${qs}`);
  if (!res.ok) throw new Error('Failed to fetch canteen records');
  return res.json();
}

export function getExportCsvUrl(filters: FilterState, search: string = ''): string {
  const qs = buildQuery({
    start_date: filters.startDate,
    end_date: filters.endDate,
    meal: filters.meals,
    canteen_section: filters.sections,
    food_category: filters.categories,
    search: search.trim() || undefined,
  });
  return `${API_BASE}/analytics/export${qs}`;
}

export async function predictWaste(payload: PredictionRequest): Promise<PredictionResult> {
  const res = await fetch(`${API_BASE}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Prediction failed. Please check inputs.');
  }
  return res.json();
}

export async function fetchPredictionHistory(
  limit: number = 100,
  meal?: string,
  risk?: string
): Promise<PredictionHistory> {
  const qs = buildQuery({ limit, meal, risk });
  const res = await fetch(`${API_BASE}/predictions/history${qs}`);
  if (!res.ok) throw new Error('Failed to fetch prediction history');
  return res.json();
}

export async function clearPredictionHistory(): Promise<{ message: string; deleted_count: number }> {
  const res = await fetch(`${API_BASE}/predictions/history`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to clear prediction history');
  return res.json();
}

export async function fetchModelMetrics(): Promise<ModelMetrics> {
  const res = await fetch(`${API_BASE}/models/metrics`);
  if (!res.ok) throw new Error('Failed to fetch model evaluation metrics');
  return res.json();
}

// =========================================================================
// Phase 7 Pilot Operational Data Capture API
// =========================================================================

import type {
  MealService,
  MenuItem,
  DemandObservation,
  ProductionRecord,
  ServiceRecord,
  WasteRecord,
  ServiceDetails,
  PilotQualityReport,
  POSImportResult,
  ProductionCorrectionPayload,
  ServiceCorrectionPayload,
  WasteCorrectionPayload,
} from '../types/pilot';

export async function fetchPilotServices(section?: string, limit: number = 50): Promise<MealService[]> {
  const qs = buildQuery({ canteen_section: section, limit });
  const res = await fetch(`${API_BASE}/pilot/services${qs}`);
  if (!res.ok) throw new Error('Failed to load pilot meal services');
  return res.json();
}

export async function createPilotService(payload: {
  service_date: string;
  meal_period: string;
  canteen_section: string;
  notes?: string;
}): Promise<MealService> {
  const res = await fetch(`${API_BASE}/pilot/services`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create meal service');
  }
  return res.json();
}

export async function fetchPilotServiceDetails(serviceId: string): Promise<ServiceDetails> {
  const res = await fetch(`${API_BASE}/pilot/services/${encodeURIComponent(serviceId)}`);
  if (!res.ok) throw new Error('Failed to load service details');
  return res.json();
}

export async function updatePilotServiceStatus(
  serviceId: string,
  status: string,
  notes?: string,
  updatedBy?: string
): Promise<MealService> {
  const res = await fetch(`${API_BASE}/pilot/services/${encodeURIComponent(serviceId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, notes, updated_by: updatedBy }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update service status');
  }
  return res.json();
}

export async function fetchPilotMenuItems(): Promise<MenuItem[]> {
  const res = await fetch(`${API_BASE}/pilot/menu-items`);
  if (!res.ok) throw new Error('Failed to load master menu items');
  return res.json();
}

export async function createPilotMenuItem(payload: {
  item_id: string;
  item_name: string;
  food_category: string;
  standard_portion_unit: string;
  standard_portion_grams: number;
}): Promise<MenuItem> {
  const res = await fetch(`${API_BASE}/pilot/menu-items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to register dish item');
  }
  return res.json();
}

export async function addMenuToPilotService(
  serviceId: string,
  payload: { item_id: string; planned_portions?: number }
): Promise<any> {
  const res = await fetch(`${API_BASE}/pilot/services/${encodeURIComponent(serviceId)}/menu`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to add dish to service');
  }
  return res.json();
}

export async function recordPilotDemandObservation(
  serviceId: string,
  payload: {
    observation_source: string;
    expected_headcount: number;
    confidence_score?: number;
    recorded_by?: string;
  }
): Promise<DemandObservation> {
  const res = await fetch(`${API_BASE}/pilot/services/${encodeURIComponent(serviceId)}/observations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to record pre-service headcount');
  }
  return res.json();
}

export async function recordPilotProduction(
  menuEntryId: string,
  payload: {
    portions_prepared: number;
    prepared_weight_kg?: number;
    batch_completion_time?: string;
    logged_by?: string;
  }
): Promise<ProductionRecord> {
  const res = await fetch(`${API_BASE}/pilot/menu/${encodeURIComponent(menuEntryId)}/production`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to record batch production');
  }
  return res.json();
}

export async function recordPilotService(
  menuEntryId: string,
  payload: {
    portions_served: number;
    stockout_occurred: boolean;
    stockout_time?: string;
    data_source?: string;
    logged_by?: string;
  }
): Promise<ServiceRecord> {
  const res = await fetch(`${API_BASE}/pilot/menu/${encodeURIComponent(menuEntryId)}/service`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to record portions served');
  }
  return res.json();
}

export async function recordPilotWaste(
  menuEntryId: string,
  payload: {
    unserved_surplus_weight_kg: number;
    plate_waste_weight_kg: number;
    disposal_destination?: string;
    logged_by?: string;
  }
): Promise<WasteRecord> {
  const res = await fetch(`${API_BASE}/pilot/menu/${encodeURIComponent(menuEntryId)}/waste`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to record waste measurements');
  }
  return res.json();
}

export async function importPilotPOSCsv(csvContent: string): Promise<POSImportResult> {
  const res = await fetch(`${API_BASE}/pilot/pos/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csv_content: csvContent }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'POS CSV import failed');
  }
  return res.json();
}

export async function fetchPilotQualityReport(): Promise<PilotQualityReport> {
  const res = await fetch(`${API_BASE}/pilot/quality-report`);
  if (!res.ok) throw new Error('Failed to load pilot quality report');
  return res.json();
}

export function getPilotExportUrl(excludeHoldout: boolean = true): string {
  return `${API_BASE}/pilot/export?exclude_holdout=${excludeHoldout}`;
}

export async function correctPilotProduction(
  productionId: string,
  payload: ProductionCorrectionPayload
): Promise<ProductionRecord> {
  const res = await fetch(`${API_BASE}/pilot/production/${encodeURIComponent(productionId)}/correct`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to correct production record');
  }
  return res.json();
}

export async function correctPilotService(
  serviceRecordId: string,
  payload: ServiceCorrectionPayload
): Promise<ServiceRecord> {
  const res = await fetch(`${API_BASE}/pilot/service-records/${encodeURIComponent(serviceRecordId)}/correct`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to correct service record');
  }
  return res.json();
}

export async function correctPilotWaste(
  wasteId: string,
  payload: WasteCorrectionPayload
): Promise<WasteRecord> {
  const res = await fetch(`${API_BASE}/pilot/waste/${encodeURIComponent(wasteId)}/correct`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to correct waste record');
  }
  return res.json();
}


