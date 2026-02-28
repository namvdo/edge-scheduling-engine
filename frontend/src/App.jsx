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
  const metricsRef = useRef([]);
  const [logs, setLogs] = useState([]);
  const [trainingMode, setTrainingMode] = useState('Train');
  const [ddpgData, setDdpgData] = useState(generateDDPGData('Train'));

  // Config state
  const [syncInterval, setSyncInterval] = useState(10);
  const [configRu, setConfigRu] = useState(5);
  const [configDu, setConfigDu] = useState(5);
  const [appliedConfig, setAppliedConfig] = useState({ ru: 5, du: 5, cu: 1 });
  const [configUes, setConfigUes] = useState(250);
  const [isApplying, setIsApplying] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Handle DDPG Tab Switch
  useEffect(() => {
    setDdpgData(generateDDPGData(trainingMode));
  }, [trainingMode]);

  // Reset selected node constraint on shrink
  useEffect(() => {
    setSelectedSpikeNode('RU-1');
  }, [appliedConfig]);

  const handleApplyConfig = () => {
    setIsApplying(true);
    setAppliedConfig({ ru: configRu, du: configDu, cu: 1 });
    sendJsonMessage({
      type: "UPDATE_CONFIG",
      ru: configRu,
      du: configDu,
      max_ues: configUes
    });
    setLogs(prev => [{ type: 'SYS', level: 'INFO', msg: `Applied new configuration. Sync interval set to ${syncInterval}s. Active RUs: ${configRu}, Active DUs: ${configDu}`, node: 'WebUI', ts: new Date().toLocaleTimeString('en-US', { hour12: false }) }, ...prev].slice(0, 10));
    // Simulate config delay
    setTimeout(() => {
      setIsApplying(false);
      metricsRef.current = [];
      setMetrics([]);
    }, 1000);
  };

  const handleExportCSV = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      alert("Historical data exported to downloads folder!");
    }, 1000);
  };

  const [selectedSpikeNode, setSelectedSpikeNode] = useState('RU-1');

  const WS_URL = 'ws://127.0.0.1:8000/ws';
  const { lastJsonMessage, sendJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: (closeEvent) => true,
    reconnectInterval: 3000,
  });

  const fireSpikeCommand = () => {
    sendJsonMessage({
      type: "INJECT_SPIKE",
      node: selectedSpikeNode
    });
  };

  // Process metrics specifically for the selected history node
  const activeHistoryData = metrics.map((m) => {
    let nodeData = { compute: 0, storage: 0, spectrum: 0 };
    if (m.node_allocations) {
      const found = m.node_allocations.find(n => n.name === selectedSpikeNode);
      if (found) nodeData = found;
    }
    return {
      time: m.time,
      CPU: nodeData.compute,
      Storage: nodeData.storage,
      Spectrum: nodeData.spectrum
    };
  });

  useEffect(() => {
    if (lastJsonMessage) {
      if (lastJsonMessage.type === "METRICS") {
        setMetrics(prev => {
          const newArr = [...prev.slice(1)];
          newArr.push(lastJsonMessage);
          metricsRef.current = newArr; // Update ref
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

  const getNodeColorClass = (nodeName, defaultClasses) => {
    const latest = metrics[metrics.length - 1];
    if (!latest || !latest.node_allocations) return `${defaultClasses} border-emerald-500 text-slate-300 shadow-[0_0_15px_rgba(16,185,129,0.3)]`;

    const node = latest.node_allocations.find(n => n.name === nodeName);
    if (!node) return `${defaultClasses} border-emerald-500 text-slate-300 shadow-[0_0_15px_rgba(16,185,129,0.3)]`;

    if (node.compute > 85) {
      return `${defaultClasses} border-rose-500 text-rose-200 shadow-[0_0_30px_rgba(244,63,94,0.6)] animate-[pulse_2s_infinite]`;
    } else if (node.compute > 60) {
      return `${defaultClasses} border-amber-500 text-amber-200 shadow-[0_0_25px_rgba(245,158,11,0.4)]`;
    }
    return `${defaultClasses} border-emerald-500 text-slate-300 shadow-[0_0_15px_rgba(16,185,129,0.4)]`;
  };

  const getTooltipData = (nodeName) => {
    const latest = metrics[metrics.length - 1];
    if (!latest || !latest.node_allocations) return { compute: 0, spectrum: 0, storage: 0 };
    return latest.node_allocations.find(n => n.name === nodeName) || { compute: 0, spectrum: 0, storage: 0 };
  };

  const getLinkProps = (nodeName, defaultText) => {
    const data = getTooltipData(nodeName);
    if (data.compute > 85) {
      return { stroke: "#f43f5e", strokeWidth: 6, opacity: "opacity-80", textFill: "#f43f5e", text: `Util: ${data.compute}%` };
    } else if (data.compute > 60) {
      return { stroke: "#f59e0b", strokeWidth: 4, opacity: "opacity-70", textFill: "#f59e0b", text: `Util: ${data.compute}%` };
    }
    return { stroke: "#334155", strokeWidth: 3, opacity: "opacity-100", textFill: "#64748b", text: defaultText };
  };

  const getLayout = (config) => {
    const { ru, du } = config;
    const nodes = [];
    const links = [];

    // CU is always 1, put it on the right side
    const cuX = 600;
    const cuY = 175;
    nodes.push({ id: 'CU-Core', x: cuX, y: cuY });

    // DUs in the middle
    const duX = 400;
    const duSpacing = 350 / (du + 1); // Adjust spacing for better distribution
    for (let i = 0; i < du; i++) {
      const y = 30 + (i + 1) * duSpacing;
      nodes.push({ id: `DU-${i + 1}`, x: duX, y });
      // Link to CU (Index 0)
      links.push({ source: nodes.length - 1, target: 0, label: 'F1/E2' });
    }

    // RUs on the left
    const ruX = 150;
    const ruSpacing = 350 / (ru + 1); // Adjust spacing for better distribution
    for (let i = 0; i < ru; i++) {
      const y = 30 + (i + 1) * ruSpacing;
      nodes.push({ id: `RU-${i + 1}`, x: ruX, y });
      // Connect each RU to a DU (distribute evenly)
      const targetDuIndex = 1 + (i % du); // 1 is index of first DU
      links.push({ source: nodes.length - 1, target: targetDuIndex, label: '5G NR' });
    }

    return { nodes, links };
  };

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
          <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-4 relative overflow-hidden backdrop-blur-sm shadow-xl h-[800px]">
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
            <div className="absolute inset-0 top-12 flex items-center justify-center pointer-events-none opacity-20 z-0">
              <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
                <path d="M0,0 L100,100 M100,0 L0,100 M50,0 L50,100 M0,50 L100,50" stroke="#334155" strokeWidth="0.5" strokeDasharray="2,2" />
              </svg>
            </div>

            {/* Simulated Nodes & Links */}
            <div className="absolute inset-0 top-16 flex items-center justify-center z-10 transition-transform duration-500 scale-150 lg:scale-[1.7] origin-center">
              <div className="relative w-[700px] h-[350px]">
                {/* Lines (Edges) */}
                <svg className="absolute inset-0 w-full h-full pb-4">
                  {(() => {
                    const layout = getLayout(appliedConfig);
                    return layout.links.map((link, idx) => {
                      const source = layout.nodes[link.source];
                      const target = layout.nodes[link.target];
                      const p = getLinkProps(target.id, link.label);
                      return (
                        <g key={idx}>
                          <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke={p.stroke} strokeWidth={p.strokeWidth} className={`transition-all duration-500 ${p.opacity}`} />
                          <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 10} fill={p.textFill} fontSize="10" textAnchor="middle" className="transition-colors duration-500">{p.text}</text>
                        </g>
                      );
                    });
                  })()}
                </svg>

                {/* Nodes rendering using absolute positioning */}
                {(() => {
                  const layout = getLayout(appliedConfig);
                  return layout.nodes.map((n, idx) => {
                    const isRU = n.id.startsWith('RU');
                    const isDU = n.id.startsWith('DU');
                    const sizeClass = isRU ? 'w-16 h-16 text-xs' : (isDU ? (n.id.includes('Core') ? 'w-24 h-24 text-base' : 'w-20 h-20 text-sm') : 'w-20 h-20 text-sm');
                    const borderClass = isRU ? 'border-[3px]' : (isDU && n.id.includes('Core') ? 'border-[5px]' : 'border-[4px]');

                    return (
                      <div key={idx} className="absolute flex flex-col items-center group cursor-pointer z-30" style={{ top: n.y, left: n.x, transform: 'translate(-50%, -50%)' }}>
                        <div className={getNodeColorClass(n.id, `${sizeClass} ${borderClass} rounded-full bg-slate-900 flex items-center justify-center font-bold transition-all duration-300`)}>{n.id}</div>
                        <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 bg-slate-950/90 border border-slate-700 py-1.5 px-3 rounded-lg text-xs whitespace-nowrap backdrop-blur-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                          <div className="text-slate-400">Compute: <span className="text-cyan-400 font-mono">{getTooltipData(n.id).compute}%</span></div>
                          <div className="text-slate-400">Spectrum: <span className="text-purple-400 font-mono">{getTooltipData(n.id).spectrum} PRBs</span></div>
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>
            </div>
          </div>

          {/* Bottom Panels Row (DDPG & RAFT) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-[160px] shrink-0">

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
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${trainingMode === 'Train' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
                  >Train</button>
                  <button
                    onClick={() => setTrainingMode('Eval')}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${trainingMode === 'Eval' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
                  >Evaluate</button>
                </div>
              </div>

              <div className="flex gap-4 text-[10px] text-slate-400 mb-2 px-2">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-purple-500"></span>Critic Loss</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-cyan-500"></span>Total Reward</span>
              </div>

              <div className="flex-1 w-full min-h-[70px]">
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

              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">RUs Online</div>
                  <div className="text-cyan-400 font-mono text-xs flex items-center gap-2">
                    {appliedConfig.ru} Radio Units
                  </div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">DUs Active</div>
                  <div className="text-green-400 font-mono text-xs flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                    {appliedConfig.du} (Tol: {Math.floor((appliedConfig.du - 1) / 2)})
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

              <div className="flex-1 bg-slate-950/80 rounded-lg p-2 overflow-hidden border border-slate-800/80 font-mono text-[10px] space-y-1 relative shadow-inner">
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
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">RUs (Radio Units)</label>
                        <select value={configRu} onChange={(e) => setConfigRu(Number(e.target.value))} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-cyan-500 shadow-inner font-mono appearance-none cursor-pointer">
                          {[3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(num => (
                            <option key={`ru-${num}`} value={num}>{num} RUs {num === 5 ? '(Default)' : ''}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">DUs (Distributed Units)</label>
                        <select value={configDu} onChange={(e) => setConfigDu(Number(e.target.value))} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-cyan-500 shadow-inner font-mono appearance-none cursor-pointer">
                          {[3, 5, 7, 9].map(num => (
                            <option key={`du-${num}`} value={num}>{num} DUs {num === 5 ? '(Default)' : ''}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Max UEs / Cell</label>
                      <input type="number" value={configUes} onChange={(e) => setConfigUes(Number(e.target.value))} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-cyan-500 shadow-inner font-mono" />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-1.5">
                      <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Cloud Sync Interval</label>
                      <span className="text-xs text-cyan-400 font-mono">{syncInterval}s</span>
                    </div>
                    <input type="range" min="1" max="60" value={syncInterval} onChange={(e) => setSyncInterval(e.target.value)} className="w-full accent-cyan-500 h-1.5 rounded-lg appearance-none bg-slate-800 cursor-pointer" />
                  </div>

                  {/* Stress Testing Section */}
                  <div className="pt-4 border-t border-slate-800/60 mb-1">
                    <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide flex items-center gap-1 mb-2">
                      <AlertTriangle className="w-3 h-3 text-rose-500" />
                      Stress Testing
                    </div>
                    <div className="flex gap-2">
                      <select
                        className="bg-slate-950 border border-slate-700/50 rounded-lg p-2 text-xs text-slate-300 w-1/3 outline-none focus:border-cyan-500 shadow-inner appearance-none cursor-pointer"
                        value={selectedSpikeNode}
                        onChange={(e) => setSelectedSpikeNode(e.target.value)}
                      >
                        {getLayout(appliedConfig).nodes.map((n) => (
                          <option key={n.id} value={n.id}>{n.id}</option>
                        ))}
                      </select>
                      <button
                        onClick={fireSpikeCommand}
                        className="flex-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 hover:border-rose-500/50 font-semibold py-2 px-3 rounded-lg text-xs transition-all active:scale-[0.98]"
                      >
                        Inject Workload Spike
                      </button>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-2 italic leading-tight">Floods selected node with 500% PRB demand to test scheduling rebalancing.</div>
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
                <div className="flex flex-col h-full space-y-4">
                  <div className="flex justify-between items-center mb-2">
                    <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Select Node Trace</label>
                    <select
                      className="bg-slate-950 border border-slate-700/50 rounded-lg p-1.5 text-xs text-slate-300 w-1/2 outline-none focus:border-cyan-500 shadow-inner appearance-none cursor-pointer"
                      value={selectedSpikeNode}
                      onChange={(e) => setSelectedSpikeNode(e.target.value)}
                    >
                      {getLayout(appliedConfig).nodes.map((n) => (
                        <option key={n.id} value={n.id}>{n.id}</option>
                      ))}
                    </select>
                  </div>

                  <div className="flex gap-4 text-[9px] font-mono text-slate-400 mb-1 justify-center">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-cyan-400"></span>CPU (%)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-fuchsia-400"></span>Mem (MB)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-400"></span>PRB</span>
                  </div>

                  <div className="flex-1 w-full min-h-[220px] bg-slate-950/50 rounded-lg border border-slate-800/80 p-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={activeHistoryData} margin={{ top: 5, right: 0, left: -25, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                        <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="left" tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} width={35} />
                        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} width={35} />
                        <Tooltip
                          contentStyle={{ backgroundColor: 'rgba(2, 6, 23, 0.9)', borderColor: '#1e293b', borderRadius: '8px', fontSize: '10px' }}
                          itemStyle={{ color: '#cbd5e1' }}
                        />
                        <Line yAxisId="left" type="monotone" dataKey="CPU" stroke="#22d3ee" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line yAxisId="left" type="monotone" dataKey="Storage" stroke="#e879f9" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line yAxisId="right" type="monotone" dataKey="Spectrum" stroke="#34d399" strokeWidth={2} dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <button onClick={handleExportCSV} disabled={isExporting} className="w-full px-4 py-2 border border-slate-700/50 rounded-lg text-xs hover:bg-slate-800 transition-colors mt-auto font-medium shadow-inner flex items-center justify-center gap-2">
                    {isExporting ? <div className="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin"></div> : <History className="w-3 h-3" />}
                    {isExporting ? 'Exporting...' : 'Export Telemetry CSV'}
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

    </div >
  );
};

export default App;
