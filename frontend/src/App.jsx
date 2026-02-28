import React, { useState, useEffect, useRef } from 'react';
import useWebSocket from 'react-use-websocket';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar } from 'recharts';
import { Activity, Server, Cpu, Network, Wifi, AlertTriangle, CheckCircle2, Settings, History, Info } from 'lucide-react';

const generateDDPGData = (mode) => {
  let r = mode === 'Train' ? -2000 : 500;
  return Array.from({ length: 50 }, (_, i) => {
    r += mode === 'Train' ? Math.random() * 100 : Math.random() * 20 - 10;
    return {
      episode: i,
      actorLoss: mode === 'Train' ? Math.random() * -0.015 : Math.random() * -0.002 - 0.005,
      criticLoss: mode === 'Train' ? Math.random() * 0.05 : Math.random() * 0.01 + 0.01,
      reward: r,
    };
  });
};

const App = () => {
  const [activeTab, setActiveTab] = useState('config');
  // Fill initial buffer to render chart shapes
  const [metrics, setMetrics] = useState(Array.from({ length: 20 }, (_, i) => ({ time: i, throughput: 0, latency: 0, utilization: 0, users: 0 })));
  const [logs, setLogs] = useState([]);
  const [trainingMode, setTrainingMode] = useState('Train');
  const [ddpgData, setDdpgData] = useState(generateDDPGData('Train'));

  // Config state
  const [syncInterval, setSyncInterval] = useState(10);
  const [isApplying, setIsApplying] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Handle DDPG Tab Switch
  useEffect(() => {
    setDdpgData(generateDDPGData(trainingMode));
  }, [trainingMode]);

  const handleApplyConfig = () => {
    setIsApplying(true);
    setLogs(prev => [{ type: 'SYS', level: 'INFO', msg: `Applied new configuration. Sync interval set to ${syncInterval}s.`, node: 'WebUI', ts: new Date().toLocaleTimeString('en-US', { hour12: false }) }, ...prev].slice(0, 10));
    setTimeout(() => setIsApplying(false), 800);
  };

  const handleExportCSV = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      alert("Historical data exported to downloads folder!");
    }, 1000);
  };

  const WS_URL = 'ws://127.0.0.1:8000/ws';
  const { lastJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: (closeEvent) => true,
    reconnectInterval: 3000,
  });

  useEffect(() => {
    if (lastJsonMessage) {
      if (lastJsonMessage.type === "METRICS") {
        setMetrics(prev => {
          const newArr = [...prev.slice(1)];
          newArr.push(lastJsonMessage);
          return newArr;
        });
      } else {
        setLogs(prev => {
          const newLogs = [lastJsonMessage, ...prev].slice(0, 10);
          return newLogs;
        });
      }
    }
  }, [lastJsonMessage]);


  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-4 font-sans selection:bg-cyan-500/30">

      {/* Header */}
      <header className="flex items-center justify-between mb-6 pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-cyan-950/50 rounded-lg border border-cyan-800 shadow-[0_0_15px_rgba(6,182,212,0.2)]">
            <Network className="w-6 h-6 text-cyan-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent tracking-wide">
              6G ADVANCED RESOURCE SCHEDULER
            </h1>
            <p className="text-xs text-slate-500 tracking-wider">DRS-SIM v3.1 | DISTRIBUTED EDGE ENGINE</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 rounded-full border border-slate-800 text-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span className="text-emerald-400 font-medium">System Online</span>
          </div>
          <button className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400 hover:text-cyan-400">
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-12 gap-6 pb-12">

        {/* Left Col: Topology (8/12) */}
        <div className="col-span-12 xl:col-span-8 flex flex-col gap-6">

          {/* Topology Map Panel */}
          <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-4 relative overflow-hidden backdrop-blur-sm shadow-xl min-h-[450px]">
            <div className="flex justify-between items-center mb-4 relative z-10">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Wifi className="w-5 h-5 text-cyan-500" />
                Live 5G/6G Network Topology Map
              </h2>
              <div className="flex gap-4 text-xs font-medium">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500"></span>Healthy</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500"></span>Medium Load</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.6)]"></span>Congested/Critical</span>
              </div>
            </div>

            {/* SVG Topology Visualization Background */}
            <div className="absolute inset-0 top-12 flex items-center justify-center pointer-events-none opacity-20">
              <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
                <path d="M0,0 L100,100 M100,0 L0,100 M50,0 L50,100 M0,50 L100,50" stroke="#334155" strokeWidth="0.5" strokeDasharray="2,2" />
              </svg>
            </div>

            {/* Simulated Nodes & Links */}
            <div className="absolute inset-0 top-16 flex items-center justify-center">
              <div className="relative w-[700px] h-[350px]">
                {/* Lines (Edges) */}
                <svg className="absolute inset-0 w-full h-full pb-4">
                  {/* RU-1 to DU-1 */}
                  <line x1="100" y1="80" x2="250" y2="175" stroke="#334155" strokeWidth="4" />
                  <text x="160" y="115" fill="#64748b" fontSize="10" transform="rotate(35 160 115)">5G NR</text>

                  {/* RU-2 to DU-1 */}
                  <line x1="100" y1="270" x2="250" y2="175" stroke="#0ea5e9" strokeWidth="10" className="opacity-60" /> {/* Heavy Utilization */}
                  <text x="175" y="245" fill="#0ea5e9" fontSize="10" transform="rotate(-35 175 245)">Util: 89%</text>

                  {/* DU-1 to DU-Core */}
                  <line x1="250" y1="175" x2="400" y2="175" stroke="#334155" strokeWidth="3" />
                  <text x="325" y="165" fill="#64748b" fontSize="10" textAnchor="middle">Lk: 10Gbps</text>

                  {/* DU-Core to CU-East */}
                  <line x1="400" y1="175" x2="550" y2="80" stroke="#f43f5e" strokeWidth="6" className="opacity-80" /> {/* Congested */}
                  <text x="475" y="120" fill="#f43f5e" fontSize="10" transform="rotate(-35 475 120)">Util: 95%</text>

                  {/* DU-Core to CU-West */}
                  <line x1="400" y1="175" x2="550" y2="270" stroke="#334155" strokeWidth="4" />
                  <text x="475" y="240" fill="#64748b" fontSize="10" transform="rotate(35 475 240)">F1/E2 Interface</text>

                  {/* Top RU */}
                  <line x1="300" y1="50" x2="400" y2="175" stroke="#334155" strokeWidth="2" />
                  {/* Bot RU */}
                  <line x1="300" y1="300" x2="400" y2="175" stroke="#334155" strokeWidth="2" />
                </svg>

                {/* Nodes rendering using absolute positioning */}

                {/* Node RU101-G (Green) */}
                <div className="absolute top-[80px] left-[100px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-16 h-16 rounded-full bg-slate-900 border-[3px] border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)] flex items-center justify-center text-xs font-bold text-slate-300">RU-1</div>
                </div>

                {/* Node RU102-G (Green) */}
                <div className="absolute top-[270px] left-[100px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-16 h-16 rounded-full bg-slate-900 border-[3px] border-emerald-500 flex items-center justify-center text-xs font-bold text-slate-300">RU-2</div>
                </div>

                {/* Node DU101-G (Green) */}
                <div className="absolute top-[175px] left-[250px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-20 h-20 rounded-full bg-slate-900 border-[4px] border-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.3)] flex items-center justify-center text-sm font-bold text-slate-300 relative group">
                    DU-1
                    <div className="absolute -top-12 left-1/2 -translate-x-1/2 bg-slate-950 border border-slate-700 py-1 px-2 rounded text-[10px] text-slate-400 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20">
                      BW 1.3Gbps | Lat 4ms
                    </div>
                  </div>
                </div>

                {/* Node DU105-Y (Yellow - Core) */}
                <div className="absolute top-[175px] left-[400px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-24 h-24 rounded-full bg-slate-900 border-[5px] border-amber-500 shadow-[0_0_25px_rgba(245,158,11,0.4)] flex items-center justify-center text-base font-bold text-slate-200">
                    DU-Core
                  </div>
                </div>

                {/* Top RU-3 (Green) */}
                <div className="absolute top-[50px] left-[300px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-12 h-12 rounded-full bg-slate-900 border-[2px] border-emerald-500 flex items-center justify-center text-[10px] font-bold text-slate-400">RU-3</div>
                </div>

                {/* Bottom RU-4 (Green) */}
                <div className="absolute top-[300px] left-[300px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-12 h-12 rounded-full bg-slate-900 border-[2px] border-emerald-500 flex items-center justify-center text-[10px] font-bold text-slate-400">RU-4</div>
                </div>

                {/* Node CU202-R (Red - Congested) */}
                <div className="absolute top-[80px] left-[550px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-20 h-20 rounded-full bg-slate-900 border-[4px] border-rose-500 shadow-[0_0_30px_rgba(244,63,94,0.6)] animate-[pulse_2s_infinite] flex items-center justify-center text-sm font-bold text-rose-200 cursor-pointer">
                    CU-East
                  </div>
                  {/* Tooltip visible permanently for demo */}
                  <div className="absolute -bottom-16 left-1/2 -translate-x-1/2 bg-slate-950/90 border border-slate-700 py-1.5 px-3 rounded-lg text-xs whitespace-nowrap backdrop-blur-md z-20">
                    <div className="font-bold text-rose-400 border-b border-slate-800 pb-1 mb-1">Alert: High Load</div>
                    <div className="text-slate-400">Load: <span className="text-rose-400 font-mono">98%</span></div>
                  </div>
                </div>

                {/* Node CU208-G (Green) */}
                <div className="absolute top-[270px] left-[550px] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                  <div className="w-20 h-20 rounded-full bg-slate-900 border-[4px] border-emerald-500 flex items-center justify-center text-sm font-bold text-slate-300">
                    CU-West
                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* Bottom Panels Row (DDPG & RAFT) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 min-h-[250px]">

            {/* DDPG Training Monitor */}
            <div className="bg-slate-900/40 rounded-xl border border-slate-800 p-4 flex flex-col shadow-lg backdrop-blur-sm">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-semibold text-sm flex items-center gap-2 text-slate-200">
                  <Activity className="w-4 h-4 text-purple-400" />
                  1) DDPG Training Monitor
                </h3>
                <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-lg p-1">
                  <button
                    onClick={() => setTrainingMode('Train')}
                    className={`px-3 py-1 rounded text-xs font-medium transition-colors ${trainingMode === 'Train' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
                  >Train</button>
                  <button
                    onClick={() => setTrainingMode('Eval')}
                    className={`px-3 py-1 rounded text-xs font-medium transition-colors ${trainingMode === 'Eval' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
                  >Evaluate</button>
                </div>
              </div>

              <div className="flex gap-4 text-[10px] text-slate-400 mb-2 px-2">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-purple-500"></span>Critic Loss</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-cyan-500"></span>Total Reward</span>
              </div>

              <div className="flex-1 w-full min-h-[150px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={ddpgData} margin={{ top: 5, right: 0, left: -20, bottom: 5 }}>
                    <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={40} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip
                      contentStyle={{ backgroundColor: 'rgba(2, 6, 23, 0.9)', borderColor: '#1e293b', borderRadius: '8px', fontSize: '11px', backdropFilter: 'blur(4px)' }}
                      itemStyle={{ color: '#cbd5e1' }}
                    />
                    <Line yAxisId="left" type="monotone" dataKey="criticLoss" stroke="#a855f7" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                    <Line yAxisId="right" type="monotone" dataKey="reward" stroke="#0ea5e9" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* RAFT Consensus View */}
            <div className="bg-slate-900/40 rounded-xl border border-slate-800 p-4 flex flex-col shadow-lg backdrop-blur-sm">
              <div className="flex justify-between items-center mb-4 text-slate-200">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <Server className="w-4 h-4 text-blue-400" />
                  2) RAFT Consensus View
                </h3>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">Leader Node</div>
                  <div className="text-emerald-400 font-mono text-xs flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    RU-1 (Active)
                  </div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">Global State</div>
                  <div className="text-slate-300 font-mono text-xs flex justify-between">
                    <span>T: <span className="text-cyan-400">452</span></span>
                    <span>Idx: <span className="text-purple-400">18,970</span></span>
                  </div>
                </div>
              </div>

              <div className="flex-1 bg-slate-950/80 rounded-lg p-2.5 overflow-hidden border border-slate-800/80 font-mono text-[10px] space-y-2 relative shadow-inner">
                {logs.map((log, i) => (
                  <div key={i} className={`pl-4 border-l-2 ml-1 flex items-center gap-1 ${log.level === 'CRIT' || log.level === 'WARN' ? 'text-rose-400 border-rose-900/50' : 'text-slate-400 border-slate-800'}`}>
                    {log.level === 'CRIT' && <AlertTriangle className="w-3 h-3" />}
                    {log.level === 'INFO' && <span className="text-blue-500 mr-1">▶</span>}
                    [{log.node}] {log.msg}
                  </div>
                ))}

                {/* Fade out effect at bottom */}
                <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-slate-950 to-transparent pointer-events-none"></div>
              </div>
            </div>

          </div>
        </div>

        {/* Right Col: Control Panel & Metrics Sidebar (4/12) */}
        <div className="col-span-12 xl:col-span-4 flex flex-col gap-6">

          {/* Scheduler Control Panel */}
          <div className="bg-slate-900/50 rounded-xl border border-slate-800 flex flex-col shadow-lg backdrop-blur-sm overflow-hidden h-auto">
            {/* Tabs */}
            <div className="flex bg-slate-950/40">
              <button
                className={`flex-1 py-3 text-sm font-medium transition-all ${activeTab === 'config' ? 'bg-slate-800/80 text-cyan-400 border-t-2 border-cyan-400 shadow-inner text-shadow-sm shadow-cyan-500/20' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-900'}`}
                onClick={() => setActiveTab('config')}
              >
                Configuration
              </button>
              <button
                className={`flex-1 py-3 text-sm font-medium transition-all border-l border-slate-800 ${activeTab === 'history' ? 'bg-slate-800/80 text-purple-400 border-t-2 border-purple-400 shadow-inner text-shadow-sm shadow-purple-500/20' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-900'}`}
                onClick={() => setActiveTab('history')}
              >
                History
              </button>
            </div>

            {/* Tab Content */}
            <div className="p-5 overflow-y-auto">
              {activeTab === 'config' && (
                <div className="space-y-5">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Scheduling Algorithm</label>
                    <select className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-cyan-500 transition-colors shadow-inner appearance-none cursor-pointer">
                      <option>DDPG Edge AI (Active)</option>
                      <option>Stackelberg Game Theory</option>
                      <option>Static Capacity PF</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Active Nodes</label>
                      <input type="number" defaultValue={5} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-cyan-500 shadow-inner font-mono" />
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Max UEs / Cell</label>
                      <input type="number" defaultValue={250} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-cyan-500 shadow-inner font-mono" />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-1.5">
                      <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Cloud Sync Interval</label>
                      <span className="text-xs text-cyan-400 font-mono">{syncInterval}s</span>
                    </div>
                    <input type="range" min="1" max="60" value={syncInterval} onChange={(e) => setSyncInterval(e.target.value)} className="w-full accent-cyan-500 h-1.5 rounded-lg appearance-none bg-slate-800 cursor-pointer" />
                  </div>

                  <button
                    onClick={() => handleApplyConfig()}
                    disabled={isApplying}
                    className={`w-full mt-2 font-medium py-2.5 rounded-lg shadow-[0_4px_15px_rgba(6,182,212,0.25)] transition-all flex justify-center items-center gap-2 border border-cyan-400/20 active:scale-[0.98] ${isApplying ? 'bg-cyan-800 text-cyan-400 cursor-wait' : 'bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white'}`}
                  >
                    {isApplying ? <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div> : <Settings className="w-4 h-4" />}
                    {isApplying ? 'Applying...' : 'Apply Configuration'}
                  </button>
                </div>
              )}
              {activeTab === 'history' && (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-3 py-8">
                  <History className="w-8 h-8 opacity-50" />
                  <p className="text-sm">Historical Replay Mode Ready</p>
                  <button onClick={handleExportCSV} disabled={isExporting} className="px-4 py-1.5 border border-slate-700 rounded-md text-xs hover:bg-slate-800 transition-colors">
                    {isExporting ? 'Exporting...' : 'Export CSV'}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Main Stats (Moved to bottom right to fit description flow better, though original had right sidebar) */}
          <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-5 shadow-lg backdrop-blur-sm flex-1">
            <h2 className="text-sm font-semibold mb-5 flex items-center justify-between text-slate-200 border-b border-slate-800/60 pb-2">
              <span className="flex items-center gap-2"><Activity className="w-4 h-4 text-emerald-400" /> Real-Time System Metrics</span>
              <div className="flex space-x-1">
                <span className="w-1 h-3 bg-emerald-500 rounded-full animate-[bounce_1s_infinite]"></span>
                <span className="w-1 h-4 bg-emerald-500 rounded-full animate-[bounce_1s_infinite_100ms]"></span>
              </div>
            </h2>

            <div className="space-y-5">
              {/* Metric: Throughput */}
              <div>
                <div className="flex justify-between items-baseline mb-1">
                  <div className="text-xs text-slate-400 font-medium">Agg Throughput</div>
                  <div className="flex items-end gap-2">
                    <span className="text-xl font-bold text-slate-100 font-mono tracking-tight">{metrics[metrics.length - 1]?.throughput?.toFixed(1) || 0}</span>
                    <span className="text-[10px] text-slate-500 pb-0.5">Mbps</span>
                  </div>
                </div>
                <div className="h-10 w-full bg-slate-950/50 rounded overflow-hidden border border-slate-800/50">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={metrics}>
                      <defs>
                        <linearGradient id="colorTp" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.5} />
                          <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="monotone" dataKey="throughput" stroke="#0ea5e9" strokeWidth={2} fillOpacity={1} fill="url(#colorTp)" isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Metric: Latency */}
              <div>
                <div className="flex justify-between items-baseline mb-1">
                  <div className="text-xs text-slate-400 font-medium">System Latency</div>
                  <div className="flex items-end gap-2">
                    <span className="text-xl font-bold text-slate-100 font-mono tracking-tight">{metrics[metrics.length - 1]?.latency?.toFixed(1) || 0}</span>
                    <span className="text-[10px] text-slate-500 pb-0.5">ms</span>
                  </div>
                </div>
                <div className="h-10 w-full bg-slate-950/50 rounded overflow-hidden border border-slate-800/50">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={metrics}>
                      <defs>
                        <linearGradient id="colorLat" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#a855f7" stopOpacity={0.5} />
                          <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="step" dataKey="latency" stroke="#a855f7" strokeWidth={2} fillOpacity={1} fill="url(#colorLat)" isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                {/* Metric: Users */}
                <div className="bg-slate-950/50 border border-slate-800/50 p-2 rounded-lg flex flex-col items-center justify-center">
                  <div className="text-[10px] text-slate-400 mb-1">Active UEs</div>
                  <div className="text-xl font-bold text-cyan-400 font-mono tracking-tighter">{metrics[metrics.length - 1]?.users || 0}</div>
                </div>
                {/* Metric: Util */}
                <div className="bg-slate-950/50 border border-slate-800/50 p-2 rounded-lg flex flex-col items-center justify-center">
                  <div className="text-[10px] text-slate-400 mb-1">Compute Util</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono tracking-tighter">{metrics[metrics.length - 1]?.utilization?.toFixed(0) || 0}%</div>
                </div>
              </div>

              {/* TDD Split & Network Slicing */}
              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-800/60 mt-2">
                <div className="bg-slate-950/50 border border-slate-800/50 p-3 rounded-lg flex flex-col items-center justify-center relative overflow-hidden">
                  <div className="text-[10px] text-slate-400 mb-2 w-full text-left uppercase tracking-wider font-semibold">Dynamic TDD Split</div>
                  <div className="flex w-full h-3 rounded-full overflow-hidden bg-slate-800 mb-2">
                    <div className="bg-cyan-500 h-full transition-all duration-500" style={{ width: `${metrics[metrics.length - 1]?.tdd_dl || 50}%` }}></div>
                    <div className="bg-purple-500 h-full transition-all duration-500" style={{ width: `${metrics[metrics.length - 1]?.tdd_ul || 50}%` }}></div>
                  </div>
                  <div className="flex justify-between w-full text-[9px] font-mono font-bold">
                    <span className="text-cyan-400">DL: {metrics[metrics.length - 1]?.tdd_dl || 50}%</span>
                    <span className="text-purple-400">UL: {metrics[metrics.length - 1]?.tdd_ul || 50}%</span>
                  </div>
                </div>

                <div className="bg-slate-950/50 border border-slate-800/50 p-2 rounded-lg flex flex-col items-center justify-center">
                  <div className="text-[10px] text-slate-400 mb-2 w-full text-left uppercase tracking-wider font-semibold">Slice Allocation</div>
                  <div className="w-full flex-1 flex items-end justify-between gap-1 h-6">
                    {(metrics[metrics.length - 1]?.slice_allocation || []).map((slice, i) => (
                      <div key={i} className="flex flex-col items-center justify-end w-1/3 h-full group relative">
                        <div className={`w-full rounded-t-sm transition-all duration-500 ${i === 0 ? 'bg-blue-500/80' : i === 1 ? 'bg-rose-500/80' : 'bg-emerald-500/80'}`} style={{ height: `${slice.value}%`, minHeight: '4px' }}></div>
                        <div className="text-[8px] text-slate-500 mt-1 uppercase font-semibold">{slice.name}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Node-specific Resource Allocation */}
              <div className="pt-4 border-t border-slate-800/60 mt-2">
                <div className="text-xs text-slate-400 font-medium mb-3">Resource Allocation by Node</div>
                <div className="h-36 w-full bg-slate-950/50 rounded-lg p-2 border border-slate-800/50">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={metrics[metrics.length - 1]?.node_allocations || []} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} />
                      <Tooltip cursor={{ fill: '#0f172a' }} contentStyle={{ backgroundColor: 'rgba(2, 6, 23, 0.9)', borderColor: '#1e293b', borderRadius: '8px', fontSize: '10px' }} />
                      <Bar dataKey="spectrum" name="Spectrum (PRBs)" fill="#0ea5e9" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="compute" name="Compute (%)" fill="#8b5cf6" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="storage" name="Storage (Buffer MB)" fill="#f43f5e" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>

      {/* Footer Log Strip */}
      <div className="bg-slate-950 border-t border-slate-800 fixed bottom-0 left-0 right-0 h-10 flex items-center px-4 font-mono text-[11px] overflow-hidden z-20">
        <div className="flex items-center gap-8 animate-[scroll_20s_linear_infinite] whitespace-nowrap min-w-full hover:[animation-play-state:paused] cursor-default">
          {logs.map((log, i) => (
            <span key={`ticker-${i}`} className={`flex items-center gap-2 ${log.level === 'CRIT' ? 'text-rose-200' : 'text-slate-300'}`}>
              {log.level === 'CRIT' && <span className="text-rose-500 font-bold">{log.ts} | CRIT</span>}
              {log.level === 'WARN' && <span className="text-amber-500 font-bold">{log.ts} | WARN</span>}
              {log.level === 'INFO' && <span className="text-blue-500 font-bold">{log.ts} | INFO</span>}
              {log.msg}
            </span>
          ))}
          {/* Duplicate for infinite effect */}
          {logs.map((log, i) => (
            <span key={`ticker-dup-${i}`} className={`flex items-center gap-2 ${log.level === 'CRIT' ? 'text-rose-200' : 'text-slate-300'}`}>
              {log.level === 'CRIT' && <span className="text-rose-500 font-bold">{log.ts} | CRIT</span>}
              {log.level === 'WARN' && <span className="text-amber-500 font-bold">{log.ts} | WARN</span>}
              {log.level === 'INFO' && <span className="text-blue-500 font-bold">{log.ts} | INFO</span>}
              {log.msg}
            </span>
          ))}
        </div>
      </div>

    </div>
  );
};

export default App;
