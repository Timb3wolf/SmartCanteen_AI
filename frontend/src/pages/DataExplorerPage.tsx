import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Database,
  Search,
  Download,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Filter,
  RotateCcw,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { RiskBadge } from '../components/ui/RiskBadge';
import { fetchMetadata, fetchRecords, getExportCsvUrl } from '../services/api';
import { FilterState } from '../types';
import { formatCurrency, formatDate, formatKg } from '../lib/utils';

export function DataExplorerPage() {
  const [filters, setFilters] = useState<FilterState>({
    meals: [],
    sections: [],
    categories: [],
  });
  const [search, setSearch] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('Date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const { data: metadata } = useQuery({
    queryKey: ['metadata'],
    queryFn: fetchMetadata,
  });

  const { data: recordsData, isLoading } = useQuery({
    queryKey: ['canteen-records', filters, search, sortBy, sortOrder, page, pageSize],
    queryFn: () => fetchRecords(filters, search, sortBy, sortOrder, page, pageSize),
  });

  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
    setPage(1);
  };

  const exportUrl = getExportCsvUrl(filters, search);

  const meals = metadata?.meals || ['Breakfast', 'Lunch', 'Dinner'];
  const sections = metadata?.canteen_sections || ['A', 'B', 'C', 'D'];
  const categories = metadata?.food_categories || ['Meat', 'Rice', 'Soup', 'Vegetables'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-[#E3E8E1] p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#EBF1EA] text-[#245C46]">
              Server-Side Pagination & Query
            </span>
            <span className="text-xs text-[#737D76]">
              {recordsData?.total ?? 2600} Total Matching Records
            </span>
          </div>
          <h1 className="text-2xl font-bold text-[#24312B] tracking-tight">Canteen Historical Dataset Explorer</h1>
          <p className="text-xs text-[#737D76] max-w-2xl mt-1">
            Inspect raw observation logs, sort by dish waste weight or financial loss, and download filtered records as a CSV.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <a href={exportUrl} download="SmartCanteen_Filtered_Data.csv">
            <Button variant="primary" size="sm" className="gap-1.5">
              <Download className="w-3.5 h-3.5" />
              <span>Export Filtered CSV</span>
            </Button>
          </a>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          {/* Search Box */}
          <div className="relative w-full lg:w-72">
            <Search className="w-4 h-4 text-[#737D76] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search category, meal, section, risk..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full text-xs bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg pl-9 pr-3 py-2 text-[#24312B] focus:outline-none focus:ring-1 focus:ring-[#245C46]"
            />
          </div>

          {/* Inline Category, Meal, Section Quick Filters */}
          <div className="flex flex-wrap items-center gap-3 text-xs w-full lg:w-auto">
            {/* Meal Filter */}
            <select
              value={filters.meals[0] || ''}
              onChange={(e) => {
                const val = e.target.value;
                setFilters({ ...filters, meals: val ? [val] : [] });
                setPage(1);
              }}
              className="bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-2.5 py-1.5 text-[#24312B] focus:outline-none"
            >
              <option value="">All Meals</option>
              {meals.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>

            {/* Section Filter */}
            <select
              value={filters.sections[0] || ''}
              onChange={(e) => {
                const val = e.target.value;
                setFilters({ ...filters, sections: val ? [val] : [] });
                setPage(1);
              }}
              className="bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-2.5 py-1.5 text-[#24312B] focus:outline-none"
            >
              <option value="">All Sections</option>
              {sections.map((s) => (
                <option key={s} value={s}>
                  Section {s}
                </option>
              ))}
            </select>

            {/* Category Filter */}
            <select
              value={filters.categories[0] || ''}
              onChange={(e) => {
                const val = e.target.value;
                setFilters({ ...filters, categories: val ? [val] : [] });
                setPage(1);
              }}
              className="bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-2.5 py-1.5 text-[#24312B] focus:outline-none"
            >
              <option value="">All Categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            {(filters.meals.length > 0 || filters.sections.length > 0 || filters.categories.length > 0 || search) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilters({ meals: [], sections: [], categories: [] });
                  setSearch('');
                  setPage(1);
                }}
                className="text-xs text-[#737D76] hover:text-[#C65353]"
              >
                <RotateCcw className="w-3 h-3 mr-1" />
                Reset
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Table Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <div>
              <CardTitle>Historical Log Table</CardTitle>
              <CardDescription>
                Showing {recordsData?.items.length || 0} of {recordsData?.total || 0} records (Page {recordsData?.page || 1} of {recordsData?.total_pages || 1})
              </CardDescription>
            </div>

            <div className="flex items-center gap-2 text-xs text-[#737D76]">
              <span>Rows per page:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="bg-[#F7F8F4] border border-[#E3E8E1] rounded-md px-2 py-1 text-xs text-[#24312B]"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>
        </CardHeader>

        {isLoading ? (
          <div className="py-16 text-center text-xs text-[#737D76]">Loading records...</div>
        ) : !recordsData || recordsData.items.length === 0 ? (
          <div className="py-16 text-center text-[#737D76]">
            <Database className="w-10 h-10 mx-auto text-[#CBD5C8] mb-2" />
            <p className="text-sm font-semibold text-[#24312B]">No Records Found</p>
            <p className="text-xs text-[#737D76]">Try adjusting your search criteria or resetting filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#F7F8F4] border-y border-[#E3E8E1] text-[#737D76]">
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B]"
                    onClick={() => handleSort('Date')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Date</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B]"
                    onClick={() => handleSort('Meal')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Meal</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B]"
                    onClick={() => handleSort('Canteen_Section')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Section</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B]"
                    onClick={() => handleSort('Food_Category')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Food Category</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B] text-right"
                    onClick={() => handleSort('Waste_Weight_kg')}
                  >
                    <div className="flex items-center justify-end gap-1">
                      <span>Waste Weight</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B] text-right"
                    onClick={() => handleSort('Unit_Price_per_kg')}
                  >
                    <div className="flex items-center justify-end gap-1">
                      <span>Unit Price</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-2.5 px-4 font-semibold cursor-pointer hover:text-[#24312B] text-right"
                    onClick={() => handleSort('Cost_Loss')}
                  >
                    <div className="flex items-center justify-end gap-1">
                      <span>Cost Loss</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th className="py-2.5 px-4 font-semibold text-center">Waste Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F0F3ED]">
                {recordsData.items.map((row, idx) => (
                  <tr key={idx} className="hover:bg-[#F7F8F4]/80 transition-colors">
                    <td className="py-2.5 px-4 font-medium text-[#24312B]">{formatDate(row.Date)}</td>
                    <td className="py-2.5 px-4">{row.Meal}</td>
                    <td className="py-2.5 px-4">Section {row.Canteen_Section}</td>
                    <td className="py-2.5 px-4 font-medium text-[#24312B]">{row.Food_Category}</td>
                    <td className="py-2.5 px-4 font-bold text-[#245C46] text-right">
                      {formatKg(row.Waste_Weight_kg)}
                    </td>
                    <td className="py-2.5 px-4 text-right">{formatCurrency(row.Unit_Price_per_kg)}/kg</td>
                    <td className="py-2.5 px-4 font-semibold text-[#D97706] text-right">
                      {formatCurrency(row.Cost_Loss)}
                    </td>
                    <td className="py-2.5 px-4 text-center">
                      <RiskBadge risk={row.Waste_Risk} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {recordsData && recordsData.total_pages > 1 && (
          <div className="pt-4 border-t border-[#F0F3ED] flex items-center justify-between text-xs text-[#737D76]">
            <div>
              Showing Page <span className="font-semibold text-[#24312B]">{recordsData.page}</span> of{' '}
              <span className="font-semibold text-[#24312B]">{recordsData.total_pages}</span>
            </div>

            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="px-2 py-1"
              >
                <ChevronLeft className="w-4 h-4 mr-0.5" />
                <span>Previous</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                disabled={page >= recordsData.total_pages}
                onClick={() => setPage(page + 1)}
                className="px-2 py-1"
              >
                <span>Next</span>
                <ChevronRight className="w-4 h-4 ml-0.5" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
