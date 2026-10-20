import { Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { fetchHealth } from '../services/api';

export function RootLayout() {
  const { data: health, isLoading: isLoadingHealth } = useQuery({
    queryKey: ['system-health'],
    queryFn: fetchHealth,
    refetchInterval: 30000,
    retry: 2,
  });

  return (
    <div className="min-h-screen flex flex-col bg-[#F7F8F4] text-[#24312B]">
      <Navbar health={health} isLoadingHealth={isLoadingHealth} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Outlet />
      </main>

      <Footer />
    </div>
  );
}
