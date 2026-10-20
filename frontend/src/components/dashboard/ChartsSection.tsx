import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
  AreaChart,
  Area,
  CartesianGrid,
  Legend,
} from 'recharts';
import { Card, CardHeader, CardTitle, CardDescription } from '../ui/Card';
import { Skeleton } from '../ui/Skeleton';
import { DistributionData } from '../../types';
import { formatCurrency, formatKg, formatPercent } from '../../lib/utils';

interface ChartsSectionProps {
  distribution?: DistributionData;
  isLoading?: boolean;
}

export function ChartsSection({ distribution, isLoading }: ChartsSectionProps) {
  if (isLoading || !distribution) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {[...Array(6)].map((_, i) => (
          <Card key={i} className="h-80 flex flex-col justify-between">
            <Skeleton className="w-1/2 h-5 mb-2" />
            <Skeleton className="w-full h-56" />
          </Card>
        ))}
      </div>
    );
  }

  // Risk Color Mapping
  const getRiskColor = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'low':
        return '#059669';
      case 'medium':
        return '#D97706';
      case 'high':
        return '#E11D48';
      default:
        return '#245C46';
    }
  };

  const categoryColors = ['#245C46', '#3D7C62', '#629E84', '#8FBFA9'];

  return (
    <div className="space-y-6">
      {/* Top 3 Bar Charts */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* 1. Food Waste by Category */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Waste by Food Category</CardTitle>
              <CardDescription>Total waste generated across dish categories</CardDescription>
            </div>
          </CardHeader>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distribution.waste_by_category} margin={{ top: 10, right: 10, left: -15, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F0F3ED" />
                <XAxis dataKey="category" tick={{ fill: '#737D76', fontSize: 11 }} interval={0} angle={-15} textAnchor="end" />
                <YAxis tick={{ fill: '#737D76', fontSize: 11 }} />
                <Tooltip
                  formatter={(val: any) => [formatKg(Number(val)), 'Total Waste']}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E3E8E1', borderRadius: '8px', fontSize: '12px' }}
                />
                <Bar dataKey="waste_kg" radius={[4, 4, 0, 0]}>
                  {distribution.waste_by_category.map((_, index) => (
                    <Cell key={`cell-cat-${index}`} fill={categoryColors[index % categoryColors.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* 2. Food Waste by Meal */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Waste by Meal Period</CardTitle>
              <CardDescription>Comparison across breakfast, lunch, and dinner</CardDescription>
            </div>
          </CardHeader>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distribution.waste_by_meal} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F0F3ED" />
                <XAxis dataKey="meal" tick={{ fill: '#737D76', fontSize: 11 }} />
                <YAxis tick={{ fill: '#737D76', fontSize: 11 }} />
                <Tooltip
                  formatter={(val: any) => [formatKg(Number(val)), 'Total Waste']}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E3E8E1', borderRadius: '8px', fontSize: '12px' }}
                />
                <Bar dataKey="waste_kg" fill="#A8BFA5" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* 3. Food Waste by Section */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Waste by Canteen Section</CardTitle>
              <CardDescription>Distribution across physical serving stations</CardDescription>
            </div>
          </CardHeader>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distribution.waste_by_section} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F0F3ED" />
                <XAxis dataKey="section" tick={{ fill: '#737D76', fontSize: 11 }} tickFormatter={(s) => `Sec ${s}`} />
                <YAxis tick={{ fill: '#737D76', fontSize: 11 }} />
                <Tooltip
                  formatter={(val: any) => [formatKg(Number(val)), 'Total Waste']}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E3E8E1', borderRadius: '8px', fontSize: '12px' }}
                />
                <Bar dataKey="waste_kg" fill="#245C46" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Middle Row: Financial Loss & Risk Distribution */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* 4. Financial Loss by Category */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Financial Loss by Category</CardTitle>
              <CardDescription>Dollar amount lost based on item unit price ($)</CardDescription>
            </div>
          </CardHeader>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distribution.financial_loss_by_category} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F0F3ED" />
                <XAxis dataKey="category" tick={{ fill: '#737D76', fontSize: 11 }} />
                <YAxis tick={{ fill: '#737D76', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  formatter={(val: any) => [formatCurrency(Number(val)), 'Financial Loss']}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E3E8E1', borderRadius: '8px', fontSize: '12px' }}
                />
                <Bar dataKey="cost_loss" fill="#E6B566" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* 5. Waste Risk Distribution */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Waste Risk Distribution</CardTitle>
              <CardDescription>Frequency of Low, Medium, and High risk classifications</CardDescription>
            </div>
          </CardHeader>
          <div className="h-64 w-full flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={distribution.risk_distribution}
                  dataKey="count"
                  nameKey="risk"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={4}
                  label={({ risk, percentage }: any) => `${risk}: ${percentage}%`}
                >
                  {distribution.risk_distribution.map((entry) => (
                    <Cell key={`risk-cell-${entry.risk}`} fill={getRiskColor(entry.risk)} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(val: any, name: any, item: any) => [
                    `${val} records (${formatPercent(item.payload.percentage)})`,
                    `${name} Risk`,
                  ]}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E3E8E1', borderRadius: '8px', fontSize: '12px' }}
                />
                <Legend verticalAlign="bottom" height={36} iconType="circle" />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* 6. Daily Waste & Financial Loss Trend */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Daily Food Waste & Financial Loss Trend</CardTitle>
            <CardDescription>Time-series view of day-by-day food waste (kg) and associated cost loss ($)</CardDescription>
          </div>
        </CardHeader>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={distribution.daily_waste_trend} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="wasteGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#245C46" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#245C46" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="lossGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#E6B566" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#E6B566" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F0F3ED" />
              <XAxis dataKey="date" tick={{ fill: '#737D76', fontSize: 11 }} minTickGap={30} />
              <YAxis yAxisId="left" tick={{ fill: '#737D76', fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: '#737D76', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                formatter={(val: any, name: any) => {
                  if (name === 'Daily Waste') return [formatKg(Number(val)), name];
                  if (name === 'Financial Loss') return [formatCurrency(Number(val)), name];
                  return [val, name];
                }}
                contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E3E8E1', borderRadius: '8px', fontSize: '12px' }}
              />
              <Legend verticalAlign="top" align="right" height={36} iconType="circle" />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="waste_kg"
                name="Daily Waste"
                stroke="#245C46"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#wasteGradient)"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="cost_loss"
                name="Financial Loss"
                stroke="#E6B566"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#lossGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
