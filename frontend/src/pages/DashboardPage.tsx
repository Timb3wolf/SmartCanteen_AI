import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Sparkles, ArrowRight, RefreshCw, AlertCircle } from 'lucide-react';
import { FilterBar } from '../components/dashboard/FilterBar';
import { KpiGrid } from '../components/dashboard/KpiGrid';
import { ChartsSection } from '../components/dashboard/ChartsSection';
import { RecommendationsSection } from '../components/dashboard/RecommendationsSection';
import { Button } from '../components/ui/Button';
import {
  fetchAnalyticsDistribution,
  fetchAnalyticsRecommendations,
  fetchAnalyticsSummary,
  fetchMetadata,
} from '../services/api';
import { FilterState } from '../types';

export function DashboardPage() {
  const [filters, setFilters] = useState<FilterState>({
    startDate: undefined,
    endDate: undefined,
    meals: [],
    sections: [],
    categories: [],
  });

  // Query metadata for filter options
  const { data: metadata } = useQuery({
    queryKey: ['metadata'],
    queryFn: fetchMetadata,
    staleTime: 1000 * 60 * 10,
  });

  // Query summary KPIs
  const {
    data: summary,
    isLoading: isLoadingSummary,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['analytics-summary', filters],
    queryFn: () => fetchAnalyticsSummary(filters),
  });

  // Query chart distributions
  const {
    data: distribution,
    isLoading: isLoadingDistribution,
    refetch: refetchDistribution,
  } = useQuery({
    queryKey: ['analytics-distribution', filters],
    queryFn: () => fetchAnalyticsDistribution(filters),
  });

  // Query dynamic recommendations
  const {
    data: recommendationsData,
    isLoading: isLoadingRecs,
    refetch: refetchRecs,
  } = useQuery({
    queryKey: ['analytics-recommendations', filters],
    queryFn: () => fetchAnalyticsRecommendations(filters),
  });

  const handleResetFilters = () => {
    setFilters({
      startDate: undefined,
      endDate: undefined,
      meals: [],
      sections: [],
      categories: [],
    });
  };

  const handleRefreshAll = () => {
    refetchSummary();
    refetchDistribution();
    refetchRecs();
  };

  return (
    <div className="space-y-6">
      {/* Top Welcome / Header Banner */}
      <div className="bg-white rounded-2xl border border-[#E3E8E1] p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#EBF1EA] text-[#245C46]">
              Operational Intelligence
            </span>
            <span className="text-xs text-[#737D76]">Historical Log: Jun 11 – Aug 10, 2025</span>
          </div>
          <h1 className="text-2xl font-bold text-[#24312B] tracking-tight">Food Waste & Loss Analytics</h1>
          <p className="text-xs text-[#737D76] max-w-2xl mt-1">
            Real-time analytics and predictive intelligence designed to eliminate university canteen food surplus,
            cut financial losses, and support proactive menu planning.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <Button variant="outline" size="sm" onClick={handleRefreshAll} title="Refresh Analytics Data">
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>

          <Link to="/predict">
            <Button variant="primary" size="sm">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Predict Future Waste</span>
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </Link>
        </div>
      </div>

      {summaryError && (
        <div className="p-4 rounded-xl bg-[#FFF1F2] border border-[#FECDD3] text-[#E11D48] flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>Failed to load canteen analytics. Please ensure the backend server is running.</span>
          </div>
          <Button variant="outline" size="sm" onClick={handleRefreshAll}>
            Retry
          </Button>
        </div>
      )}

      {/* Filter Toolbar */}
      <FilterBar
        filters={filters}
        metadata={metadata}
        onChange={setFilters}
        onReset={handleResetFilters}
      />

      {/* Primary KPI Summary Cards */}
      <KpiGrid summary={summary} isLoading={isLoadingSummary} />

      {/* Dynamic Data-Driven Recommendations */}
      <RecommendationsSection
        recommendations={recommendationsData?.recommendations}
        isLoading={isLoadingRecs}
      />

      {/* Visual Analytics Grid */}
      <ChartsSection distribution={distribution} isLoading={isLoadingDistribution} />
    </div>
  );
}
