import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Layers,
  ShieldAlert,
  Info,
  TrendingDown,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { fetchModelMetrics } from '../services/api';

export function ModelsPage() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ['model-metrics'],
    queryFn: fetchModelMetrics,
  });

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-[#E3E8E1] p-6 shadow-xs">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#EBF1EA] text-[#245C46]">
            ML Governance & Transparency
          </span>
          <span className="text-xs text-[#737D76]">Scikit-Learn Random Forest Pipeline</span>
        </div>
        <h1 className="text-2xl font-bold text-[#24312B] tracking-tight">Machine Learning Model Insights</h1>
        <p className="text-xs text-[#737D76] max-w-3xl mt-1">
          SmartCanteen AI uses two distinct Random Forest models trained on 2,600 historical canteen records.
          In accordance with AI safety and production engineering standards, the exact test set evaluation metrics
          are reported transparently below.
        </p>
      </div>

      {/* Critical Limitation Banner */}
      <div className="p-4 rounded-xl bg-[#FFFBEB] border border-[#FDE68A] text-[#D97706] flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <p className="font-semibold text-[#B45309]">Important Operational Notice on Model Accuracy</p>
          <p className="text-[#92400E] leading-relaxed">
            The regression model achieves a negative test R² score (<strong>-0.128</strong>) and the multi-class classifier achieves
            approximately <strong>35.38%</strong> test accuracy. These baseline scores indicate that static date and meal features alone
            do not fully capture day-to-day attendance swings. Predictions should be used as operational estimates alongside kitchen logs.
          </p>
        </div>
      </div>

      {/* Model Cards: Regression & Classification */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Random Forest Regressor */}
        <Card className="flex flex-col justify-between">
          <div>
            <CardHeader>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
                  <TrendingDown className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle>Random Forest Regressor</CardTitle>
                  <CardDescription>Predicts waste quantity in kilograms (Waste_Weight_kg)</CardDescription>
                </div>
              </div>
            </CardHeader>

            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-3 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1]">
                  <span className="text-[11px] text-[#737D76] block mb-1">Mean Absolute Error</span>
                  <span className="text-lg font-bold text-[#24312B]">1.32 kg</span>
                  <span className="text-[10px] text-[#A0AAA2] block mt-0.5">MAE</span>
                </div>
                <div className="p-3 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1]">
                  <span className="text-[11px] text-[#737D76] block mb-1">Root Mean Squared Error</span>
                  <span className="text-lg font-bold text-[#24312B]">1.55 kg</span>
                  <span className="text-[10px] text-[#A0AAA2] block mt-0.5">RMSE</span>
                </div>
                <div className="p-3 rounded-lg bg-[#FFF1F2] border border-[#FECDD3]">
                  <span className="text-[11px] text-[#E11D48] block mb-1">R² Score</span>
                  <span className="text-lg font-bold text-[#E11D48]">-0.128</span>
                  <span className="text-[10px] text-[#E11D48]/70 block mt-0.5">Needs Tuning</span>
                </div>
              </div>

              <div className="text-xs text-[#737D76] space-y-2 pt-2 border-t border-[#F0F3ED]">
                <p>
                  <strong>What MAE & RMSE mean:</strong> On average, the model's waste prediction differs by approximately 1.32 kg from the actual scale weight recorded at the canteen.
                </p>
                <p>
                  <strong>Why R² is negative:</strong> In scikit-learn, a negative R² score indicates that the baseline regressor performs worse than simply predicting the mean waste value. Adding time-series lags and student attendance logs will improve this.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-[#F0F3ED] text-[11px] text-[#A0AAA2]">
            Checkpoint: <code>models/waste_regression_model.pkl</code> (~18.9 MB)
          </div>
        </Card>

        {/* Random Forest Classifier */}
        <Card className="flex flex-col justify-between">
          <div>
            <CardHeader>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle>Random Forest Classifier</CardTitle>
                  <CardDescription>Predicts waste risk tier: Low, Medium, or High</CardDescription>
                </div>
              </div>
            </CardHeader>

            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="p-2.5 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1]">
                  <span className="text-[10px] text-[#737D76] block mb-1">Accuracy</span>
                  <span className="text-base font-bold text-[#24312B]">35.38%</span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1]">
                  <span className="text-[10px] text-[#737D76] block mb-1">Precision</span>
                  <span className="text-base font-bold text-[#24312B]">35.47%</span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1]">
                  <span className="text-[10px] text-[#737D76] block mb-1">Recall</span>
                  <span className="text-base font-bold text-[#24312B]">35.38%</span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#F7F8F4] border border-[#E3E8E1]">
                  <span className="text-[10px] text-[#737D76] block mb-1">Macro F1</span>
                  <span className="text-base font-bold text-[#24312B]">35.42%</span>
                </div>
              </div>

              <div className="text-xs text-[#737D76] space-y-2 pt-2 border-t border-[#F0F3ED]">
                <p>
                  <strong>Balanced Class Context:</strong> The dataset has three balanced classes (Low: 869, Medium: 872, High: 859 records). A random guess has ~33.3% accuracy; the model currently achieves 35.38%.
                </p>
                <p>
                  <strong>Operational Interpretation:</strong> Risk outputs should be interpreted as directional probability indicators rather than definitive classifications.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-[#F0F3ED] text-[11px] text-[#A0AAA2]">
            Checkpoint: <code>models/waste_risk_classifier.pkl</code> (~17.6 MB)
          </div>
        </Card>
      </div>

      {/* Feature Engineering Architecture */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <CardTitle>Feature Engineering Pipeline (13 Features)</CardTitle>
              <CardDescription>Exact feature schema consumed by both models during inference</CardDescription>
            </div>
          </div>
        </CardHeader>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="p-3.5 rounded-xl bg-[#F7F8F4] border border-[#E3E8E1]">
            <h4 className="font-semibold text-[#24312B] mb-2 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#245C46]" />
              Numerical & Temporal
            </h4>
            <ul className="space-y-1.5 text-[#737D76]">
              <li><code>Unit_Price_per_kg</code> — Dish unit cost</li>
              <li><code>Year</code> — Calendar year</li>
              <li><code>Month</code> — Month of service (1-12)</li>
              <li><code>Day</code> — Day of month (1-31)</li>
              <li><code>DayOfWeek</code> — Weekday index (0=Mon, 6=Sun)</li>
            </ul>
          </div>

          <div className="p-3.5 rounded-xl bg-[#F7F8F4] border border-[#E3E8E1]">
            <h4 className="font-semibold text-[#24312B] mb-2 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#A8BFA5]" />
              One-Hot Categorical
            </h4>
            <ul className="space-y-1.5 text-[#737D76]">
              <li><code>Meal_Dinner</code></li>
              <li><code>Meal_Lunch</code></li>
              <li><code>Canteen_Section_B</code></li>
              <li><code>Canteen_Section_C</code></li>
              <li><code>Canteen_Section_D</code></li>
            </ul>
          </div>

          <div className="p-3.5 rounded-xl bg-[#F7F8F4] border border-[#E3E8E1]">
            <h4 className="font-semibold text-[#24312B] mb-2 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#E6B566]" />
              Food Categories & Baseline
            </h4>
            <ul className="space-y-1.5 text-[#737D76]">
              <li><code>Food_Category_Rice</code></li>
              <li><code>Food_Category_Soup</code></li>
              <li><code>Food_Category_Vegetables</code></li>
              <li className="text-[#A0AAA2] italic pt-1 border-t border-[#E3E8E1]">
                Baseline (dropped): Breakfast, Section A, Meat
              </li>
            </ul>
          </div>
        </div>
      </Card>

      {/* Recommended Model Improvements */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
              <CheckCircle2 className="w-4 h-4 text-[#059669]" />
            </div>
            <div>
              <CardTitle>Roadmap for Future ML Accuracy Improvements</CardTitle>
              <CardDescription>Concrete recommendations to enhance predictive performance</CardDescription>
            </div>
          </div>
        </CardHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="p-3.5 rounded-xl border border-[#E3E8E1] bg-white">
            <h4 className="font-semibold text-[#24312B] mb-1">1. Temporal Lag Features & Rolling Means</h4>
            <p className="text-[#737D76] leading-relaxed">
              Incorporate 7-day and 14-day rolling waste averages per canteen section. Food consumption has strong weekly cyclicality that static dates cannot capture.
            </p>
          </div>

          <div className="p-3.5 rounded-xl border border-[#E3E8E1] bg-white">
            <h4 className="font-semibold text-[#24312B] mb-1">2. University Academic Calendar & Foot Traffic</h4>
            <p className="text-[#737D76] leading-relaxed">
              Integrate student swipe logs, exam schedules, and university holidays. Waste drops dramatically when students are on study breaks.
            </p>
          </div>

          <div className="p-3.5 rounded-xl border border-[#E3E8E1] bg-white">
            <h4 className="font-semibold text-[#24312B] mb-1">3. Gradient Boosted Trees (LightGBM / XGBoost)</h4>
            <p className="text-[#737D76] leading-relaxed">
              Experiment with modern gradient boosted tree models and Optuna hyperparameter optimization to reduce MAE below 0.8 kg.
            </p>
          </div>

          <div className="p-3.5 rounded-xl border border-[#E3E8E1] bg-white">
            <h4 className="font-semibold text-[#24312B] mb-1">4. Portions Prepared vs. Leftover Split</h4>
            <p className="text-[#737D76] leading-relaxed">
              Log both the total weight of food prepared and plate return scraps separately to distinguish kitchen overproduction from student uneaten food.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
