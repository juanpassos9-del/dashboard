import { useState, type FormEvent } from 'react';
import { Activity, ArrowRight, CalendarDays, CandlestickChart, Eye, EyeOff, LockKeyhole, Mail, Newspaper } from 'lucide-react';
import { createClient } from '@supabase/supabase-js';
import './App.css';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const streamlitUrl = import.meta.env.VITE_STREAMLIT_URL;
const supabase = supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;

function App() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');

    if (!supabase) {
      setError('O serviço de autenticação não está configurado.');
      return;
    }

    const rawDestination = String(streamlitUrl || '').trim().replace(/^['"]|['"]$/g, '');
    let destination: URL;
    try {
      const absoluteDestination = /^[a-z][a-z\d+.-]*:\/\//i.test(rawDestination)
        ? rawDestination
        : `https://${rawDestination}`;
      destination = new URL(absoluteDestination);
      if (destination.protocol !== 'https:' && destination.hostname !== 'localhost') {
        throw new Error('Invalid destination');
      }
    } catch {
      setError('O endereço do terminal ainda não foi configurado.');
      return;
    }

    setPending(true);
    const { error: authError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    if (authError) {
      setError('E-mail ou senha inválidos. Confira os dados e tente novamente.');
      setPending(false);
      return;
    }

    window.location.replace(destination.toString());
  };

  return (
    <main className="login-page">
      <header className="site-header">
        <a className="brand" href="/" aria-label="Trading Strategy, início">
          <span>TRADING <b>STRATEGY</b></span>
        </a>
        <span className="secure-label"><LockKeyhole size={14} /> ÁREA DO ASSINANTE</span>
      </header>

      <section className="login-layout">
        <div className="login-copy">
          <div className="eyebrow"><span /> TERMINAL TTS</div>
          <h1>Inteligência de mercado.<br /><em>Em um só lugar.</em></h1>
          <div className="login-brand-image">
            <img
              src="/trading-strategy-logo.png"
              alt="Trading Strategy — o mercado como você nunca viu"
            />
          </div>
          <section className="platform-preview" aria-label="Demonstração das áreas do terminal">
            <div className="preview-heading">
              <span>PRÉVIA DO TERMINAL</span>
              <span>DEMONSTRAÇÃO · NÃO É TEMPO REAL</span>
            </div>
            <div className="preview-row">
              <Activity size={15} aria-hidden="true" />
              <div><strong>FX COMMAND CENTER</strong><span>Majors · DXY · Treasuries · correlações</span></div>
              <i className="preview-spark spark-fx" aria-hidden="true" />
            </div>
            <div className="preview-row">
              <Activity size={15} aria-hidden="true" />
              <div><strong>TERMINAL GLOBAL</strong><span>FX · ações · bonds · commodities</span></div>
              <i className="preview-spark spark-global" aria-hidden="true" />
            </div>
            <div className="preview-row">
              <CandlestickChart size={15} aria-hidden="true" />
              <div><strong>TERMINAL DE TRADING</strong><span>WIN/WDO · ajustes · zonas de desvio</span></div>
              <i className="preview-spark spark-trading" aria-hidden="true" />
            </div>
            <div className="preview-row">
              <CalendarDays size={15} aria-hidden="true" />
              <div><strong>INTELIGÊNCIA DE MERCADO</strong><span>Calendário econômico · Market Report</span></div>
              <Newspaper size={14} className="preview-news" aria-hidden="true" />
            </div>
          </section>
        </div>

        <section className="login-panel" aria-labelledby="login-title">
          <div className="panel-mark"><LockKeyhole size={18} /></div>
          <div className="panel-kicker">ACESSO DO ASSINANTE</div>
          <h2 id="login-title">Bem-vindo de volta</h2>
          <p className="panel-subtitle">Acesse seu terminal TTS</p>

          <form onSubmit={handleSubmit}>
            <label htmlFor="email">E-mail</label>
            <div className="input-wrap">
              <Mail size={17} aria-hidden="true" />
              <input
                id="email"
                type="email"
                autoComplete="username"
                placeholder="voce@exemplo.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="password-label">
              <label htmlFor="password">Senha</label>
            </div>
            <div className="input-wrap">
              <LockKeyhole size={17} aria-hidden="true" />
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Sua senha"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              <button
                className="visibility-button"
                type="button"
                onClick={() => setShowPassword((visible) => !visible)}
                aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                title={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>

            {error && <div className="form-error" role="alert">{error}</div>}

            <button className="submit-button" type="submit" disabled={pending}>
              <span>{pending ? 'Validando acesso...' : 'Entrar no terminal'}</span>
              {!pending && <ArrowRight size={17} />}
            </button>
          </form>

          <div className="panel-footer"><span /> CONEXÃO SEGURA <b>·</b> SUPABASE AUTH</div>
        </section>
      </section>

      <footer className="site-footer">
        <span>© {new Date().getFullYear()} Trading Strategy</span>
        <span>ANÁLISE · CONTEXTO · EXECUÇÃO</span>
      </footer>
    </main>
  );
}

export default App;
