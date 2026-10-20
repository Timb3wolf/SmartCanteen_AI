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
