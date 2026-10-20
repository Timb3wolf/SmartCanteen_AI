import { Filter, RotateCcw, Calendar, Check } from 'lucide-react';
import { FilterState, Metadata } from '../../types';
import { Button } from '../ui/Button';

interface FilterBarProps {
  filters: FilterState;
  metadata?: Metadata;
  onChange: (newFilters: FilterState) => void;
  onReset: () => void;
}

export function FilterBar({ filters, metadata, onChange, onReset }: FilterBarProps) {
  const toggleArrayItem = (list: string[], item: string): string[] => {
    if (list.includes(item)) {
      return list.filter((i) => i !== item);
    }
    return [...list, item];
  };

  const activeFiltersCount =
    (filters.startDate ? 1 : 0) +
    (filters.endDate ? 1 : 0) +
    (filters.meals.length > 0 ? 1 : 0) +
    (filters.sections.length > 0 ? 1 : 0) +
    (filters.categories.length > 0 ? 1 : 0);

  const allMeals = metadata?.meals || ['Breakfast', 'Lunch', 'Dinner'];
  const allSections = metadata?.canteen_sections || ['A', 'B', 'C', 'D'];
  const allCategories = metadata?.food_categories || ['Meat', 'Rice', 'Soup', 'Vegetables'];

  return (
    <div className="bg-white rounded-xl border border-[#E3E8E1] p-4 shadow-xs">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-3 border-b border-[#F0F3ED]">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
            <Filter className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-[#24312B]">Operational Filters</h2>
            <p className="text-xs text-[#737D76]">
              {activeFiltersCount === 0
                ? 'Showing all 2,600 historical records'
                : `${activeFiltersCount} active filter criteria applied`}
            </p>
          </div>
        </div>

        {activeFiltersCount > 0 && (
          <Button variant="ghost" size="sm" onClick={onReset} className="text-[#737D76] hover:text-[#C65353]">
            <RotateCcw className="w-3.5 h-3.5 mr-1" />
            Reset Filters
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 pt-3">
        {/* Date Range */}
        <div>
          <label className="block text-xs font-medium text-[#737D76] mb-1.5 flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5" /> Date Range
          </label>
          <div className="flex items-center gap-1.5">
            <input
              type="date"
              value={filters.startDate || ''}
              min={metadata?.date_range.min_date}
              max={metadata?.date_range.max_date}
              onChange={(e) => onChange({ ...filters, startDate: e.target.value || undefined })}
              className="w-full text-xs bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-2.5 py-1.5 text-[#24312B] focus:outline-none focus:ring-1 focus:ring-[#245C46]"
            />
            <span className="text-xs text-[#737D76]">-</span>
            <input
              type="date"
              value={filters.endDate || ''}
              min={metadata?.date_range.min_date}
              max={metadata?.date_range.max_date}
              onChange={(e) => onChange({ ...filters, endDate: e.target.value || undefined })}
              className="w-full text-xs bg-[#F7F8F4] border border-[#E3E8E1] rounded-lg px-2.5 py-1.5 text-[#24312B] focus:outline-none focus:ring-1 focus:ring-[#245C46]"
            />
          </div>
        </div>

        {/* Meal Filter */}
        <div>
          <label className="block text-xs font-medium text-[#737D76] mb-1.5">Meal Periods</label>
          <div className="flex flex-wrap gap-1.5">
            {allMeals.map((meal) => {
              const isSelected = filters.meals.includes(meal);
              return (
                <button
                  key={meal}
                  onClick={() => onChange({ ...filters, meals: toggleArrayItem(filters.meals, meal) })}
                  className={`text-xs px-2.5 py-1 rounded-md font-medium border transition-colors flex items-center gap-1 cursor-pointer ${
                    isSelected
                      ? 'bg-[#245C46] text-white border-[#245C46]'
                      : 'bg-[#F7F8F4] text-[#737D76] border-[#E3E8E1] hover:border-[#CBD5C8]'
                  }`}
                >
                  {isSelected && <Check className="w-3 h-3" />}
                  {meal}
                </button>
              );
            })}
          </div>
        </div>

        {/* Section Filter */}
        <div>
          <label className="block text-xs font-medium text-[#737D76] mb-1.5">Canteen Sections</label>
          <div className="flex flex-wrap gap-1.5">
            {allSections.map((sec) => {
              const isSelected = filters.sections.includes(sec);
              return (
                <button
                  key={sec}
                  onClick={() => onChange({ ...filters, sections: toggleArrayItem(filters.sections, sec) })}
                  className={`text-xs px-2.5 py-1 rounded-md font-medium border transition-colors flex items-center gap-1 cursor-pointer ${
                    isSelected
                      ? 'bg-[#245C46] text-white border-[#245C46]'
                      : 'bg-[#F7F8F4] text-[#737D76] border-[#E3E8E1] hover:border-[#CBD5C8]'
                  }`}
                >
                  {isSelected && <Check className="w-3 h-3" />}
                  Section {sec}
                </button>
              );
            })}
          </div>
        </div>

        {/* Food Category Filter */}
        <div>
          <label className="block text-xs font-medium text-[#737D76] mb-1.5">Food Categories</label>
          <div className="flex flex-wrap gap-1.5">
            {allCategories.map((cat) => {
              const isSelected = filters.categories.includes(cat);
              return (
                <button
                  key={cat}
                  onClick={() => onChange({ ...filters, categories: toggleArrayItem(filters.categories, cat) })}
                  className={`text-xs px-2.5 py-1 rounded-md font-medium border transition-colors flex items-center gap-1 cursor-pointer ${
                    isSelected
                      ? 'bg-[#245C46] text-white border-[#245C46]'
                      : 'bg-[#F7F8F4] text-[#737D76] border-[#E3E8E1] hover:border-[#CBD5C8]'
                  }`}
                >
                  {isSelected && <Check className="w-3 h-3" />}
                  {cat}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
