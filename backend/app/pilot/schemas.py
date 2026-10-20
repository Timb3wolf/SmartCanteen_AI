"""Pydantic schemas and request/response models for the Pilot Data Capture API."""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# =========================================================================
# 1. Meal Service Schemas
# =========================================================================

class MealServiceCreate(BaseModel):
    service_date: str = Field(..., description="Service date in YYYY-MM-DD format")
    meal_period: Literal["Breakfast", "Lunch", "Dinner"] = Field(..., description="Service period")
    canteen_section: Literal["A", "B", "C", "D"] = Field(..., description="Canteen dining section")
    scheduled_start: Optional[str] = Field(None, description="ISO timestamp for service start")
    scheduled_end: Optional[str] = Field(None, description="ISO timestamp for service end")

    @field_validator("service_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("service_date must be in ISO format (YYYY-MM-DD)")


class MealServiceStatusUpdate(BaseModel):
    status: Literal["Planned", "In_Prep", "Serving", "Closed", "Audited"] = Field(..., description="New status")
    notes: Optional[str] = None
    updated_by: Optional[str] = Field("staff", description="Staff identifier")


class MealServiceResponse(BaseModel):
    service_id: str
    service_date: str
    meal_period: str
    canteen_section: str
    service_status: str
    scheduled_start: str
    scheduled_end: str
    created_at: str
    updated_at: str


# =========================================================================
# 2. Menu Item Schemas
# =========================================================================

class MenuItemCreate(BaseModel):
    item_id: str = Field(..., min_length=2, max_length=64, description="Unique dish identifier slug")
    item_name: str = Field(..., min_length=2, max_length=128, description="Human-readable dish name")
    food_category: Literal["Meat", "Rice", "Soup", "Vegetables"]
    standard_portion_unit: str = Field("portions", description="Standard unit (e.g. portions, grams, bowls)")
    standard_portion_grams: float = Field(150.0, gt=0.0, description="Nominal cooked portion mass in grams")


class MenuItemResponse(BaseModel):
    item_id: str
    item_name: str
    food_category: str
    standard_portion_unit: str
    standard_portion_grams: float
    is_active: bool
    created_at: str


# =========================================================================
# 3. Meal Menu Bridge Schemas
# =========================================================================

class MealMenuCreate(BaseModel):
    item_id: str = Field(..., description="ID of menu item to schedule")
    planned_portions: int = Field(0, ge=0, description="Initial planning target")
    unit_price: float = Field(..., ge=0.0, description="Retail selling price per portion")
    ingredient_cost_per_portion: float = Field(..., ge=0.0, description="Procurement raw goods cost")


class MealMenuResponse(BaseModel):
    menu_entry_id: str
    service_id: str
    item_id: str
    item_name: Optional[str] = None
    food_category: Optional[str] = None
    planned_portions: int
    unit_price: float
    ingredient_cost_per_portion: float
    is_available: bool


# =========================================================================
# 4. Demand Observation Schemas
# =========================================================================

class DemandObservationCreate(BaseModel):
    observation_timestamp: Optional[str] = Field(None, description="When observation was made (ISO)")
    expected_headcount: int = Field(..., ge=0, description="Estimated student/staff footfall")
    observation_source: str = Field("Timetable_Schedule", description="Timetable, WiFi, Turnstile, Manual")
    registered_reservations: int = Field(0, ge=0, description="Pre-ordered meal count")
    notes: Optional[str] = None
    recorded_by: Optional[str] = Field("staff", description="Staff identifier")


class DemandObservationResponse(BaseModel):
    observation_id: str
    service_id: str
    observation_timestamp: str
    expected_headcount: int
    observation_source: str
    registered_reservations: int
    notes: Optional[str]
    recorded_at: str
    recorded_by: Optional[str]


# =========================================================================
# 5. Production Record Schemas
# =========================================================================

class ProductionRecordCreate(BaseModel):
    measurement_time: Optional[str] = Field(None, description="Batch completion time (ISO)")
    batch_number: int = Field(1, ge=1, description="Sequential batch number")
    portions_prepared: int = Field(..., ge=0, description="Count of cooked portions")
    prepared_weight_kg: Optional[float] = Field(None, ge=0.0, description="Scale weight of batch in kg")
    kitchen_station: str = Field("Main_Station", description="Prep station")
    recorded_by: Optional[str] = Field("chef", description="Staff badge ID")


class ProductionRecordResponse(BaseModel):
    production_id: str
    menu_entry_id: str
    measurement_time: str
    batch_number: int
    portions_prepared: int
    prepared_weight_kg: Optional[float]
    kitchen_station: str
    recorded_at: str
    recorded_by: Optional[str]
    superseded_by_id: Optional[str]


# =========================================================================
# 6. Service Record Schemas
# =========================================================================

class ServiceRecordCreate(BaseModel):
    measurement_time: Optional[str] = Field(None, description="POS reading time (ISO)")
    portions_served: int = Field(..., ge=0, description="Total portions dispensed")
    stockout_occurred: bool = Field(False, description="Did dish run out during service?")
    stockout_time: Optional[str] = Field(None, description="Time of stockout if applicable")
    gross_sales_amount: float = Field(0.0, ge=0.0, description="Total sales in currency")
    data_source: str = Field("POS_Register", description="POS_Register, Manual_Audit, POS_CSV_Import")
    recorded_by: Optional[str] = Field("cashier", description="Staff badge ID")


class ServiceRecordResponse(BaseModel):
    service_record_id: str
    menu_entry_id: str
    measurement_time: str
    portions_served: int
    stockout_occurred: bool
    stockout_time: Optional[str]
    gross_sales_amount: float
    data_source: str
    recorded_at: str
    recorded_by: Optional[str]
    superseded_by_id: Optional[str]


# =========================================================================
# 7. Waste Record Schemas
# =========================================================================

class WasteRecordCreate(BaseModel):
    measurement_time: Optional[str] = Field(None, description="Weighing time (ISO)")
    unserved_surplus_weight_kg: float = Field(..., ge=0.0, description="Unserved kitchen leftovers in kg")
    plate_waste_weight_kg: float = Field(..., ge=0.0, description="Customer plate waste in kg")
    disposal_destination: str = Field("Compost", description="Compost, Donation, Biofuel, Chilled_Reuse, Landfill")
    measurement_method: str = Field("Digital_Scale", description="Digital_Scale, Floor_Scale, Visual_Estimate")
    recorded_by: Optional[str] = Field("auditor", description="Staff badge ID")


class WasteRecordResponse(BaseModel):
    waste_id: str
    menu_entry_id: str
    measurement_time: str
    unserved_surplus_weight_kg: float
    plate_waste_weight_kg: float
    disposal_destination: str
    measurement_method: str
    recorded_at: str
    recorded_by: Optional[str]
    superseded_by_id: Optional[str]


# =========================================================================
# 8. Aggregated Service Details Response
# =========================================================================

class MenuEntryDetail(BaseModel):
    menu_entry_id: str
    item_id: str
    item_name: str
    food_category: str
    planned_portions: int
    unit_price: float
    ingredient_cost_per_portion: float
    is_available: bool
    production_records: List[ProductionRecordResponse] = []
    service_records: List[ServiceRecordResponse] = []
    waste_records: List[WasteRecordResponse] = []
    total_portions_prepared: int = 0
    total_portions_served: int = 0
    total_unserved_surplus_kg: float = 0.0
    total_plate_waste_kg: float = 0.0


class ServiceDetailsResponse(BaseModel):
    service: MealServiceResponse
    observations: List[DemandObservationResponse] = []
    menu_entries: List[MenuEntryDetail] = []
    is_complete: bool = False
    validation_warnings: List[str] = []


# =========================================================================
# 9. POS Import Schemas
# =========================================================================

class POSImportRow(BaseModel):
    service_date: str
    meal_period: str
    canteen_section: str
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    portions_served: int = Field(..., ge=0)
    gross_sales_amount: float = Field(0.0, ge=0.0)
    stockout_occurred: bool = False
    measurement_time: Optional[str] = None


class POSImportPayload(BaseModel):
    csv_content: str = Field(..., description="Raw CSV string content exported from POS system")


class POSImportResponse(BaseModel):
    success: bool
    total_rows_processed: int
    imported_count: int
    skipped_count: int
    errors: List[str] = []
    warnings: List[str] = []


# =========================================================================
# 10. Pilot Quality & Readiness Report Schemas
# =========================================================================

class ReadinessGateStatus(BaseModel):
    gate_id: str
    name: str
    description: str
    is_met: bool
    current_value: str
    required_value: str
    details: str


class PilotQualityReportResponse(BaseModel):
    pilot_section: str
    pilot_meal_period: str
    total_services_recorded: int
    target_services_count: int
    complete_services_count: int
    compliance_rate: float
    target_compliance_rate: float
    services_missing_headcount: int
    services_missing_production: int
    services_missing_pos_service: int
    services_missing_waste: int
    late_entries_count: int
    holdout_policy: Dict[str, Any]
    readiness_gates: List[ReadinessGateStatus]
    is_pilot_ready_for_ml: bool
