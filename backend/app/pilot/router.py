"""FastAPI Router for the SmartCanteen AI Pilot Data Capture API."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from backend.app.pilot.schemas import (
    DemandObservationCreate,
    DemandObservationResponse,
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
    ProductionRecordCreate,
    ProductionRecordResponse,
    ServiceDetailsResponse,
    ServiceRecordCreate,
    ServiceRecordResponse,
    WasteRecordCreate,
    WasteRecordResponse,
)
from backend.app.pilot.service import PilotDataService

router = APIRouter(prefix="/pilot", tags=["Pilot Data Capture"])
_default_pilot_service = PilotDataService()


def get_pilot_service() -> PilotDataService:
    """Dependency provider for PilotDataService."""
    return _default_pilot_service


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
):
    """Schedule a new meal service event."""
    try:
        return service.create_meal_service(req)
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
):
    """Update service status (e.g. advance from Serving to Closed or Audited)."""
    try:
        return service.update_service_status(
            service_id, req.status, notes=req.notes, performed_by=req.updated_by
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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
):
    """Register a new dish recipe in the master catalog."""
    try:
        return service.create_menu_item(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/services/{service_id}/menu", response_model=MealMenuResponse, status_code=status.HTTP_201_CREATED)
def add_menu_to_service(
    service_id: str,
    req: MealMenuCreate,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Schedule a dish item on a specific meal service."""
    try:
        return service.add_menu_to_service(service_id, req)
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
    """Log pre-service expected headcount from timetable, Wi-Fi, or manual estimates."""
    try:
        return service.record_demand_observation(service_id, req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 4. Production, Service & Waste Logging
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


# =========================================================================
# 5. POS CSV Import Engine
# =========================================================================

@router.post("/pos/import", response_model=POSImportResponse)
async def import_pos_file(
    request: Request,
    payload: Optional[POSImportPayload] = None,
    service: PilotDataService = Depends(get_pilot_service),
):
    """Import and validate an end-of-day POS transaction CSV via JSON payload or raw body."""
    if payload and payload.csv_content:
        content_str = payload.csv_content
        performed_by = "api_payload"
    else:
        content_bytes = await request.body()
        if not content_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No CSV content provided.")
        try:
            content_str = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            content_str = content_bytes.decode("latin-1")
        performed_by = "raw_body_upload"

    res = service.import_pos_csv(content_str, performed_by=performed_by)
    return res


# =========================================================================
# 6. Quality Report & Export
# =========================================================================

@router.get("/quality-report", response_model=PilotQualityReportResponse)
def get_pilot_quality_report(service: PilotDataService = Depends(get_pilot_service)):
    """Retrieve data quality summary, logging compliance rate, and Phase 6 readiness gates."""
    return service.get_quality_report()


@router.get("/export")
def export_pilot_records(service: PilotDataService = Depends(get_pilot_service)):
    """Export validated, reconciled pilot records as JSON."""
    records = service.export_flat_dataset()
    return JSONResponse(
        content={
            "exported_at": service.get_quality_report().pilot_section,
            "total_records": len(records),
            "records": records,
        }
    )
