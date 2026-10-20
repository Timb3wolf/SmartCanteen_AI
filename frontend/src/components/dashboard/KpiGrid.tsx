import { Trash2, Scale, DollarSign, Database, Utensils } from 'lucide-react';
import { AnalyticsSummary } from '../../types';
import { Card } from '../ui/Card';
import { Skeleton } from '../ui/Skeleton';
import { formatCurrency, formatKg } from '../../lib/utils';

interface KpiGridProps {
  summary?: AnalyticsSummary;
  isLoading?: boolean;
}

export function KpiGrid({ summary, isLoading }: KpiGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {[...Array(5)].map((_, i) => (
          <Card key={i} className="p-4">
            <Skeleton className="w-8 h-8 rounded-lg mb-3" />
            <Skeleton className="w-16 h-3 mb-2" />
            <Skeleton className="w-24 h-6" />
          </Card>
        ))}
      </div>
    );
  }

  const kpis = [
    {
      title: 'Total Food Waste',
      value: formatKg(summary?.total_waste_kg),
      subtext: 'Cumulative discarded volume',
      icon: Trash2,
      color: 'text-[#245C46] bg-[#245C46]/10',
    },
    {
      title: 'Avg Waste / Record',
      value: formatKg(summary?.avg_waste_per_record_kg),
      subtext: 'Per dish serving event',
      icon: Scale,
      color: 'text-[#A8BFA5] bg-[#A8BFA5]/20',
    },
    {
      title: 'Total Financial Loss',
      value: formatCurrency(summary?.total_financial_loss),
      subtext: 'Calculated (waste × price)',
      icon: DollarSign,
      color: 'text-[#D97706] bg-[#FFFBEB]',
    },
    {
      title: 'Analyzed Records',
      value: summary?.record_count?.toLocaleString() || '0',
      subtext: 'Matching operational events',
      icon: Database,
      color: 'text-[#737D76] bg-[#F0F3ED]',
    },
    {
      title: 'Avg Waste / Service',
      value: formatKg(summary?.avg_waste_per_service_kg),
      subtext: 'Combined meal session waste',
      icon: Utensils,
      color: 'text-[#245C46] bg-[#EBF1EA]',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {kpis.map((kpi) => {
        const Icon = kpi.icon;
        return (
          <Card key={kpi.title} className="p-4 relative overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-[#737D76]">{kpi.title}</span>
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${kpi.color}`}>
                <Icon className="w-4 h-4" />
              </div>
            </div>
            <div className="text-xl font-bold text-[#24312B] tracking-tight">{kpi.value}</div>
            <div className="text-[11px] text-[#A0AAA2] mt-1">{kpi.subtext}</div>
          </Card>
        );
      })}
    </div>
  );
}
