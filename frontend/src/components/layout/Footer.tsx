import { Link } from 'react-router-dom';
import { Leaf, ShieldAlert } from 'lucide-react';

export function Footer() {
  return (
    <footer className="mt-auto border-t border-[#E3E8E1] bg-white py-8 text-xs text-[#737D76]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#245C46]/10 flex items-center justify-center text-[#245C46]">
              <Leaf className="w-3.5 h-3.5" />
            </div>
            <span className="font-semibold text-[#24312B]">SmartCanteen AI</span>
            <span>— Sustainable University Dining Analytics & ML</span>
          </div>

          <div className="flex items-center gap-6">
            <Link to="/models" className="hover:text-[#245C46] transition-colors flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Model Limitations (MAE: 1.32 kg | Acc: 35.4%)</span>
            </Link>
            <a
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
              className="hover:text-[#245C46] transition-colors"
            >
              Swagger API Docs
            </a>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-[#F0F3ED] text-center text-[11px] text-[#A0AAA2]">
          Built with React 19, TypeScript, Tailwind CSS, FastAPI, and scikit-learn. Historical data: 2,600 university canteen records.
        </div>
      </div>
    </footer>
  );
}
