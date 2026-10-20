import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  BrainCircuit,
  Sparkles,
  Calendar,
  Utensils,
  Store,
  DollarSign,
  Layers,
  History,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { RiskBadge } from '../components/ui/RiskBadge';
import { fetchMetadata, fetchPredictionHistory, predictWaste } from '../services/api';
import { PredictionRequest, PredictionResult } from '../types';
import { formatCurrency, formatKg } from '../lib/utils';

export function PredictPage() {
  const queryClient = useQueryClient();

  // Fetch metadata for default values and options
  const { data: metadata } = useQuery({
    queryKey: ['metadata'],
    queryFn: fetchMetadata,
  });

  // Fetch recent history
  const { data: historyData } = useQuery({
    queryKey: ['prediction-history'],
    queryFn: () => fetchPredictionHistory(5),
  });

  const [date, setDate] = useState<string>(() => {
    return new Date().toISOString().split('T')[0];
  });
  const [meal, setMeal] = useState<string>('Lunch');
  const [section, setSection] = useState<string>('B');
  const [category, setCategory] = useState<string>('Rice');
  const [price, setPrice] = useState<number>(4.5);

  const [lastResult, setLastResult] = useState<PredictionResult | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const predictMutation = useMutation({
    mutationFn: (payload: PredictionRequest) => predictWaste(payload),
    onSuccess: (result) => {
      setLastResult(result);
      setFormError(null);
      // Invalidate history query so new prediction immediately shows up
      queryClient.invalidateQueries({ queryKey: ['prediction-history'] });
    },
    onError: (err: any) => {
      setFormError(err.message || 'Prediction failed. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!date) {
      setFormError('Please select a valid service date.');
      return;
    }
    if (price <= 0 || price > 50) {
      setFormError('Unit price per kg must be between $0.10 and $50.00.');
      return;
    }

    predictMutation.mutate({
      date,
      meal,
      canteen_section: section,
      food_category: category,
      unit_price_per_kg: Number(price),
    });
  };

  const meals = metadata?.meals || ['Breakfast', 'Lunch', 'Dinner'];
  const sections = metadata?.canteen_sections || ['A', 'B', 'C', 'D'];
  const categories = metadata?.food_categories || ['Meat', 'Rice', 'Soup', 'Vegetables'];

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-[#E3E8E1] p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#EBF1EA] text-[#245C46]">
              Machine Learning Inference
            </span>
          </div>
          <h1 className="text-2xl font-bold text-[#24312B] tracking-tight">AI Food Waste Prediction Sandbox</h1>
          <p className="text-xs text-[#737D76] max-w-2xl mt-1">
            Simulate future meal services using our trained dual Random Forest models. Estimate food waste quantity (kg),
            classify operational risk, and quantify anticipated monetary loss.
          </p>
        </div>

        <Link to="/history">
          <Button variant="outline" size="sm" className="gap-1.5 shrink-0">
            <History className="w-3.5 h-3.5" />
            <span>View Full History</span>
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Prediction Form (7 columns) */}
        <div className="lg:col-span-7">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
                  <BrainCircuit className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle>Inference Parameters</CardTitle>
                  <CardDescription>Enter dish and scheduling details for model inference</CardDescription>
                </div>
              </div>
            </CardHeader>

            <form onSubmit={handleSubmit} className="space-y-4">
              {formError && (
                <div className="p-3 rounded-lg bg-[#FFF1F2] border border-[#FECDD3] text-[#E11D48] text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              {/* Service Date */}
              <div>
                <label className="block text-xs font-medium text-[#24312B] mb-1 flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-[#737D76]" />
                  <span>Observation Date</span>
                </label>
                <input
                  type="date"
                  required
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="w-full text-sm bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-3 py-2 text-[#24312B] focus:outline-none focus:ring-2 focus:ring-[#245C46]/20 focus:border-[#245C46]"
                />
                <p className="text-[11px] text-[#737D76] mt-1">Calendar features (Year, Month, Day, DayOfWeek) are extracted automatically.</p>
              </div>

              {/* Meal & Section Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-[#24312B] mb-1 flex items-center gap-1.5">
                    <Utensils className="w-3.5 h-3.5 text-[#737D76]" />
                    <span>Meal Period</span>
                  </label>
                  <select
                    value={meal}
                    onChange={(e) => setMeal(e.target.value)}
                    className="w-full text-sm bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-3 py-2 text-[#24312B] focus:outline-none focus:ring-2 focus:ring-[#245C46]/20 focus:border-[#245C46]"
                  >
                    {meals.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-[#24312B] mb-1 flex items-center gap-1.5">
                    <Store className="w-3.5 h-3.5 text-[#737D76]" />
                    <span>Canteen Section</span>
                  </label>
                  <select
                    value={section}
                    onChange={(e) => setSection(e.target.value)}
                    className="w-full text-sm bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-3 py-2 text-[#24312B] focus:outline-none focus:ring-2 focus:ring-[#245C46]/20 focus:border-[#245C46]"
                  >
                    {sections.map((s) => (
                      <option key={s} value={s}>
                        Section {s}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Category & Unit Price Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-[#24312B] mb-1 flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-[#737D76]" />
                    <span>Food Category</span>
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full text-sm bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-3 py-2 text-[#24312B] focus:outline-none focus:ring-2 focus:ring-[#245C46]/20 focus:border-[#245C46]"
                  >
                    {categories.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-[#24312B] mb-1 flex items-center gap-1.5">
                    <DollarSign className="w-3.5 h-3.5 text-[#737D76]" />
                    <span>Unit Price ($ / kg)</span>
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="50.0"
                    required
                    value={price}
                    onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
                    className="w-full text-sm bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-3 py-2 text-[#24312B] focus:outline-none focus:ring-2 focus:ring-[#245C46]/20 focus:border-[#245C46]"
                  />
                </div>
              </div>

              <div className="pt-2">
                <Button
                  type="submit"
                  variant="primary"
                  className="w-full py-2.5"
                  isLoading={predictMutation.isPending}
                >
                  <Sparkles className="w-4 h-4 mr-1.5 text-[#E6B566]" />
                  <span>Execute Model Prediction</span>
                </Button>
              </div>
            </form>
          </Card>
        </div>

        {/* Prediction Results Card (5 columns) */}
        <div className="lg:col-span-5 space-y-4">
          <Card className="border-[#245C46]/20 relative overflow-hidden">
            <CardHeader>
              <div>
                <CardTitle>Inference Outcome</CardTitle>
                <CardDescription>Estimated waste, risk classification, and financial loss</CardDescription>
              </div>
            </CardHeader>

            {lastResult ? (
              <div className="space-y-5 animate-in fade-in duration-300">
                {/* Result Top Badges */}
                <div className="flex items-center justify-between">
                  <span className="text-xs text-[#737D76]">
                    {lastResult.meal} • Section {lastResult.canteen_section} • {lastResult.food_category}
                  </span>
                  <RiskBadge risk={lastResult.predicted_risk} size="md" />
                </div>

                {/* Primary Metric: Predicted Waste */}
                <div className="bg-[#F7F8F4] rounded-xl p-4 border border-[#E3E8E1] text-center">
                  <span className="text-xs font-medium text-[#737D76] uppercase tracking-wider">
                    Predicted Food Waste
                  </span>
                  <div className="text-3xl font-extrabold text-[#245C46] my-1">
                    {formatKg(lastResult.predicted_waste_kg)}
                  </div>
                  <span className="text-[11px] text-[#A0AAA2]">Random Forest Regressor output</span>
                </div>

                {/* Secondary Metrics */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg border border-[#E3E8E1] bg-white">
                    <span className="text-[11px] text-[#737D76] block mb-1">Financial Loss</span>
                    <span className="text-lg font-bold text-[#D97706]">
                      {formatCurrency(lastResult.estimated_financial_loss)}
                    </span>
                    <span className="text-[10px] text-[#A0AAA2] block mt-0.5">
                      {lastResult.predicted_waste_kg} kg × ${lastResult.unit_price_per_kg}
                    </span>
                  </div>

                  <div className="p-3 rounded-lg border border-[#E3E8E1] bg-white">
                    <span className="text-[11px] text-[#737D76] block mb-1">Assessed Risk</span>
                    <span className="text-lg font-bold text-[#24312B] capitalize">
                      {lastResult.predicted_risk} Risk
                    </span>
                    <span className="text-[10px] text-[#A0AAA2] block mt-0.5">Classifier prediction</span>
                  </div>
                </div>

                {/* Operational Guidance Disclaimer */}
                <div className="p-3 rounded-lg bg-[#EBF1EA]/60 border border-[#CBD5C8] text-[11px] text-[#24312B] flex items-start gap-2">
                  <Info className="w-4 h-4 text-[#245C46] shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block mb-0.5">Operational Guidance</span>
                    This prediction is automatically saved to your history log. Test set evaluation: MAE 1.32 kg, Accuracy 35.4%. Use estimates as directional indicators alongside kitchen audits.
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-[#737D76]">
                <div className="w-12 h-12 rounded-full bg-[#F0F3ED] flex items-center justify-center mx-auto mb-3 text-[#245C46]">
                  <Sparkles className="w-6 h-6 text-[#A8BFA5]" />
                </div>
                <h4 className="text-sm font-semibold text-[#24312B] mb-1">Awaiting Prediction</h4>
                <p className="text-xs text-[#737D76] max-w-xs mx-auto">
                  Adjust the form parameters on the left and click "Execute Model Prediction" to generate real-time estimates.
                </p>
              </div>
            )}
          </Card>

          {/* Quick Recent Predictions Snippet */}
          {historyData && historyData.predictions.length > 0 && (
            <Card>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold text-[#24312B]">Recent Session Predictions</span>
                <Link to="/history" className="text-xs text-[#245C46] font-medium hover:underline">
                  View all ({historyData.total})
                </Link>
              </div>
              <div className="space-y-2">
                {historyData.predictions.slice(0, 3).map((item) => (
                  <div
                    key={item.id}
                    className="p-2.5 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1] flex items-center justify-between text-xs"
                  >
                    <div>
                      <span className="font-medium text-[#24312B]">
                        {item.meal} ({item.food_category})
                      </span>
                      <span className="text-[11px] text-[#737D76] block">Section {item.canteen_section}</span>
                    </div>
                    <div className="text-right">
                      <span className="font-bold text-[#245C46]">{formatKg(item.predicted_waste_kg)}</span>
                      <div className="mt-0.5">
                        <RiskBadge risk={item.predicted_risk} size="sm" showIcon={false} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
