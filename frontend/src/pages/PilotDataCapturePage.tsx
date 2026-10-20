import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ClipboardList,
  Plus,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  UploadCloud,
  Download,
  RefreshCw,
  ChefHat,
  Users,
  Scale,
  Utensils,
  ShieldCheck,
  Calendar,
  Layers,
  ChevronRight,
  Info,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import {
  fetchPilotServices,
  createPilotService,
  fetchPilotServiceDetails,
  updatePilotServiceStatus,
  fetchPilotMenuItems,
  createPilotMenuItem,
  addMenuToPilotService,
  recordPilotDemandObservation,
  recordPilotProduction,
  recordPilotService,
  recordPilotWaste,
  importPilotPOSCsv,
  fetchPilotQualityReport,
  getPilotExportUrl,
} from '../services/api';
import type { MealService, MenuItem, ServiceDetails, POSImportResult } from '../types/pilot';

export function PilotDataCapturePage() {
  const queryClient = useQueryClient();

  // Active service selection
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [activeWorkflowTab, setActiveWorkflowTab] = useState<'preservice' | 'production' | 'service' | 'waste' | 'audit'>('preservice');
  const [showPOSModal, setShowPOSModal] = useState<boolean>(false);
  const [showQualityModal, setShowQualityModal] = useState<boolean>(false);
  const [showNewServiceModal, setShowNewServiceModal] = useState<boolean>(false);
  const [showNewDishModal, setShowNewDishModal] = useState<boolean>(false);

  // Form states
  const [newServiceForm, setNewServiceForm] = useState({
    service_date: new Date().toISOString().split('T')[0],
    meal_period: 'Lunch',
    canteen_section: 'A',
    notes: '',
  });

  const [newDishForm, setNewDishForm] = useState({
    item_id: '',
    item_name: '',
    food_category: 'Meat',
    standard_portion_unit: 'portions',
    standard_portion_grams: 200,
  });

  const [selectedDishToAdd, setSelectedDishToAdd] = useState<string>('');
  const [plannedPortionsInput, setPlannedPortionsInput] = useState<number>(100);

  // Step 1: Pre-service headcount form
  const [headcountForm, setHeadcountForm] = useState({
    expected_headcount: 250,
    observation_source: 'Timetable',
    confidence_score: 0.85,
    recorded_by: 'kitchen_manager',
  });

  // Step 2: Production form
  const [prodForm, setProdForm] = useState<Record<string, { batch_number: number; portions_prepared: number; prepared_weight_kg: number; logged_by: string }>>({});

  // Step 3: Service form
  const [servForm, setServForm] = useState<Record<string, { portions_served: number; stockout_occurred: boolean; stockout_time: string; logged_by: string }>>({});

  // Step 4: Waste form
  const [wasteForm, setWasteForm] = useState<Record<string, { unserved_surplus_weight_kg: number; plate_waste_weight_kg: number; disposal_destination: string; logged_by: string }>>({});

  // POS CSV text state
  const [posCsvText, setPosCsvText] = useState<string>(
    'service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred\n'
  );
  const [posImportResult, setPosImportResult] = useState<POSImportResult | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Queries
  const { data: services, isLoading: isLoadingServices, refetch: refetchServices } = useQuery({
    queryKey: ['pilot-services'],
    queryFn: () => fetchPilotServices('A', 30),
  });

  const { data: menuCatalog, refetch: refetchCatalog } = useQuery({
    queryKey: ['pilot-menu-items'],
    queryFn: fetchPilotMenuItems,
  });

  const effectiveServiceId = selectedServiceId || (services && services.length > 0 ? services[0].service_id : null);

  const { data: serviceDetails, isLoading: isLoadingDetails, refetch: refetchDetails } = useQuery({
    queryKey: ['pilot-service-details', effectiveServiceId],
    queryFn: () => (effectiveServiceId ? fetchPilotServiceDetails(effectiveServiceId) : null),
    enabled: !!effectiveServiceId,
  });

  const { data: qualityReport, refetch: refetchQuality } = useQuery({
    queryKey: ['pilot-quality-report'],
    queryFn: fetchPilotQualityReport,
  });

  // Helper notice
  const showNotice = (type: 'success' | 'error', text: string) => {
    setActionMessage({ type, text });
    setTimeout(() => setActionMessage(null), 5000);
  };

  // Mutations
  const createServiceMutation = useMutation({
    mutationFn: createPilotService,
    onSuccess: (data) => {
      showNotice('success', `Created service ${data.service_id}`);
      setShowNewServiceModal(false);
      refetchServices();
      setSelectedServiceId(data.service_id);
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const createDishMutation = useMutation({
    mutationFn: createPilotMenuItem,
    onSuccess: (data) => {
      showNotice('success', `Registered dish: ${data.item_name}`);
      setShowNewDishModal(false);
      refetchCatalog();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const addMenuMutation = useMutation({
    mutationFn: ({ serviceId, payload }: { serviceId: string; payload: any }) =>
      addMenuToPilotService(serviceId, payload),
    onSuccess: () => {
      showNotice('success', 'Dish added to service menu');
      refetchDetails();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const observationMutation = useMutation({
    mutationFn: ({ serviceId, payload }: { serviceId: string; payload: any }) =>
      recordPilotDemandObservation(serviceId, payload),
    onSuccess: () => {
      showNotice('success', 'Recorded pre-service headcount observation');
      refetchDetails();
      refetchQuality();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const productionMutation = useMutation({
    mutationFn: ({ menuEntryId, payload }: { menuEntryId: string; payload: any }) =>
      recordPilotProduction(menuEntryId, payload),
    onSuccess: () => {
      showNotice('success', 'Recorded kitchen batch production');
      refetchDetails();
      refetchQuality();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const serviceRecordMutation = useMutation({
    mutationFn: ({ menuEntryId, payload }: { menuEntryId: string; payload: any }) =>
      recordPilotService(menuEntryId, payload),
    onSuccess: () => {
      showNotice('success', 'Recorded portions served');
      refetchDetails();
      refetchQuality();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const wasteMutation = useMutation({
    mutationFn: ({ menuEntryId, payload }: { menuEntryId: string; payload: any }) =>
      recordPilotWaste(menuEntryId, payload),
    onSuccess: () => {
      showNotice('success', 'Recorded waste measurement (surplus & plate waste separate)');
      refetchDetails();
      refetchQuality();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const statusMutation = useMutation({
    mutationFn: ({ serviceId, status, notes }: { serviceId: string; status: string; notes?: string }) =>
      updatePilotServiceStatus(serviceId, status, notes, 'kitchen_lead'),
    onSuccess: () => {
      showNotice('success', 'Service status updated');
      refetchDetails();
      refetchServices();
      refetchQuality();
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  const posImportMutation = useMutation({
    mutationFn: importPilotPOSCsv,
    onSuccess: (data) => {
      setPosImportResult(data);
      refetchDetails();
      refetchQuality();
      refetchServices();
      if (data.success) {
        showNotice('success', `POS CSV: Imported ${data.imported_count} records (${data.skipped_count} skipped).`);
      } else {
        showNotice('error', 'POS CSV import contained errors.');
      }
    },
    onError: (err: any) => showNotice('error', err.message),
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Banner / Context */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-[#E3E8E1] shadow-xs">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 text-xs font-bold rounded-full bg-[#EBF1EA] text-[#245C46] border border-[#C5D7C0]">
              Phase 7 Operational Pilot
            </span>
            <span className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              Isolated Store: data/pilot_operational.db
            </span>
            <span className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-amber-50 text-amber-700 border border-amber-200">
              Target: Section A · Lunch
            </span>
          </div>
          <h1 className="text-2xl font-bold text-[#24312B] tracking-tight">Staff Operational Data Capture</h1>
          <p className="text-sm text-[#737D76] mt-0.5">
            Log genuine kitchen prep, POS portions served, and separated surplus/plate waste without ML interference.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowQualityModal(true)}
            className="flex items-center gap-1.5"
          >
            <ShieldCheck className="w-4 h-4 text-[#245C46]" />
            Quality & Readiness
            {qualityReport && (
              <span className="ml-1 text-[11px] font-bold px-1.5 py-0.2 bg-[#EBF1EA] text-[#245C46] rounded-full">
                {qualityReport.complete_services_count}/{qualityReport.total_services_recorded}
              </span>
            )}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowPOSModal(true)}
            className="flex items-center gap-1.5"
          >
            <UploadCloud className="w-4 h-4 text-blue-600" />
            Import POS CSV
          </Button>

          <a
            href={getPilotExportUrl()}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-[#E3E8E1] bg-white text-[#24312B] hover:bg-neutral-50 transition-colors"
          >
            <Download className="w-4 h-4 text-neutral-600" />
            Export JSON
          </a>

          <Button
            size="sm"
            onClick={() => setShowNewServiceModal(true)}
            className="bg-[#245C46] hover:bg-[#1b4736] text-white flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            New Service
          </Button>
        </div>
      </div>

      {/* Action Notice Alert */}
      {actionMessage && (
        <div
          className={`p-4 rounded-xl flex items-center gap-3 border ${
            actionMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}
        >
          {actionMessage.type === 'success' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          ) : (
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
          )}
          <span className="text-sm font-medium">{actionMessage.text}</span>
        </div>
      )}

      {/* Service Selector & Status Header */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Column: Service Selector List */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#24312B] uppercase tracking-wider">Meal Services</h3>
            <span className="text-xs text-[#737D76]">{services?.length || 0} recorded</span>
          </div>

          <div className="space-y-2 max-h-[580px] overflow-y-auto pr-1">
            {isLoadingServices && (
              <div className="p-4 text-center text-xs text-neutral-400">Loading services...</div>
            )}
            {services && services.length === 0 && (
              <div className="p-4 rounded-xl border border-dashed border-[#E3E8E1] text-center text-xs text-[#737D76]">
                No services logged yet. Click "+ New Service" to begin pilot data collection.
              </div>
            )}
            {services?.map((s) => {
              const isSelected = s.service_id === effectiveServiceId;
              return (
                <button
                  key={s.service_id}
                  onClick={() => setSelectedServiceId(s.service_id)}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-[#EBF1EA] border-[#245C46] shadow-xs'
                      : 'bg-white border-[#E3E8E1] hover:border-neutral-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-[#24312B]">{s.service_date}</span>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                        s.status === 'Closed' || s.status === 'Audited'
                          ? 'bg-neutral-100 text-neutral-700'
                          : s.status === 'Serving'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-emerald-100 text-emerald-800'
                      }`}
                    >
                      {s.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5 text-xs text-[#737D76]">
                    <span>{s.meal_period}</span>
                    <span>•</span>
                    <span>Sec {s.canteen_section}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column: Workflow Steps for Active Service */}
        <div className="lg:col-span-3 space-y-4">
          {!serviceDetails && !isLoadingDetails && (
            <Card className="p-8 text-center text-[#737D76]">
              Select a service from the left or create a new meal service to start data entry.
            </Card>
          )}

          {isLoadingDetails && (
            <Card className="p-8 text-center text-[#737D76]">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-[#245C46]" />
              Loading service details...
            </Card>
          )}

          {serviceDetails && (
            <>
              {/* Active Service Status Card */}
              <div className="bg-white p-5 rounded-2xl border border-[#E3E8E1] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-[#24312B]">
                      {serviceDetails.service.service_date} · {serviceDetails.service.meal_period} (Section {serviceDetails.service.canteen_section})
                    </h2>
                    <span className="text-xs px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-600 font-mono">
                      {serviceDetails.service.service_id}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-[#737D76]">
                    <span>Status: <strong className="text-[#24312B]">{serviceDetails.service.status}</strong></span>
                    <span>•</span>
                    <span>Dishes on Menu: <strong className="text-[#24312B]">{serviceDetails.menu_entries.length}</strong></span>
                    <span>•</span>
                    <span>
                      Completeness:{' '}
                      <span className={`font-semibold ${serviceDetails.is_complete ? 'text-emerald-700' : 'text-amber-700'}`}>
                        {serviceDetails.is_complete ? 'Complete' : 'Incomplete'}
                      </span>
                    </span>
                  </div>
                </div>

                {/* Status Advancement Controls */}
                <div className="flex items-center gap-2">
                  {serviceDetails.service.status === 'Planned' && (
                    <Button
                      size="sm"
                      onClick={() => statusMutation.mutate({ serviceId: serviceDetails.service.service_id, status: 'In_Prep' })}
                    >
                      Advance to In_Prep
                    </Button>
                  )}
                  {serviceDetails.service.status === 'In_Prep' && (
                    <Button
                      size="sm"
                      onClick={() => statusMutation.mutate({ serviceId: serviceDetails.service.service_id, status: 'Serving' })}
                    >
                      Start Serving
                    </Button>
                  )}
                  {serviceDetails.service.status === 'Serving' && (
                    <Button
                      size="sm"
                      onClick={() => statusMutation.mutate({ serviceId: serviceDetails.service.service_id, status: 'Closed' })}
                    >
                      Close Service
                    </Button>
                  )}
                  {serviceDetails.service.status === 'Closed' && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => statusMutation.mutate({ serviceId: serviceDetails.service.service_id, status: 'Audited' })}
                    >
                      Mark Audited
                    </Button>
                  )}
                </div>
              </div>

              {/* Validation Warnings Notice if any */}
              {serviceDetails.validation_warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl text-amber-900">
                  <div className="flex items-center gap-2 text-sm font-semibold mb-1">
                    <AlertTriangle className="w-4 h-4 text-amber-600" />
                    Pending Collection Actions:
                  </div>
                  <ul className="text-xs list-disc list-inside space-y-0.5 text-amber-800">
                    {serviceDetails.validation_warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Workflow Tabs */}
              <div className="flex border-b border-[#E3E8E1] space-x-1">
                {[
                  { id: 'preservice', label: '1. Pre-Service (T-4h)', icon: Users },
                  { id: 'production', label: '2. Kitchen Prep', icon: ChefHat },
                  { id: 'service', label: '3. Portions Served', icon: Utensils },
                  { id: 'waste', label: '4. Waste Log', icon: Scale },
                  { id: 'audit', label: '5. Audit Trail', icon: Layers },
                ].map((tab) => {
                  const Icon = tab.icon;
                  const isActive = activeWorkflowTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveWorkflowTab(tab.id as any)}
                      className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all ${
                        isActive
                          ? 'border-[#245C46] text-[#245C46] bg-[#EBF1EA]/30'
                          : 'border-transparent text-[#737D76] hover:text-[#24312B]'
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* TAB 1: PRE-SERVICE INPUTS */}
              {activeWorkflowTab === 'preservice' && (
                <div className="space-y-6 pt-2">
                  {/* Headcount Observation Box */}
                  <Card className="p-5">
                    <CardHeader className="p-0 mb-4">
                      <CardTitle className="text-sm font-bold text-[#24312B] flex items-center gap-2">
                        <Users className="w-4 h-4 text-[#245C46]" />
                        Pre-Service Headcount Estimate (Cutoff T - 4h)
                      </CardTitle>
                      <CardDescription className="text-xs text-[#737D76]">
                        Logged before food preparation begins. Legitimate input for future demand forecasting models.
                      </CardDescription>
                    </CardHeader>

                    {serviceDetails.observations.length > 0 ? (
                      <div className="space-y-3">
                        <div className="p-3 bg-emerald-50/60 border border-emerald-100 rounded-xl flex items-center justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-neutral-500">Recorded Headcount:</span>
                              {serviceDetails.observations[0].is_late_entry && (
                                <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-red-100 text-red-800 border border-red-200">
                                  Late Entry (Post T-4h Cutoff)
                                </span>
                              )}
                            </div>
                            <div className="text-xl font-bold text-[#24312B]">
                              {serviceDetails.observations[0].expected_headcount} guests
                            </div>
                            <span className="text-[11px] text-neutral-500">
                              Source: {serviceDetails.observations[0].observation_source} · Recorded by{' '}
                              {serviceDetails.observations[0].recorded_by || 'Staff'} · Cutoff:{' '}
                              {serviceDetails.observations[0].prediction_cutoff_timestamp?.slice(11, 16) || 'T-4h'}
                            </span>
                          </div>
                          <CheckCircle2 className="w-6 h-6 text-emerald-600" />
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                        <div>
                          <label className="text-xs font-medium text-neutral-700 block mb-1">Expected Headcount</label>
                          <input
                            type="number"
                            min="1"
                            value={headcountForm.expected_headcount}
                            onChange={(e) => setHeadcountForm({ ...headcountForm, expected_headcount: parseInt(e.target.value) || 0 })}
                            className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                          />
                        </div>
                        <div>
                          <label className="text-xs font-medium text-neutral-700 block mb-1">Observation Source</label>
                          <select
                            value={headcountForm.observation_source}
                            onChange={(e) => setHeadcountForm({ ...headcountForm, observation_source: e.target.value })}
                            className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                          >
                            <option value="Timetable">Timetable Enrollment</option>
                            <option value="Wifi_Count">Wi-Fi Footfall Probe</option>
                            <option value="Preorder">App Pre-orders</option>
                            <option value="Kitchen_Estimate">Kitchen Headcount Estimate</option>
                            <option value="Historical_Average">Historical Moving Average</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-xs font-medium text-neutral-700 block mb-1">Logged By</label>
                          <input
                            type="text"
                            value={headcountForm.recorded_by}
                            onChange={(e) => setHeadcountForm({ ...headcountForm, recorded_by: e.target.value })}
                            className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                          />
                        </div>
                        <div className="flex items-end">
                          <Button
                            size="sm"
                            className="w-full"
                            onClick={() =>
                              observationMutation.mutate({
                                serviceId: serviceDetails.service.service_id,
                                payload: headcountForm,
                              })
                            }
                          >
                            Save Headcount
                          </Button>
                        </div>
                      </div>
                    )}
                  </Card>

                  {/* Service Menu Dishes */}
                  <Card className="p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h4 className="text-sm font-bold text-[#24312B]">Scheduled Service Dishes</h4>
                        <p className="text-xs text-[#737D76]">Add dishes planned for this specific meal service.</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowNewDishModal(true)}
                          className="text-xs"
                        >
                          + New Catalog Recipe
                        </Button>
                      </div>
                    </div>

                    {/* Add Dish Row */}
                    <div className="flex flex-col sm:flex-row items-end gap-3 p-3 bg-neutral-50 rounded-xl mb-4 border border-[#E3E8E1]">
                      <div className="flex-1">
                        <label className="text-xs font-medium text-neutral-700 block mb-1">Select Catalog Dish</label>
                        <select
                          value={selectedDishToAdd}
                          onChange={(e) => setSelectedDishToAdd(e.target.value)}
                          className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1] bg-white"
                        >
                          <option value="">-- Choose a dish recipe --</option>
                          {menuCatalog?.map((m) => (
                            <option key={m.item_id} value={m.item_id}>
                              {m.item_name} ({m.food_category} · {m.standard_portion_grams}g)
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="w-32">
                        <label className="text-xs font-medium text-neutral-700 block mb-1">Planned Portions</label>
                        <input
                          type="number"
                          min="1"
                          value={plannedPortionsInput}
                          onChange={(e) => setPlannedPortionsInput(parseInt(e.target.value) || 0)}
                          className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1] bg-white"
                        />
                      </div>
                      <Button
                        size="sm"
                        disabled={!selectedDishToAdd}
                        onClick={() => {
                          addMenuMutation.mutate({
                            serviceId: serviceDetails.service.service_id,
                            payload: {
                              item_id: selectedDishToAdd,
                              planned_portions: plannedPortionsInput,
                            },
                          });
                          setSelectedDishToAdd('');
                        }}
                      >
                        Add to Menu
                      </Button>
                    </div>

                    {/* Scheduled dishes list */}
                    <div className="divide-y divide-[#E3E8E1]">
                      {serviceDetails.menu_entries.length === 0 && (
                        <div className="py-6 text-center text-xs text-neutral-400">
                          No dishes scheduled yet. Select a dish above to configure the service menu.
                        </div>
                      )}
                      {serviceDetails.menu_entries.map((entry) => (
                        <div key={entry.menu_entry_id} className="py-3 flex items-center justify-between">
                          <div>
                            <div className="font-semibold text-sm text-[#24312B]">{entry.item_name}</div>
                            <div className="text-xs text-neutral-500">
                              {entry.food_category} · Standard: {entry.standard_portion_grams}g · Planned:{' '}
                              <strong>{entry.planned_portions || 'N/A'}</strong> portions
                            </div>
                          </div>
                          <span className="text-xs px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-600 font-mono">
                            {entry.menu_entry_id}
                          </span>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              )}

              {/* TAB 2: KITCHEN PRODUCTION LOGGING */}
              {activeWorkflowTab === 'production' && (
                <div className="space-y-4 pt-2">
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-900 flex items-start gap-2">
                    <Info className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <strong>Production Batch Logging:</strong> Enter portions prepared and weighed cooked weight for each batch.
                      Multiple batches per dish are supported and aggregated automatically.
                    </div>
                  </div>

                  {serviceDetails.menu_entries.map((entry) => {
                    const f = prodForm[entry.menu_entry_id] || {
                      batch_number: (entry.production_records.length || 0) + 1,
                      portions_prepared: entry.planned_portions || 80,
                      prepared_weight_kg: Number((((entry.planned_portions || 80) * entry.standard_portion_grams) / 1000).toFixed(2)),
                      logged_by: 'cook_dan',
                    };

                    return (
                      <Card key={entry.menu_entry_id} className="p-4">
                        <div className="flex items-center justify-between mb-3 border-b border-[#E3E8E1] pb-2">
                          <div>
                            <h4 className="text-sm font-bold text-[#24312B]">{entry.item_name}</h4>
                            <span className="text-xs text-neutral-500">
                              Total Prepared: <strong>{entry.total_portions_prepared} portions</strong> ({entry.total_cooked_weight_kg} kg)
                            </span>
                          </div>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-600">
                            {entry.production_records.length} batch(es) recorded
                          </span>
                        </div>

                        {/* Batch form */}
                        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Batch #</label>
                            <input
                              type="number"
                              min="1"
                              value={f.batch_number}
                              onChange={(e) =>
                                setProdForm({
                                  ...prodForm,
                                  [entry.menu_entry_id]: { ...f, batch_number: parseInt(e.target.value) || 1 },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Portions Prepared</label>
                            <input
                              type="number"
                              min="0"
                              value={f.portions_prepared}
                              onChange={(e) =>
                                setProdForm({
                                  ...prodForm,
                                  [entry.menu_entry_id]: { ...f, portions_prepared: parseInt(e.target.value) || 0 },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Cooked Weight (kg)</label>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={f.prepared_weight_kg}
                              onChange={(e) =>
                                setProdForm({
                                  ...prodForm,
                                  [entry.menu_entry_id]: { ...f, prepared_weight_kg: parseFloat(e.target.value) || 0 },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Cook / Logger</label>
                            <input
                              type="text"
                              value={f.logged_by}
                              onChange={(e) =>
                                setProdForm({
                                  ...prodForm,
                                  [entry.menu_entry_id]: { ...f, logged_by: e.target.value },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div className="flex items-end">
                            <Button
                              size="sm"
                              className="w-full"
                              onClick={() =>
                                productionMutation.mutate({
                                  menuEntryId: entry.menu_entry_id,
                                  payload: f,
                                })
                              }
                            >
                              Log Batch
                            </Button>
                          </div>
                        </div>

                        {/* List existing batches */}
                        {entry.production_records.length > 0 && (
                          <div className="mt-3 pt-2 border-t border-[#E3E8E1] text-[11px] text-neutral-600 space-y-1">
                            {entry.production_records.map((rec) => (
                              <div key={rec.production_id} className="flex justify-between">
                                <span>Batch {rec.batch_number}: {rec.portions_prepared} portions ({rec.prepared_weight_kg || 0} kg)</span>
                                <span className="text-neutral-400">By {rec.logged_by || rec.recorded_by || 'Staff'} · {(rec.recorded_at || rec.created_at || '').slice(11, 16)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </Card>
                    );
                  })}
                </div>
              )}

              {/* TAB 3: PORTIONS SERVED & STOCKOUTS */}
              {activeWorkflowTab === 'service' && (
                <div className="space-y-4 pt-2">
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <strong>Portions Served & Early Stockouts:</strong> Log customer transactions dispensed through POS register
                      or counter count. If a dish ran out before service ended, mark stockout occurred.
                    </div>
                  </div>

                  {serviceDetails.menu_entries.map((entry) => {
                    const f = servForm[entry.menu_entry_id] || {
                      portions_served: entry.total_portions_served || Math.max(0, entry.total_portions_prepared - 5),
                      stockout_occurred: entry.stockout_occurred || false,
                      stockout_time: '',
                      logged_by: 'pos_cashier',
                    };

                    return (
                      <Card key={entry.menu_entry_id} className="p-4">
                        <div className="flex items-center justify-between mb-3 border-b border-[#E3E8E1] pb-2">
                          <div>
                            <h4 className="text-sm font-bold text-[#24312B]">{entry.item_name}</h4>
                            <span className="text-xs text-neutral-500">
                              Prepared: {entry.total_portions_prepared} portions · Currently Recorded Served:{' '}
                              <strong>{entry.total_portions_served} portions</strong>
                            </span>
                          </div>
                          {entry.stockout_occurred && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-semibold">
                              Stockout Flagged
                            </span>
                          )}
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Portions Served</label>
                            <input
                              type="number"
                              min="0"
                              value={f.portions_served}
                              onChange={(e) =>
                                setServForm({
                                  ...servForm,
                                  [entry.menu_entry_id]: { ...f, portions_served: parseInt(e.target.value) || 0 },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div className="flex items-center gap-2 pt-5">
                            <input
                              type="checkbox"
                              id={`stockout-${entry.menu_entry_id}`}
                              checked={f.stockout_occurred}
                              onChange={(e) =>
                                setServForm({
                                  ...servForm,
                                  [entry.menu_entry_id]: { ...f, stockout_occurred: e.target.checked },
                                })
                              }
                              className="rounded border-[#E3E8E1] text-[#245C46] focus:ring-[#245C46]"
                            />
                            <label htmlFor={`stockout-${entry.menu_entry_id}`} className="text-xs font-medium text-neutral-700">
                              Dish Stocked Out
                            </label>
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Cashier / Source</label>
                            <input
                              type="text"
                              value={f.logged_by}
                              onChange={(e) =>
                                setServForm({
                                  ...servForm,
                                  [entry.menu_entry_id]: { ...f, logged_by: e.target.value },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div className="flex items-end">
                            <Button
                              size="sm"
                              className="w-full"
                              onClick={() =>
                                serviceRecordMutation.mutate({
                                  menuEntryId: entry.menu_entry_id,
                                  payload: f,
                                })
                              }
                            >
                              Save Served Count
                            </Button>
                          </div>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}

              {/* TAB 4: WASTE SEPARATION LOGGING */}
              {activeWorkflowTab === 'waste' && (
                <div className="space-y-4 pt-2">
                  <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 flex items-start gap-2">
                    <Scale className="w-4 h-4 text-emerald-700 flex-shrink-0 mt-0.5" />
                    <div>
                      <strong>Independent Waste Separation (Phase 6 Design Baseline):</strong> Unserved kitchen surplus (pans
                      left in kitchen) and customer plate waste (scraped from trays) are measured independently on kitchen scales.
                      Do not force an exact mass-balance equation.
                    </div>
                  </div>

                  {serviceDetails.menu_entries.map((entry) => {
                    const f = wasteForm[entry.menu_entry_id] || {
                      unserved_surplus_weight_kg: entry.total_unserved_surplus_kg || 1.25,
                      plate_waste_weight_kg: entry.total_plate_waste_kg || 0.75,
                      disposal_destination: 'Compost',
                      logged_by: 'steward_rob',
                    };

                    return (
                      <Card key={entry.menu_entry_id} className="p-4">
                        <div className="flex items-center justify-between mb-3 border-b border-[#E3E8E1] pb-2">
                          <div>
                            <h4 className="text-sm font-bold text-[#24312B]">{entry.item_name}</h4>
                            <span className="text-xs text-neutral-500">
                              Logged Surplus: <strong>{entry.total_unserved_surplus_kg} kg</strong> · Logged Plate Waste:{' '}
                              <strong>{entry.total_plate_waste_kg} kg</strong>
                            </span>
                          </div>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-600">
                            Scale ID: Kitchen-Scale-01
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Unserved Surplus (kg)</label>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={f.unserved_surplus_weight_kg}
                              onChange={(e) =>
                                setWasteForm({
                                  ...wasteForm,
                                  [entry.menu_entry_id]: { ...f, unserved_surplus_weight_kg: parseFloat(e.target.value) || 0 },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Plate Waste (kg)</label>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={f.plate_waste_weight_kg}
                              onChange={(e) =>
                                setWasteForm({
                                  ...wasteForm,
                                  [entry.menu_entry_id]: { ...f, plate_waste_weight_kg: parseFloat(e.target.value) || 0 },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Disposal Stream</label>
                            <select
                              value={f.disposal_destination}
                              onChange={(e) =>
                                setWasteForm({
                                  ...wasteForm,
                                  [entry.menu_entry_id]: { ...f, disposal_destination: e.target.value },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            >
                              <option value="Compost">Compost</option>
                              <option value="Donation">Charity Food Donation</option>
                              <option value="Anaerobic_Digestion">Anaerobic Digester</option>
                              <option value="Landfill">Landfill</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-[11px] font-medium text-neutral-700 block mb-1">Logged By</label>
                            <input
                              type="text"
                              value={f.logged_by}
                              onChange={(e) =>
                                setWasteForm({
                                  ...wasteForm,
                                  [entry.menu_entry_id]: { ...f, logged_by: e.target.value },
                                })
                              }
                              className="w-full text-xs p-2 rounded-lg border border-[#E3E8E1]"
                            />
                          </div>
                          <div className="flex items-end">
                            <Button
                              size="sm"
                              className="w-full"
                              onClick={() =>
                                wasteMutation.mutate({
                                  menuEntryId: entry.menu_entry_id,
                                  payload: f,
                                })
                              }
                            >
                              Record Waste
                            </Button>
                          </div>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}

              {/* TAB 5: AUDIT TRAIL & COMPLETENESS */}
              {activeWorkflowTab === 'audit' && (
                <div className="space-y-4 pt-2">
                  <Card className="p-5">
                    <CardHeader className="p-0 mb-3">
                      <CardTitle className="text-sm font-bold text-[#24312B]">Service Validation Summary</CardTitle>
                      <CardDescription className="text-xs text-[#737D76]">
                        Audit verification against Phase 6 completeness checklist.
                      </CardDescription>
                    </CardHeader>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                      <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                        <span className="text-[11px] text-neutral-500 block">Pre-Service Headcount</span>
                        <span className="text-sm font-bold text-[#24312B]">
                          {serviceDetails.observations.length > 0 ? 'Recorded ✓' : 'Missing ✗'}
                        </span>
                      </div>
                      <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                        <span className="text-[11px] text-neutral-500 block">Menu Items</span>
                        <span className="text-sm font-bold text-[#24312B]">
                          {serviceDetails.menu_entries.length} scheduled
                        </span>
                      </div>
                      <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                        <span className="text-[11px] text-neutral-500 block">POS Portions Reconciled</span>
                        <span className="text-sm font-bold text-[#24312B]">
                          {serviceDetails.menu_entries.filter((m) => m.service_records.length > 0).length}/
                          {serviceDetails.menu_entries.length} dishes
                        </span>
                      </div>
                      <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                        <span className="text-[11px] text-neutral-500 block">Separated Waste Weighed</span>
                        <span className="text-sm font-bold text-[#24312B]">
                          {serviceDetails.menu_entries.filter((m) => m.waste_records.length > 0).length}/
                          {serviceDetails.menu_entries.length} dishes
                        </span>
                      </div>
                    </div>

                    <div className="p-3 rounded-xl bg-neutral-50 border border-[#E3E8E1] text-xs text-neutral-600">
                      <strong>Audit Policy:</strong> All creation and modification events are recorded immutably in
                      <code className="text-[#245C46] font-mono ml-1">pilot_audit_logs</code>. Prior measurements are superseded, never silently overwritten.
                    </div>
                  </Card>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* MODAL 1: SCHEDULE NEW SERVICE */}
      {showNewServiceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-xl border border-[#E3E8E1] space-y-4">
            <h3 className="text-base font-bold text-[#24312B]">Schedule New Meal Service</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-neutral-700 block mb-1">Service Date</label>
                <input
                  type="date"
                  value={newServiceForm.service_date}
                  onChange={(e) => setNewServiceForm({ ...newServiceForm, service_date: e.target.value })}
                  className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-neutral-700 block mb-1">Meal Period</label>
                  <select
                    value={newServiceForm.meal_period}
                    onChange={(e) => setNewServiceForm({ ...newServiceForm, meal_period: e.target.value })}
                    className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                  >
                    <option value="Lunch">Lunch</option>
                    <option value="Dinner">Dinner</option>
                    <option value="Breakfast">Breakfast</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-neutral-700 block mb-1">Canteen Section</label>
                  <select
                    value={newServiceForm.canteen_section}
                    onChange={(e) => setNewServiceForm({ ...newServiceForm, canteen_section: e.target.value })}
                    className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                  >
                    <option value="A">Section A (Pilot)</option>
                    <option value="B">Section B</option>
                    <option value="C">Section C</option>
                    <option value="D">Section D</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-neutral-700 block mb-1">Notes / Service Conditions</label>
                <input
                  type="text"
                  placeholder="e.g. Regular semester week, normal kitchen staffing"
                  value={newServiceForm.notes}
                  onChange={(e) => setNewServiceForm({ ...newServiceForm, notes: e.target.value })}
                  className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-[#E3E8E1]">
              <Button variant="outline" size="sm" onClick={() => setShowNewServiceModal(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => createServiceMutation.mutate(newServiceForm)}
              >
                Create Service
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: REGISTER NEW DISH RECIPE */}
      {showNewDishModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-xl border border-[#E3E8E1] space-y-4">
            <h3 className="text-base font-bold text-[#24312B]">Register Dish Recipe</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-neutral-700 block mb-1">Dish ID</label>
                <input
                  type="text"
                  placeholder="dish_herb_chicken"
                  value={newDishForm.item_id}
                  onChange={(e) => setNewDishForm({ ...newDishForm, item_id: e.target.value })}
                  className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-neutral-700 block mb-1">Dish Name</label>
                <input
                  type="text"
                  placeholder="Herb Roasted Chicken"
                  value={newDishForm.item_name}
                  onChange={(e) => setNewDishForm({ ...newDishForm, item_name: e.target.value })}
                  className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-neutral-700 block mb-1">Food Category</label>
                  <select
                    value={newDishForm.food_category}
                    onChange={(e) => setNewDishForm({ ...newDishForm, food_category: e.target.value })}
                    className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                  >
                    <option value="Meat">Meat</option>
                    <option value="Rice">Rice</option>
                    <option value="Soup">Soup</option>
                    <option value="Vegetables">Vegetables</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-neutral-700 block mb-1">Std Portion (grams)</label>
                  <input
                    type="number"
                    min="10"
                    value={newDishForm.standard_portion_grams}
                    onChange={(e) => setNewDishForm({ ...newDishForm, standard_portion_grams: parseFloat(e.target.value) || 100 })}
                    className="w-full text-xs p-2.5 rounded-lg border border-[#E3E8E1]"
                  />
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-[#E3E8E1]">
              <Button variant="outline" size="sm" onClick={() => setShowNewDishModal(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => createDishMutation.mutate(newDishForm)}
              >
                Save Recipe
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: POS CSV IMPORT */}
      {showPOSModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl p-6 max-w-xl w-full shadow-xl border border-[#E3E8E1] space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-[#24312B] flex items-center gap-2">
                <UploadCloud className="w-5 h-5 text-blue-600" />
                Import POS Register Transactions
              </h3>
              <button
                onClick={() => setShowPOSModal(false)}
                className="text-neutral-400 hover:text-neutral-600 text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-[#737D76]">
              Paste daily register export CSV. The validator checks headers, non-negativity, prevents duplicate imports,
              and reconciles against recorded meal services.
            </p>

            <div>
              <label className="text-xs font-medium text-neutral-700 block mb-1">CSV Data Payload</label>
              <textarea
                rows={7}
                value={posCsvText}
                onChange={(e) => setPosCsvText(e.target.value)}
                className="w-full text-xs font-mono p-3 rounded-xl border border-[#E3E8E1] bg-neutral-50"
              />
            </div>

            {posImportResult && (
              <div
                className={`p-3 rounded-xl border text-xs ${
                  posImportResult.success
                    ? 'bg-emerald-50 text-emerald-900 border-emerald-200'
                    : 'bg-red-50 text-red-900 border-red-200'
                }`}
              >
                <div className="font-semibold mb-1">
                  Import Summary: {posImportResult.imported_count} imported, {posImportResult.skipped_count} skipped (idempotent).
                </div>
                {posImportResult.errors.length > 0 && (
                  <ul className="list-disc list-inside space-y-0.5 text-red-700">
                    {posImportResult.errors.map((e, idx) => (
                      <li key={idx}>{e}</li>
                    ))}
                  </ul>
                )}
                {posImportResult.warnings.length > 0 && (
                  <ul className="list-disc list-inside space-y-0.5 text-amber-700">
                    {posImportResult.warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="flex justify-between items-center pt-2 border-t border-[#E3E8E1]">
              <button
                onClick={() => {
                  setPosCsvText(
                    `service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred\n${new Date().toISOString().split('T')[0]},Lunch,A,Herb Roasted Chicken,85,425.0,0\n`
                  );
                }}
                className="text-xs text-[#245C46] underline"
              >
                Insert sample row
              </button>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowPOSModal(false)}>
                  Close
                </Button>
                <Button
                  size="sm"
                  onClick={() => posImportMutation.mutate(posCsvText)}
                >
                  Validate & Ingest
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: PILOT QUALITY & READINESS REPORT */}
      {showQualityModal && qualityReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl p-6 max-w-2xl w-full shadow-xl border border-[#E3E8E1] space-y-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-[#24312B] flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-[#245C46]" />
                  Pilot Data Quality & Phase 6 Readiness Gates
                </h3>
                <p className="text-xs text-[#737D76]">
                  Target Scope: Section {qualityReport.pilot_section} · {qualityReport.pilot_meal_period} (40 consecutive weekday services)
                </p>
              </div>
              <button
                onClick={() => setShowQualityModal(false)}
                className="text-neutral-400 hover:text-neutral-600 text-sm"
              >
                ✕
              </button>
            </div>

            {/* Compliance Gauges */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                <span className="text-[11px] text-neutral-500 block">Total Services</span>
                <span className="text-lg font-bold text-[#24312B]">{qualityReport.total_services_recorded} / 40</span>
              </div>
              <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                <span className="text-[11px] text-neutral-500 block">Complete Records</span>
                <span className="text-lg font-bold text-[#24312B]">{qualityReport.complete_services_count}</span>
              </div>
              <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                <span className="text-[11px] text-neutral-500 block">Logging Compliance</span>
                <span className="text-lg font-bold text-[#245C46]">
                  {(qualityReport.compliance_rate * 100).toFixed(1)}%
                </span>
              </div>
              <div className="p-3 bg-neutral-50 rounded-xl border border-[#E3E8E1]">
                <span className="text-[11px] text-neutral-500 block">Missing POS</span>
                <span className="text-lg font-bold text-neutral-800">{qualityReport.services_missing_pos_service}</span>
              </div>
            </div>

            {/* Readiness Gates Table */}
            <div>
              <h4 className="text-xs font-bold text-[#24312B] uppercase tracking-wider mb-2">
                Phase 6 Readiness Gates Evaluation
              </h4>
              <div className="space-y-2">
                {qualityReport.readiness_gates.map((g) => {
                  const badgeColor =
                    g.status === 'MET'
                      ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                      : g.status === 'BLOCKED'
                      ? 'bg-amber-100 text-amber-800 border-amber-200'
                      : g.status === 'NOT_STARTED'
                      ? 'bg-neutral-100 text-neutral-700 border-neutral-200'
                      : 'bg-red-100 text-red-800 border-red-200';

                  return (
                    <div
                      key={g.gate_id}
                      className="p-3 rounded-xl border border-[#E3E8E1] flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="font-semibold text-[#24312B] flex items-center gap-2">
                          <span>{g.name}</span>
                          <span className="font-mono text-[10px] text-neutral-400">({g.gate_id})</span>
                        </div>
                        <div className="text-[11px] text-neutral-500 mt-0.5">{g.details}</div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-[11px] text-neutral-600">
                          {g.current_value} / {g.required_value}
                        </span>
                        <span className={`px-2 py-0.5 rounded-full font-bold text-[10px] border ${badgeColor}`}>
                          {g.status}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Holdout Policy Notice */}
            <div className="p-3 bg-neutral-50 border border-[#E3E8E1] rounded-xl text-xs text-neutral-700">
              <strong className="text-[#24312B] block mb-0.5">Chronological Holdout Policy:</strong>
              {qualityReport.holdout_policy.policy_rule}
              <div className="text-[11px] text-neutral-500 mt-1">
                Historical Holdout: {qualityReport.holdout_policy.historical_holdout_status}
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t border-[#E3E8E1]">
              <Button size="sm" onClick={() => setShowQualityModal(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default PilotDataCapturePage;
