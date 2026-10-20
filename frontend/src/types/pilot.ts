/**
 * Type definitions for SmartCanteen AI Phase 7 Operational Pilot Data Capture.
 */

export interface MealService {
  service_id: string;
  service_date: string;
  meal_period: 'Breakfast' | 'Lunch' | 'Dinner';
  canteen_section: 'A' | 'B' | 'C' | 'D';
  status: 'Planned' | 'In_Prep' | 'Serving' | 'Closed' | 'Audited';
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MenuItem {
  item_id: string;
  item_name: string;
  food_category: 'Meat' | 'Rice' | 'Soup' | 'Vegetables';
  standard_portion_unit: string;
  standard_portion_grams: number;
  created_at: string;
}

export interface DemandObservation {
  observation_id: string;
  service_id: string;
  cutoff_timestamp: string;
  observation_source: 'Timetable' | 'Wifi_Count' | 'Preorder' | 'Historical_Average' | 'Kitchen_Estimate';
  expected_headcount: number;
  confidence_score?: number | null;
  recorded_by?: string | null;
  recorded_at: string;
}

export interface ProductionRecord {
  production_id: string;
  menu_entry_id: string;
  batch_number: number;
  portions_prepared: number;
  prepared_weight_kg?: number | null;
  batch_completion_time?: string | null;
  logged_by?: string | null;
  created_at: string;
}

export interface ServiceRecord {
  service_record_id: string;
  menu_entry_id: string;
  portions_served: number;
  stockout_occurred: boolean;
  stockout_time?: string | null;
  data_source: 'POS_Register' | 'Manual_Count';
  logged_by?: string | null;
  created_at: string;
}

export interface WasteRecord {
  waste_id: string;
  menu_entry_id: string;
  unserved_surplus_weight_kg: number;
  plate_waste_weight_kg: number;
  disposal_destination?: 'Compost' | 'Donation' | 'Landfill' | 'Anaerobic_Digestion' | null;
  scale_id?: string | null;
  logged_by?: string | null;
  created_at: string;
}

export interface MenuEntryDetail {
  menu_entry_id: string;
  item_id: string;
  item_name: string;
  food_category: string;
  standard_portion_grams: number;
  planned_portions?: number | null;
  total_portions_prepared: number;
  total_cooked_weight_kg: number;
  total_portions_served: number;
  stockout_occurred: boolean;
  total_unserved_surplus_kg: number;
  total_plate_waste_kg: number;
  production_records: ProductionRecord[];
  service_records: ServiceRecord[];
  waste_records: WasteRecord[];
}

export interface ServiceDetails {
  service: MealService;
  observations: DemandObservation[];
  menu_entries: MenuEntryDetail[];
  is_complete: boolean;
  validation_warnings: string[];
}

export interface ReadinessGate {
  gate_id: string;
  gate_name: string;
  is_met: boolean;
  current_metric: string | number;
  target_metric: string | number;
  details: string;
}

export interface PilotQualityReport {
  pilot_section: string;
  pilot_meal_period: string;
  total_services_recorded: number;
  complete_services_count: number;
  logging_compliance_rate_pct: number;
  services_with_missing_pos: number;
  services_with_stockouts: number;
  readiness_gates: ReadinessGate[];
  is_pilot_ready_for_ml: boolean;
  holdout_policy: {
    status: string;
    reserve_days: number;
    rule: string;
    description: string;
  };
}

export interface POSImportResult {
  success: boolean;
  imported_count: number;
  skipped_count: number;
  errors: string[];
  warnings: string[];
  batch_timestamp: string;
}
