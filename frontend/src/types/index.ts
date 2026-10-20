/**
 * Data contracts and type definitions for SmartCanteen AI
 */

export interface HealthStatus {
  status: 'healthy' | 'degraded';
  dataset_available: boolean;
  record_count: number;
  models_loaded: boolean;
  models: {
    regression_model: boolean;
    classifier_model: boolean;
    feature_schema: boolean;
  };
  timestamp: string;
}

export interface DateRange {
  min_date: string;
  max_date: string;
}

export interface PriceRange {
  min: number;
  max: number;
  mean: number;
}

export interface Metadata {
  meals: string[];
  canteen_sections: string[];
  food_categories: string[];
  risk_categories: string[];
  date_range: DateRange;
  unit_price_range: PriceRange;
  feature_columns: string[];
  total_dataset_records: number;
}

export interface FilterState {
  startDate?: string;
  endDate?: string;
  meals: string[];
  sections: string[];
  categories: string[];
}

export interface AnalyticsSummary {
  total_waste_kg: number;
  avg_waste_per_record_kg: number;
  total_financial_loss: number;
  record_count: number;
  avg_waste_per_service_kg: number;
  avg_daily_waste_kg: number;
  start_date?: string;
  end_date?: string;
}

export interface CategoryWasteItem {
  category: string;
  waste_kg: number;
  percentage: number;
}

export interface MealWasteItem {
  meal: string;
  waste_kg: number;
  percentage: number;
}

export interface SectionWasteItem {
  section: string;
  waste_kg: number;
  percentage: number;
}

export interface CategoryLossItem {
  category: string;
  cost_loss: number;
  percentage: number;
}

export interface RiskDistributionItem {
  risk: string;
  count: number;
  percentage: number;
}

export interface DailyTrendItem {
  date: string;
  waste_kg: number;
  cost_loss: number;
  record_count: number;
}

export interface DistributionData {
  waste_by_category: CategoryWasteItem[];
  waste_by_meal: MealWasteItem[];
  waste_by_section: SectionWasteItem[];
  financial_loss_by_category: CategoryLossItem[];
  risk_distribution: RiskDistributionItem[];
  daily_waste_trend: DailyTrendItem[];
}

export interface Recommendation {
  id: string;
  category: string;
  type: 'warning' | 'info' | 'success' | 'danger';
  title: string;
  description: string;
  metric_value?: string;
  action_item: string;
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
  generated_at: string;
}

export interface RecordItem {
  Date: string;
  Meal: string;
  Canteen_Section: string;
  Food_Category: string;
  Waste_Weight_kg: number;
  Unit_Price_per_kg: number;
  Cost_Loss: number;
  Waste_Risk: string;
}

export interface PaginatedRecords {
  items: RecordItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PredictionRequest {
  date: string;
  meal: string;
  canteen_section: string;
  food_category: string;
  unit_price_per_kg: number;
}

export interface PredictionResult {
  id?: number;
  prediction_date: string;
  meal: string;
  canteen_section: string;
  food_category: string;
  unit_price_per_kg: number;
  predicted_waste_kg: number;
  predicted_risk: 'Low' | 'Medium' | 'High' | string;
  estimated_financial_loss: number;
  model_version: string;
  created_at: string;
  warnings?: string[];
}

export interface PredictionHistory {
  predictions: PredictionResult[];
  total: number;
}

export interface ModelMetrics {
  regression: {
    mae: number;
    rmse: number;
    r2_score: number;
    target: string;
  };
  classification: {
    accuracy: number;
    macro_precision: number;
    macro_recall: number;
    macro_f1: number;
    target: string;
  };
  features_count: number;
  features: string[];
  model_types: Record<string, string>;
  disclaimer: string;
  limitations: string[];
}
