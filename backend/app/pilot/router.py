"""FastAPI Router for the SmartCanteen AI Pilot Data Capture API.

Hardened with:
- Strict Token Authentication & Role-Based Access Control (RBAC):
  * staff: Service scheduling, menu allocation, demand observation, initial kitchen/service/waste logging.
  * supervisor: Staff actions + auditable record corrections + POS CSV register ingestion.
  * auditor: Read-only visibility over quality metrics, services, and pre-service features.
  * admin: Master catalog dish registration, holdout cohort sealing/reservation, raw data exports.
- Payload size enforcement on CSV uploads (max 2 MB, HTTP 413)
- Auditable record correction endpoints enforcing mandatory justification
- Pre-service feature retrieval endpoint (strictly pre-cutoff)
- Immutable forecast record capture endpoint with frozen pre-service snapshot
- Explicit Holdout Cohort reservation, update, sealing, and release endpoints
- Holdout-protected dataset export with access auditing
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from backend.app.pilot.auth import (
    AuthenticatedActor,
    Role,
    create_access_token,
    get_current_actor,
    require_admin,
    require_any_authenticated,
    require_auditor,
    require_role,
    require_staff,
    require_supervisor,
)
from backend.app.pilot.config import (
    MAX_POS_CSV_SIZE_BYTES,
    PILOT_ACCESS_TOKEN_EXPIRE_MINUTES,
)
from backend.app.pilot.schemas import (
    DemandObservationCreate,
    DemandObservationResponse,
    ForecastRecordCreate,
    ForecastRecordResponse,
    HoldoutCohortCreate,
    HoldoutCohortReleaseRequest,
    HoldoutCohortResponse,
    HoldoutCohortSealRequest,
    HoldoutCohortUpdateRequest,
    MealMenuCreate,
    MealMenuResponse,
    MealServiceCreate,
    MealServiceResponse,
    MealServiceStatusUpdate,
    MenuItemCreate,
    MenuItemResponse,
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
    TokenRequest,
    TokenResponse,
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
    actor: AuthenticatedActor = Depends(get_current_actor),
) -> Tuple[str, str]:
    """Extract staff actor identity and verified authentication status from token.
    
    Provided for backward compatibility with existing internal service callers.
    """
    auth_status = "bearer_token_verified" if actor.is_authenticated else "unverified_client_claim"
    return (actor.actor_id, auth_status)


# =========================================================================
# 0. Authentication & Token Exchange
# =========================================================================

@router.post("/auth/token", response_model=TokenResponse)
def generate_staff_token(req: TokenRequest):
    """Issue a signed HS256 JWT access token for operational staff or testing.
    
    In a physical deployment, this is superseded by the enterprise Identity Provider / SSO.
    """
    valid_roles = [r.value for r in Role]
    if req.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{req.role}'. Must be one of: {valid_roles}",
        )
    token = create_access_token(actor_id=req.actor_id, role=req.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=PILOT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        actor_id=req.actor_id,
        role=req.role,
    )


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
    actor: AuthenticatedActor = Depends(require_any_authenticated),
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
    actor: AuthenticatedActor = Depends(require_staff),
):
    """Schedule a new meal service event (staff, supervisor, admin)."""
    try:
        return service.create_meal_service(req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/services/{service_id}", response_model=ServiceDetailsResponse)
def get_service_details(
    service_id: str,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_any_authenticated),
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
    actor: AuthenticatedActor = Depends(require_staff),
):
    """Update service status (e.g. advance from Serving to Closed or Audited)."""
    try:
        return service.update_service_status(
            service_id, req.status, notes=req.notes, performed_by=req.updated_by or actor.actor_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/services/{service_id}/preservice-features", response_model=PreServiceFeaturesResponse)
def get_preservice_features(
    service_id: str,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_any_authenticated),
):
    """Retrieve pre-service features strictly prior to prediction cutoff (leakage-safe)."""
    try:
        return service.get_preservice_features(service_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# =========================================================================
# 2. Master Menu Items Catalog & Daily Menus
# =========================================================================

@router.post("/menu-items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
def create_menu_item(
    req: MenuItemCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_admin),
):
    """Register a new standardized dish in the master catalog (admin only)."""
    try:
        return service.create_menu_item(req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/menu-items", response_model=List[MenuItemResponse])
def get_menu_items(
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_any_authenticated),
):
    """List all available standardized dishes."""
    return service.get_menu_items()


@router.post("/services/{service_id}/menu", response_model=MealMenuResponse, status_code=status.HTTP_201_CREATED)
def add_menu_to_service(
    service_id: str,
    req: MealMenuCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_staff),
):
    """Schedule a dish from catalog to a specific meal service."""
    try:
        return service.add_menu_to_service(service_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 3. Demand Observations
# =========================================================================

@router.post("/services/{service_id}/observations", response_model=DemandObservationResponse, status_code=status.HTTP_201_CREATED)
def record_demand_observation(
    service_id: str,
    req: DemandObservationCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_staff),
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
    actor: AuthenticatedActor = Depends(require_staff),
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
    actor: AuthenticatedActor = Depends(require_supervisor),
):
    """Auditably correct a previously recorded production entry (supervisor or admin only)."""
    try:
        return service.correct_production_record(production_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/menu/{menu_entry_id}/service", response_model=ServiceRecordResponse, status_code=status.HTTP_201_CREATED)
def record_service(
    menu_entry_id: str,
    req: ServiceRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_staff),
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
    actor: AuthenticatedActor = Depends(require_supervisor),
):
    """Auditably correct a previously recorded portions-served entry (supervisor or admin only)."""
    try:
        return service.correct_service_record(service_record_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/menu/{menu_entry_id}/waste", response_model=WasteRecordResponse, status_code=status.HTTP_201_CREATED)
def record_waste(
    menu_entry_id: str,
    req: WasteRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_staff),
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
    actor: AuthenticatedActor = Depends(require_supervisor),
):
    """Auditably correct a previously recorded waste measurement (supervisor or admin only)."""
    try:
        return service.correct_waste_record(waste_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 5. Forecast Record Management
# =========================================================================

@router.post("/forecasts", response_model=ForecastRecordResponse, status_code=status.HTTP_201_CREATED)
def record_forecast(
    req: ForecastRecordCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_staff),
):
    """Record an operational demand forecast with frozen pre-service snapshot."""
    try:
        return service.create_forecast_record(req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =========================================================================
# 6. POS CSV Import Engine
# =========================================================================

@router.post("/pos/import", response_model=POSImportResponse)
async def import_pos_file(
    request: Request,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_supervisor),
):
    """Import and validate an end-of-day POS transaction CSV (supervisor or admin only)."""
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

    res = service.import_pos_csv(content_str, performed_by=actor.actor_id)
    return res


# =========================================================================
# 7. Quality Report & Export
# =========================================================================

@router.get("/quality-report", response_model=PilotQualityReportResponse)
def get_pilot_quality_report(
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_any_authenticated),
):
    """Retrieve data quality summary, logging compliance rate, and 4-state Phase 6 readiness gates."""
    return service.get_quality_report()


@router.get("/export")
def export_pilot_records(
    exclude_holdout: bool = Query(True, description="Strictly exclude final 10 holdout services"),
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_role([Role.SUPERVISOR, Role.ADMIN, Role.AUDITOR])),
):
    """Export validated, reconciled pilot records as JSON with holdout protection."""
    records = service.export_flat_dataset(exclude_holdout=exclude_holdout, performed_by=actor.actor_id)
    return JSONResponse(
        content={
            "pilot_section": "A",
            "pilot_meal_period": "Lunch",
            "holdout_protection_active": exclude_holdout,
            "total_records": len(records),
            "records": records,
        }
    )


# =========================================================================
# 8. Holdout Evaluation Cohort Endpoints
# =========================================================================

@router.post("/holdout/reserve", response_model=HoldoutCohortResponse, status_code=status.HTTP_201_CREATED)
def reserve_holdout_cohort(
    req: HoldoutCohortCreate,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_admin),
):
    """Reserve an explicit list of meal service IDs as the immutable holdout cohort (admin only)."""
    try:
        return service.reserve_holdout_cohort(req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/holdout/{cohort_id}", response_model=HoldoutCohortResponse)
def update_holdout_cohort(
    cohort_id: str,
    req: HoldoutCohortUpdateRequest,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_admin),
):
    """Update reserved service IDs prior to sealing with mandatory audit justification (admin only)."""
    try:
        return service.update_holdout_cohort(cohort_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/holdout/{cohort_id}/seal", response_model=HoldoutCohortResponse)
def seal_holdout_cohort(
    cohort_id: str,
    req: HoldoutCohortSealRequest,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_admin),
):
    """Permanently seal holdout cohort, rendering it strictly immutable (admin only)."""
    try:
        return service.seal_holdout_cohort(cohort_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/holdout/{cohort_id}/release", response_model=HoldoutCohortResponse)
def release_holdout_cohort(
    cohort_id: str,
    req: HoldoutCohortReleaseRequest,
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_admin),
):
    """Release sealed holdout cohort for final one-shot benchmark evaluation (admin only)."""
    try:
        return service.release_holdout_cohort(cohort_id, req, performed_by=actor.actor_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/holdout", response_model=Optional[HoldoutCohortResponse])
def get_holdout_cohort(
    cohort_id: Optional[str] = Query(None, description="Optional specific cohort ID"),
    service: PilotDataService = Depends(get_pilot_service),
    actor: AuthenticatedActor = Depends(require_any_authenticated),
):
    """Retrieve active or specific holdout cohort record."""
    cohort = service.get_holdout_cohort(cohort_id)
    if not cohort and cohort_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cohort '{cohort_id}' not found.")
    return cohort
