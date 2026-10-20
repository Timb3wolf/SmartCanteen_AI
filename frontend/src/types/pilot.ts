/**
 * Type definitions for SmartCanteen AI Phase 7 & 8 Operational Pilot Data Capture.
 */

export interface MealService {
  service_id: string;
  service_date: string;
  meal_period: 'Breakfast' | 'Lunch' | 'Dinner';
  canteen_section: 'A' | 'B' | 'C' | 'D';
  status: 'Planned' | 'In_Prep' | 'Serving' | 'Closed' | 'Audited';
  service_status?: string;
  scheduled_start?: string;
  scheduled_end?: string;
  prediction_cutoff_time?: string;
  service_timezone?: string;
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
  observation_timestamp?: string;
  expected_headcount: number;
  observation_source: 'Timetable' | 'Wifi_Count' | 'Preorder' | 'Historical_Average' | 'Kitchen_Estimate' | string;
  registered_reservations?: number;
  is_late_entry?: boolean;
  prediction_cutoff_timestamp?: string | null;
  notes?: string | null;
  recorded_by?: string | null;
  recorded_at: string;
}

export interface ProductionRecord {
  production_id: string;
  menu_entry_id: string;
  batch_number: number;
  portions_prepared: number;
  prepared_weight_kg?: number | null;
  kitchen_station?: string;
  correction_reason?: string | null;
  logged_by?: string | null;
  recorded_by?: string | null;
  recorded_at?: string;
  superseded_by_id?: string | null;
  created_at?: string;
}

export interface ServiceRecord {
  service_record_id: string;
  menu_entry_id: string;
  portions_served: number;
  stockout_occurred: boolean;
  stockout_time?: string | null;
  gross_sales_amount?: number;
  data_source: 'POS_Register' | 'Manual_Count' | 'POS_CSV_Import' | string;
  correction_reason?: string | null;
  logged_by?: string | null;
  recorded_by?: string | null;
  recorded_at?: string;
  superseded_by_id?: string | null;
  created_at?: string;
}

export interface WasteRecord {
  waste_id: string;
  menu_entry_id: string;
  unserved_surplus_weight_kg: number;
  plate_waste_weight_kg: number;
  disposal_destination?: 'Compost' | 'Donation' | 'Landfill' | 'Anaerobic_Digestion' | string | null;
  measurement_method?: string;
  correction_reason?: string | null;
  logged_by?: string | null;
  recorded_by?: string | null;
  recorded_at?: string;
  superseded_by_id?: string | null;
  created_at?: string;
}

export interface MenuEntryDetail {
  menu_entry_id: string;
  item_id: string;
  item_name: string;
  food_category: string;
  standard_portion_grams: number;
  planned_portions?: number | null;
  unit_price?: number;
  ingredient_cost_per_portion?: number;
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
  name: string;
  description: string;
  status: 'MET' | 'BLOCKED' | 'NOT_STARTED' | 'INVALID';
  is_met: boolean;
  current_value: string;
  required_value: string;
  evidence_count?: number | null;
  denominator?: number | null;
  details: string;
}

export interface PilotQualityReport {
  pilot_section: string;
  pilot_meal_period: string;
  total_services_recorded: number;
  target_services_count: number;
  complete_services_count: number;
  compliance_rate: number;
  target_compliance_rate: number;
  services_missing_headcount: number;
  services_missing_production: number;
  services_missing_pos_service: number;
  services_missing_waste: number;
  late_entries_count: number;
  holdout_policy: {
    reserve_days: number;
    policy_rule: string;
    holdout_gate_status?: string;
    historical_holdout_status: string;
  };
  readiness_gates: ReadinessGate[];
  is_pilot_ready_for_ml: boolean;
}

export interface POSImportResult {
  success: boolean;
  total_rows_processed: number;
  imported_count: number;
  skipped_count: number;
  errors: string[];
  warnings: string[];
  accepted_row_indices?: number[];
  rejected_rows?: Array<{ row: number; reason: string }>;
}

export interface ProductionCorrectionPayload {
  portions_prepared: number;
  prepared_weight_kg?: number;
  kitchen_station?: string;
  correction_reason: string;
  corrected_by?: string;
}

export interface ServiceCorrectionPayload {
  portions_served: number;
  stockout_occurred: boolean;
  stockout_time?: string;
  gross_sales_amount: number;
  correction_reason: string;
  corrected_by?: string;
}

export interface WasteCorrectionPayload {
  unserved_surplus_weight_kg: number;
  plate_waste_weight_kg: number;
  disposal_destination: string;
  correction_reason: string;
  corrected_by?: string;
}
