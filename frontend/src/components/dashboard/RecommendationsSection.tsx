import { Lightbulb, AlertTriangle, ShieldAlert, CheckCircle2, ArrowRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '../ui/Card';
import { Skeleton } from '../ui/Skeleton';
import { Recommendation } from '../../types';

interface RecommendationsSectionProps {
  recommendations?: Recommendation[];
  isLoading?: boolean;
}

export function RecommendationsSection({ recommendations, isLoading }: RecommendationsSectionProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="w-48 h-5" />
        </CardHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      </Card>
    );
  }

  if (!recommendations || recommendations.length === 0) {
    return null;
  }

  const getTypeStyles = (type: string) => {
    switch (type) {
      case 'danger':
        return {
          card: 'bg-[#FFF1F2]/60 border-[#FECDD3]',
          badge: 'bg-[#FFE4E6] text-[#E11D48]',
          icon: ShieldAlert,
          iconColor: 'text-[#E11D48]',
        };
      case 'warning':
        return {
          card: 'bg-[#FFFBEB]/60 border-[#FDE68A]',
          badge: 'bg-[#FEF3C7] text-[#D97706]',
          icon: AlertTriangle,
          iconColor: 'text-[#D97706]',
        };
      case 'success':
        return {
          card: 'bg-[#ECFDF5]/60 border-[#A7F3D0]',
          badge: 'bg-[#D1FAE5] text-[#059669]',
          icon: CheckCircle2,
          iconColor: 'text-[#059669]',
        };
      case 'info':
      default:
        return {
          card: 'bg-[#F7F8F4] border-[#E3E8E1]',
          badge: 'bg-[#EBF1EA] text-[#245C46]',
          icon: Lightbulb,
          iconColor: 'text-[#245C46]',
        };
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
            <Lightbulb className="w-4 h-4 text-[#E6B566]" />
          </div>
          <div>
            <CardTitle>Data-Driven Operational Recommendations</CardTitle>
            <CardDescription>
              Actionable insights dynamically derived from current filter calculations
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {recommendations.map((rec) => {
          const style = getTypeStyles(rec.type);
          const Icon = style.icon;

          return (
            <div
              key={rec.id}
              className={`p-4 rounded-xl border flex flex-col justify-between transition-all hover:shadow-xs ${style.card}`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <Icon className={`w-4 h-4 ${style.iconColor}`} />
                    <span className="text-xs font-semibold text-[#24312B]">{rec.title}</span>
                  </div>
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${style.badge}`}>
                    {rec.category}
                  </span>
                </div>

                <p className="text-xs text-[#737D76] leading-relaxed mb-3">{rec.description}</p>
              </div>

              <div className="pt-2.5 border-t border-black/5 flex items-start gap-1.5 text-xs font-medium text-[#24312B]">
                <ArrowRight className="w-3.5 h-3.5 text-[#245C46] mt-0.5 shrink-0" />
                <span>{rec.action_item}</span>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
