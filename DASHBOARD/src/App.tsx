import React, { useEffect, useState } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Globe, 
  BarChart3, 
  Newspaper, 
  Calendar as CalendarIcon,
  LayoutDashboard
} from 'lucide-react';
import { 
  ResponsiveContainer,
  AreaChart,
  Area
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';

// --- CONFIGURAÇÃO SUPABASE ---
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('quotes');
  const [quotes, setQuotes] = useState<any[]>([]);

  // Efeito para buscar dados e ouvir o Realtime
  useEffect(() => {
    // 1. Busca dados iniciais
    const fetchInitialData = async () => {
      const { data } = await supabase.from('market_data').select('*');
      if (data) setQuotes(data);
    };

    fetchInitialData();

    // 2. Inscreve no canal Realtime
    const channel = supabase
      .channel('market_changes')
      .on('postgres_changes', 
        { event: '*', schema: 'public', table: 'market_data' }, 
        (payload) => {
          setQuotes(current => {
            const index = current.findIndex(q => q.symbol === (payload.new as any).symbol);
            if (index > -1) {
              const updated = [...current];
              updated[index] = payload.new;
              return updated;
            }
            return [...current, payload.new];
          });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const renderTabContent = () => {
    switch (activeTab) {
      case 'quotes':
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4">
            {quotes.map((quote) => (
              <motion.div
                key={quote.symbol}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-gray-900/60 backdrop-blur-md border border-gray-800 rounded-xl p-5 hover:border-indigo-500/50 transition-all shadow-xl"
              >
                <div className="flex justify-between items-start mb-3">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{quote.category || 'Ativo'}</span>
                  {(quote.change_percent || 0) >= 0 ? 
                    <TrendingUp className="text-emerald-400 w-4 h-4" /> : 
                    <TrendingDown className="text-rose-400 w-4 h-4" />
                  }
                </div>
                <h3 className="text-lg font-bold text-gray-100">{quote.symbol}</h3>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-black text-white">
                    {(quote.last_price || 0).toLocaleString('pt-BR', { minimumFractionDigits: (quote.last_price || 0) < 10 ? 4 : 2 })}
                  </span>
                  <span className={`text-sm font-bold ${(quote.change_percent || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {(quote.change_percent || 0) >= 0 ? '+' : ''}{(quote.change_percent || 0).toFixed(2)}%
                  </span>
                </div>
                <div className="mt-4 h-16 w-full flex items-center justify-center border border-gray-800/30 rounded-lg bg-black/20">
                   <span className="text-[10px] text-gray-600">LIVE FEED ACTIVE</span>
                </div>
              </motion.div>
            ))}
          </div>
        );
      case 'correlations':
        return (
          <div className="p-4 h-[500px] bg-gray-900/40 rounded-2xl border border-gray-800 m-4 flex items-center justify-center">
            <div className="text-center">
              <BarChart3 className="w-12 h-12 text-indigo-400 mx-auto mb-4 opacity-50" />
              <p className="text-gray-400">Matriz de Correlação Intermercado</p>
              <p className="text-xs text-gray-500 mt-2">Dados em tempo real via Supabase SDK</p>
            </div>
          </div>
        );
      default:
        return <div className="p-10 text-center text-gray-500">Em desenvolvimento...</div>;
    }
  };

  return (
    <div className="min-h-screen text-gray-100 p-4 max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-center py-8 border-b border-gray-800/50 mb-8">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-600 p-2 rounded-lg shadow-lg shadow-indigo-500/20">
            <LayoutDashboard className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black bg-gradient-to-r from-indigo-400 via-purple-400 to-indigo-500 bg-clip-text text-transparent">
              PROFIT DASHBOARD
            </h1>
            <p className="text-xs text-gray-500 font-medium">TERMINAL FINANCEIRO INSTITUCIONAL</p>
          </div>
        </div>

        <nav className="flex bg-gray-900/80 backdrop-blur-sm p-1 rounded-xl border border-gray-800 mt-6 md:mt-0">
          <button 
            onClick={() => setActiveTab('quotes')}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'quotes' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Cotações
          </button>
          <button 
            onClick={() => setActiveTab('correlations')}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'correlations' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Correlações
          </button>
          <button 
            onClick={() => setActiveTab('news')}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'news' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Notícias
          </button>
        </nav>
      </header>

      {/* Main Content */}
      <main>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
            transition={{ duration: 0.2 }}
          >
            {renderTabContent()}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Footer / Status */}
      <footer className="mt-12 pt-6 border-t border-gray-800/50 flex flex-col md:flex-row justify-between items-center text-[10px] text-gray-500 uppercase tracking-widest gap-4">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
          Status: Sistema Operacional • Profit Bridge Ativo
        </div>
        <div>
          Dados: Yahoo Finance & ProfitChart RTD • Atualização: 3s
        </div>
        <div className="flex items-center gap-4">
          <Globe className="w-3 h-3" />
          <Newspaper className="w-3 h-3" />
          <CalendarIcon className="w-3 h-3" />
        </div>
      </footer>
    </div>
  );
};

export default App;
