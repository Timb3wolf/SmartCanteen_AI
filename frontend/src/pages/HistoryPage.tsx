import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { History, Trash2, Filter, Sparkles, AlertTriangle, ArrowUpDown } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { RiskBadge } from '../components/ui/RiskBadge';
import { clearPredictionHistory, fetchPredictionHistory } from '../services/api';
import { formatCurrency, formatDate, formatKg } from '../lib/utils';

export function HistoryPage() {
  const queryClient = useQueryClient();
  const [selectedRisk, setSelectedRisk] = useState<string>('All');
  const [selectedMeal, setSelectedMeal] = useState<string>('All');
  const [showClearConfirm, setShowClearConfirm] = useState<boolean>(false);

  const { data: historyData, isLoading } = useQuery({
    queryKey: ['prediction-history'],
    queryFn: () => fetchPredictionHistory(100),
  });

  const clearMutation = useMutation({
    mutationFn: clearPredictionHistory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prediction-history'] });
      setShowClearConfirm(false);
    },
  });

  const predictions = historyData?.predictions || [];

  // Filter in-memory for quick responsiveness
  const filteredPredictions = predictions.filter((p) => {
    if (selectedRisk !== 'All' && p.predicted_risk.toLowerCase() !== selectedRisk.toLowerCase()) {
      return false;
    }
    if (selectedMeal !== 'All' && p.meal.toLowerCase() !== selectedMeal.toLowerCase()) {
      return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-[#E3E8E1] p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#EBF1EA] text-[#245C46]">
              Persistent SQLite Storage
            </span>
            <span className="text-xs text-[#737D76]">{predictions.length} Total Saved Predictions</span>
          </div>
          <h1 className="text-2xl font-bold text-[#24312B] tracking-tight">Prediction Audit History</h1>
          <p className="text-xs text-[#737D76] max-w-2xl mt-1">
            Review previous model simulations, compare predicted waste quantities, track financial loss estimates,
            and audit risk distribution across service requests.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {predictions.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowClearConfirm(true)}
              className="text-[#C65353] hover:border-[#C65353]/30"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1" />
              <span>Clear History</span>
            </Button>
          )}

          <Link to="/predict">
            <Button variant="primary" size="sm">
              <Sparkles className="w-3.5 h-3.5 mr-1.5 text-[#E6B566]" />
              <span>New Prediction</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Confirmation Modal */}
      {showClearConfirm && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-[#E3E8E1] space-y-4">
            <div className="w-12 h-12 rounded-full bg-[#FFF1F2] text-[#E11D48] flex items-center justify-center mx-auto">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div className="text-center">
              <h3 className="text-base font-bold text-[#24312B]">Clear All Prediction History?</h3>
              <p className="text-xs text-[#737D76] mt-1.5">
                This will permanently delete all {predictions.length} recorded predictions from the SQLite database.
                This action cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowClearConfirm(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => clearMutation.mutate()}
                isLoading={clearMutation.isPending}
              >
                Yes, Clear Database
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      {predictions.length > 0 && (
        <div className="bg-white rounded-xl border border-[#E3E8E1] p-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-[#737D76]" />
            <span className="text-xs font-semibold text-[#24312B]">Filter History:</span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Risk Filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-[#737D76]">Risk:</span>
              <div className="flex items-center gap-1">
                {['All', 'Low', 'Medium', 'High'].map((risk) => (
                  <button
                    key={risk}
                    onClick={() => setSelectedRisk(risk)}
                    className={`text-xs px-2.5 py-1 rounded-md font-medium border transition-colors cursor-pointer ${
                      selectedRisk.toLowerCase() === risk.toLowerCase()
                        ? 'bg-[#245C46] text-white border-[#245C46]'
                        : 'bg-[#F7F8F4] text-[#737D76] border-[#E3E8E1] hover:border-[#CBD5C8]'
                    }`}
                  >
                    {risk}
                  </button>
                ))}
              </div>
            </div>

            {/* Meal Filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-[#737D76]">Meal:</span>
              <div className="flex items-center gap-1">
                {['All', 'Breakfast', 'Lunch', 'Dinner'].map((meal) => (
                  <button
                    key={meal}
                    onClick={() => setSelectedMeal(meal)}
                    className={`text-xs px-2.5 py-1 rounded-md font-medium border transition-colors cursor-pointer ${
                      selectedMeal.toLowerCase() === meal.toLowerCase()
                        ? 'bg-[#245C46] text-white border-[#245C46]'
                        : 'bg-[#F7F8F4] text-[#737D76] border-[#E3E8E1] hover:border-[#CBD5C8]'
                    }`}
                  >
                    {meal}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History Table Card */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Historical Log Entries ({filteredPredictions.length})</CardTitle>
            <CardDescription>
              Sorted by most recent prediction execution timestamp
            </CardDescription>
          </div>
        </CardHeader>

        {isLoading ? (
          <div className="py-12 text-center text-xs text-[#737D76]">Loading prediction history...</div>
        ) : filteredPredictions.length === 0 ? (
          <div className="py-16 text-center text-[#737D76]">
            <div className="w-12 h-12 rounded-full bg-[#F0F3ED] flex items-center justify-center mx-auto mb-3 text-[#245C46]">
              <History className="w-6 h-6 text-[#A8BFA5]" />
            </div>
            <h4 className="text-sm font-semibold text-[#24312B] mb-1">
              {predictions.length === 0 ? 'No Predictions Recorded' : 'No Matching Predictions'}
            </h4>
            <p className="text-xs text-[#737D76] max-w-sm mx-auto mb-4">
              {predictions.length === 0
                ? 'Run your first machine learning simulation in the sandbox to start logging predictions.'
                : 'Try clearing your risk or meal filters to view all recorded predictions.'}
            </p>
            {predictions.length === 0 && (
              <Link to="/predict">
                <Button variant="primary" size="sm">
                  <Sparkles className="w-3.5 h-3.5 mr-1 text-[#E6B566]" />
                  <span>Go to Prediction Sandbox</span>
                </Button>
              </Link>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#F7F8F4] border-y border-[#E3E8E1] text-[#737D76]">
                  <th className="py-2.5 px-4 font-semibold">Logged At</th>
                  <th className="py-2.5 px-4 font-semibold">Service Date</th>
                  <th className="py-2.5 px-4 font-semibold">Meal</th>
                  <th className="py-2.5 px-4 font-semibold">Section</th>
                  <th className="py-2.5 px-4 font-semibold">Food Category</th>
                  <th className="py-2.5 px-4 font-semibold">Unit Price</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Predicted Waste</th>
                  <th className="py-2.5 px-4 font-semibold text-center">Risk Level</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Estimated Loss</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F0F3ED]">
                {filteredPredictions.map((row) => (
                  <tr key={row.id} className="hover:bg-[#F7F8F4]/80 transition-colors">
                    <td className="py-3 px-4 text-[#737D76]">
                      {row.created_at ? new Date(row.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    <td className="py-3 px-4 font-medium text-[#24312B]">{formatDate(row.prediction_date)}</td>
                    <td className="py-3 px-4">{row.meal}</td>
                    <td className="py-3 px-4">Section {row.canteen_section}</td>
                    <td className="py-3 px-4">{row.food_category}</td>
                    <td className="py-3 px-4">{formatCurrency(row.unit_price_per_kg)}/kg</td>
                    <td className="py-3 px-4 font-bold text-[#245C46] text-right">
                      {formatKg(row.predicted_waste_kg)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <RiskBadge risk={row.predicted_risk} size="sm" />
                    </td>
                    <td className="py-3 px-4 font-semibold text-[#D97706] text-right">
                      {formatCurrency(row.estimated_financial_loss)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
