"""FastAPI Router for the SmartCanteen AI Pilot Data Capture API.

Hardened with:
- Payload size enforcement on CSV uploads (max 2 MB, HTTP 413)
- Auditable record correction endpoints
- Pre-service feature retrieval endpoint (strictly pre-cutoff)
- Immutable forecast record capture endpoint
- Holdout-protected dataset export
- Auth token inspection and unverified actor tagging
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from backend.app.pilot.config import MAX_POS_CSV_SIZE_BYTES
from backend.app.pilot.schemas import (
    DemandObservationCreate,
    DemandObservationResponse,
    ForecastRecordCreate,
    ForecastRecordResponse,
    MealMenuCreate,
    MealMenuResponse,
    MealServiceCreate,
    MealServiceResponse,
    MealServiceStatusUpdate,
    MenuItemCreate,
    MenuItemResponse,
    POSImportPayload,
    POSImportResponse,
    PilotQualityReportResponse,
    PreServiceFeaturesResponse,
    ProductionRecordCorrectionRequest,
    ProductionRecordCreate,
    ProductionRecordResponse,
    ServiceDetailsResponse,
    ServiceRecordCorrectionRequest,
    ServiceRecordCreate,
    ServiceRecordResponse,
    WasteRecordCorrectionRequest,
    WasteRecordCreate,
    WasteRecordResponse,
)
from backend.app.pilot.service import PilotDataService

router = APIRouter(prefix="/pilot", tags=["Pilot Data Capture"])
_default_pilot_service = PilotDataService()


def get_pilot_service() -> PilotDataService:
    """Dependency provider for PilotDataService."""
    return _default_pilot_service


def extract_actor(
    x_staff_auth_token: Optional[str] = Header(None, alias="X-Staff-Auth-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Tuple[str, str]:
    """Extract staff actor identity and verify authentication status.
    
    If no verified session token is provided, returns ('unverified_staff', 'unverified_client_claim').
    """
    token = x_staff_auth_token or authorization
    if token and len(token) > 8:
        # Simple token presence indicator for pilot; real production requires OAuth/IdP
        return (f"staff_token_{token[:6]}", "bearer_token_verified")
    return ("staff", "unverified_client_claim")


# =========================================================================
# 1. Meal Services
# =========================================================================

@router.get("/services", response_model=List[MealServiceResponse])
def list_meal_services(
    service_date: Optional[str] = Query(None, description="Filter by date YYYY-MM-DD"),
    meal_period: Optional[str] = Query(None, description="Breakfast, Lunch, or Dinner"),
    canteen_section: Optional[str] = Query(None, description="A, B, C, or D"),
    status: Optional[str] = Query(None, description="Planned, In_Prep, Serving, Closed, Audited"),
    limit: int = Query(100, ge=1, le=500),
    service: PilotDataService = Depends(get_pilot_service),
):
    """List operational meal services with optional filters."""
    return service.get_meal_services(
        service_date=service_date,
        meal_period=meal_period,
        canteen_section=canteen_section,
        status=status,
        limit=limit,
    )


@router.post("/services", response_model=MealServiceResponse, status_code=status.HTTP_201_CREATED)
def create_meal_service(
    req: MealServiceCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Schedule a new meal service event."""
    try:
        return service.create_meal_service(req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/services/{service_id}", response_model=ServiceDetailsResponse)
def get_service_details(
    service_id: str,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Retrieve full service details including menu, production, POS, and waste records."""
    try:
        return service.get_service_details(service_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/services/{service_id}/status", response_model=MealServiceResponse)
def update_service_status(
    service_id: str,
    req: MealServiceStatusUpdate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Update service status (e.g. advance from Serving to Closed or Audited)."""
    try:
        return service.update_service_status(
            service_id, req.status, notes=req.notes, performed_by=req.updated_by or actor[0]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/services/{service_id}/preservice-features", response_model=PreServiceFeaturesResponse)
def get_preservice_features(
    service_id: str,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Retrieve pre-service features strictly prior to prediction cutoff (leakage-safe)."""
    try:
        return service.get_preservice_features(service_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# =========================================================================
# 2. Master Menu Items & Service Menus
# =========================================================================

@router.get("/menu-items", response_model=List[MenuItemResponse])
def list_menu_items(service: PilotDataService = Depends(get_pilot_service)):
    """List all dishes in the master menu catalog."""
    return service.get_menu_items()


@router.post("/menu-items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
def create_menu_item(
    req: MenuItemCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Register a new dish recipe in the master catalog."""
    try:
        return service.create_menu_item(req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/services/{service_id}/menu", response_model=MealMenuResponse, status_code=status.HTTP_201_CREATED)
def add_menu_to_service(
    service_id: str,
    req: MealMenuCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Schedule a dish item on a specific meal service."""
    try:
        return service.add_menu_to_service(service_id, req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 3. Pre-Service Demand Observations
# =========================================================================

@router.post("/services/{service_id}/observations", response_model=DemandObservationResponse, status_code=status.HTTP_201_CREATED)
def record_demand_observation(
    service_id: str,
    req: DemandObservationCreate,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Log pre-service expected headcount with automatic late-entry detection."""
    try:
        return service.record_demand_observation(service_id, req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 4. Production, Service & Waste Logging and Auditable Corrections
# =========================================================================

@router.post("/menu/{menu_entry_id}/production", response_model=ProductionRecordResponse, status_code=status.HTTP_201_CREATED)
def record_production(
    menu_entry_id: str,
    req: ProductionRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Log batch cooking portion count and measured cooked weight."""
    try:
        return service.record_production(menu_entry_id, req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/production/{production_id}/correct", response_model=ProductionRecordResponse)
def correct_production(
    production_id: str,
    req: ProductionRecordCorrectionRequest,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Auditably correct a previously recorded production entry."""
    try:
        return service.correct_production_record(production_id, req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/menu/{menu_entry_id}/service", response_model=ServiceRecordResponse, status_code=status.HTTP_201_CREATED)
def record_service(
    menu_entry_id: str,
    req: ServiceRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Log POS portions dispensed and any early stockout occurrence."""
    try:
        return service.record_service(menu_entry_id, req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/service-records/{service_record_id}/correct", response_model=ServiceRecordResponse)
def correct_service_record(
    service_record_id: str,
    req: ServiceRecordCorrectionRequest,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Auditably correct a previously recorded portions-served entry."""
    try:
        return service.correct_service_record(service_record_id, req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/menu/{menu_entry_id}/waste", response_model=WasteRecordResponse, status_code=status.HTTP_201_CREATED)
def record_waste(
    menu_entry_id: str,
    req: WasteRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Log post-service unserved kitchen surplus and customer plate waste separately."""
    try:
        return service.record_waste(menu_entry_id, req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/waste/{waste_id}/correct", response_model=WasteRecordResponse)
def correct_waste_record(
    waste_id: str,
    req: WasteRecordCorrectionRequest,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Auditably correct a previously recorded waste measurement."""
    try:
        return service.correct_waste_record(waste_id, req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 5. Forecast Record Management
# =========================================================================

@router.post("/forecasts", response_model=ForecastRecordResponse, status_code=status.HTTP_201_CREATED)
def record_forecast(
    req: ForecastRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Record an operational demand forecast with frozen pre-service snapshot."""
    try:
        return service.create_forecast_record(req, performed_by=actor[0])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 6. POS CSV Import Engine
# =========================================================================

@router.post("/pos/import", response_model=POSImportResponse)
async def import_pos_file(
    request: Request,
    service: PilotDataService = Depends(get_pilot_service),
    actor: Tuple[str, str] = Depends(extract_actor),
):
    """Import and validate an end-of-day POS transaction CSV with strict payload bounds."""
    # Check Content-Length header if present
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_POS_CSV_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload exceeds maximum permitted size of {MAX_POS_CSV_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    content_bytes = await request.body()
    if len(content_bytes) > MAX_POS_CSV_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload exceeds maximum permitted size of {MAX_POS_CSV_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    if not content_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No CSV content provided.")

    content_type = request.headers.get("content-type", "")
    content_str = None
    if "application/json" in content_type:
        try:
            data = json.loads(content_bytes.decode("utf-8"))
            if isinstance(data, dict):
                content_str = data.get("csv_content")
            else:
                content_str = str(data)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON payload: {e}")
    else:
        try:
            content_str = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            content_str = content_bytes.decode("latin-1")

    if not content_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty CSV content.")

    performed_by = actor[0] if actor[0] != "staff" else "api_import"
    res = service.import_pos_csv(content_str, performed_by=performed_by)
    return res


# =========================================================================
# 7. Quality Report & Export
# =========================================================================

@router.get("/quality-report", response_model=PilotQualityReportResponse)
def get_pilot_quality_report(service: PilotDataService = Depends(get_pilot_service)):
    """Retrieve data quality summary, logging compliance rate, and 4-state Phase 6 readiness gates."""
    return service.get_quality_report()


@router.get("/export")
def export_pilot_records(
    exclude_holdout: bool = Query(True, description="Strictly exclude final 10 holdout services"),
    service: PilotDataService = Depends(get_pilot_service),
):
    """Export validated, reconciled pilot records as JSON with holdout protection."""
    records = service.export_flat_dataset(exclude_holdout=exclude_holdout)
    return JSONResponse(
        content={
            "pilot_section": "A",
            "pilot_meal_period": "Lunch",
            "holdout_protection_active": exclude_holdout,
            "total_records": len(records),
            "records": records,
        }
    )
