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
  // Start empty - metrics will fill as data arrives (max 60 data points for 1 minute of history at 1Hz)
  const MAX_HISTORY = 60;
  const [metrics, setMetrics] = useState([]);
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
    // Simulate config delay - don't clear metrics to preserve history
    setTimeout(() => {
      setIsApplying(false);
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
  // Only include data points that have node_allocations for continuous lines
  const activeHistoryData = metrics
    .filter(m => m.node_allocations && m.node_allocations.length > 0)
    .map((m, idx) => {
      const found = m.node_allocations.find(n => n.name === selectedSpikeNode);
      const nodeData = found || { compute: 0, storage: 0, spectrum: 0 };
      return {
        time: idx, // Use sequential index for smooth X-axis
        CPU: nodeData.compute,
        Storage: nodeData.storage,
        Spectrum: nodeData.spectrum
      };
    });

  useEffect(() => {
    if (lastJsonMessage) {
      if (lastJsonMessage.type === "METRICS") {
        setMetrics(prev => {
          // Keep up to MAX_HISTORY data points for continuous line charts
          const newArr = prev.length >= MAX_HISTORY ? [...prev.slice(1), lastJsonMessage] : [...prev, lastJsonMessage];
          metricsRef.current = newArr;
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
    if (!latest || !latest.node_allocations) return `${defaultClasses} border-emerald-600/50 text-slate-300 shadow-[0_0_15px_rgba(16,185,129,0.15)]`;

    const node = latest.node_allocations.find(n => n.name === nodeName);
    if (!node) return `${defaultClasses} border-emerald-600/50 text-slate-300 shadow-[0_0_15px_rgba(16,185,129,0.15)]`;

    if (node.compute > 85) {
      return `${defaultClasses} border-rose-500/80 text-rose-100 shadow-[0_0_25px_rgba(244,63,94,0.4)] animate-[pulse_2s_infinite]`;
    } else if (node.compute > 60) {
      return `${defaultClasses} border-amber-500/80 text-amber-100 shadow-[0_0_20px_rgba(245,158,11,0.25)]`;
    }
    return `${defaultClasses} border-emerald-600/60 text-emerald-50 shadow-[0_0_15px_rgba(16,185,129,0.2)]`;
  };

  const getTooltipData = (nodeName) => {
    const latest = metrics[metrics.length - 1];
    if (!latest || !latest.node_allocations) return { compute: 0, spectrum: 0, storage: 0 };
    return latest.node_allocations.find(n => n.name === nodeName) || { compute: 0, spectrum: 0, storage: 0 };
  };

  const getLinkProps = (nodeName, defaultText) => {
    const data = getTooltipData(nodeName);
    if (data.compute > 85) {
      return { stroke: "#f43f5e", strokeWidth: 6, opacity: "opacity-60", textFill: "#f43f5e", text: `Util: ${data.compute}%` };
    } else if (data.compute > 60) {
      return { stroke: "#f59e0b", strokeWidth: 4, opacity: "opacity-50", textFill: "#f59e0b", text: `Util: ${data.compute}%` };
    }
    return { stroke: "#1e293b", strokeWidth: 3, opacity: "opacity-100", textFill: "#475569", text: defaultText };
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
          <div className="p-2 bg-emerald-950/50 rounded-lg border border-emerald-800 shadow-[0_0_15px_rgba(16,185,129,0.15)]">
            <Network className="w-6 h-6 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-emerald-100 to-teal-400 bg-clip-text text-transparent tracking-wide">
              5G RESOURCE SCHEDULER
            </h1>
            <p className="text-xs text-slate-500 tracking-wider">DRS-SIM v3.1 | DISTRIBUTED EDGE ENGINE</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 rounded-full border border-slate-800 text-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-500/80 animate-pulse"></span>
            <span className="text-emerald-500 font-medium">System Online</span>
          </div>
          <button className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400 hover:text-emerald-400">
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
                <Wifi className="w-5 h-5 text-emerald-500" />
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
                  const currentLeader = metrics[metrics.length - 1]?.raft_leader || 'DU-1';
                  return layout.nodes.map((n, idx) => {
                    const isRU = n.id.startsWith('RU');
                    const isDU = n.id.startsWith('DU');
                    const isLeader = n.id === currentLeader;
                    const sizeClass = isRU ? 'w-16 h-16 text-xs' : (isDU ? (n.id.includes('Core') ? 'w-24 h-24 text-base' : 'w-20 h-20 text-sm') : 'w-20 h-20 text-sm');
                    const borderClass = isRU ? 'border-[3px]' : (isDU && n.id.includes('Core') ? 'border-[5px]' : 'border-[4px]');
                    const tooltipData = getTooltipData(n.id);
                    const computeColor = tooltipData.compute > 85 ? '#f43f5e' : tooltipData.compute > 60 ? '#f59e0b' : '#10b981';
                    const storageColor = tooltipData.storage > 85 ? '#f43f5e' : tooltipData.storage > 60 ? '#f59e0b' : '#64748b';
                    const spectrumColor = '#059669';

                    // Leader DU gets gold border + glow override
                    const leaderClass = isLeader
                      ? `${sizeClass} border-[4px] border-amber-400/80 text-amber-100 shadow-[0_0_20px_rgba(245,158,11,0.3)] rounded-full bg-slate-900 flex items-center justify-center font-bold transition-all duration-300 relative z-10`
                      : getNodeColorClass(n.id, `${sizeClass} ${borderClass} rounded-full bg-slate-900 flex items-center justify-center font-bold transition-all duration-300 relative z-10`);

                    return (
                      <div key={idx} className="absolute flex flex-col items-center group cursor-pointer z-30" style={{ top: n.y, left: n.x, transform: 'translate(-50%, -50%)' }}>
                        {/* Crown badge for RAFT leader */}
                        {isLeader && (
                          <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-amber-400 text-sm z-50 animate-bounce" title="RAFT Leader">
                            👑
                          </div>
                        )}
                        {/* Follower badge for non-leader DUs */}
                        {isDU && !isLeader && (
                          <div className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-bold text-slate-500 bg-slate-800 border border-slate-700 rounded px-1 z-50">
                            F
                          </div>
                        )}
                        <div className={leaderClass}>{n.id}</div>
                        {/* Resource usage panel - appears beside the node on hover */}
                        <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 bg-slate-950/95 border-2 border-emerald-600/40 py-2.5 px-3.5 rounded-xl text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-all duration-200 pointer-events-none z-40 shadow-2xl min-w-[160px]">
                          {/* Arrow pointing left */}
                          <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-full w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-r-[8px] border-r-emerald-600/40"></div>
                          <div className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider mb-2 border-b border-slate-800 pb-1 flex items-center gap-1">
                            {n.id} Resources
                            {isLeader && <span className="text-amber-400 ml-1">👑 Leader</span>}
                          </div>
                          {/* Compute */}
                          <div className="mb-1.5">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-slate-400 text-[11px] font-medium">Compute</span>
                              <span className="font-mono font-bold text-[12px]" style={{ color: computeColor }}>{tooltipData.compute}%</span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${tooltipData.compute}%`, backgroundColor: computeColor }}></div>
                            </div>
                          </div>
                          {/* Storage */}
                          <div className="mb-1.5">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-slate-400 text-[11px] font-medium">Storage</span>
                              <span className="font-mono font-bold text-[12px]" style={{ color: storageColor }}>{tooltipData.storage} MB</span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${tooltipData.storage}%`, backgroundColor: storageColor }}></div>
                            </div>
                          </div>
                          {/* Spectrum */}
                          <div>
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-slate-400 text-[11px] font-medium">Spectrum</span>
                              <span className="font-mono font-bold text-[12px]" style={{ color: spectrumColor }}>{tooltipData.spectrum} PRBs</span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, tooltipData.spectrum / 4)}%`, backgroundColor: spectrumColor }}></div>
                            </div>
                          </div>
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
                  <Activity className="w-4 h-4 text-teal-400" />
                  1) DDPG Training Monitor
                </h3>
                <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-lg p-1">
                  <button
                    onClick={() => setTrainingMode('Train')}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${trainingMode === 'Train' ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
                  >Train</button>
                  <button
                    onClick={() => setTrainingMode('Eval')}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${trainingMode === 'Eval' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
                  >Evaluate</button>
                </div>
              </div>

              <div className="flex gap-4 text-[10px] text-slate-400 mb-2 px-2">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-teal-600"></span>Critic Loss</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-500"></span>Total Reward</span>
              </div>

              <div className="flex-1 w-full min-h-[70px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={ddpgData} margin={{ top: 5, right: 0, left: -20, bottom: 5 }}>
                    <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={40} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip
                      contentStyle={{ backgroundColor: 'rgba(2, 6, 23, 0.95)', borderColor: '#1e293b', borderRadius: '8px', fontSize: '11px', backdropFilter: 'blur(4px)' }}
                      itemStyle={{ color: '#cbd5e1' }}
                    />
                    <Line yAxisId="left" type="monotone" dataKey="criticLoss" stroke="#0d9488" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                    <Line yAxisId="right" type="monotone" dataKey="reward" stroke="#10b981" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* RAFT Consensus View */}
            <div className="bg-slate-900/40 rounded-xl border border-slate-800 p-4 flex flex-col shadow-lg backdrop-blur-sm">
              <div className="flex justify-between items-center mb-4 text-slate-200">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <Server className="w-4 h-4 text-emerald-400" />
                  2) RAFT Consensus View
                </h3>
              </div>

              <div className="grid grid-cols-4 gap-3 mb-3">
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">RUs Online</div>
                  <div className="text-emerald-500/80 font-mono text-xs flex items-center gap-2">
                    {appliedConfig.ru} Radio Units
                  </div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">DUs Active</div>
                  <div className="text-teal-500/80 font-mono text-xs flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-teal-500/60 animate-pulse"></span>
                    {appliedConfig.du} (Tol: {Math.floor((appliedConfig.du - 1) / 2)})
                  </div>
                </div>
                {/* RAFT Leader Card */}
                <div className="bg-amber-950/20 border border-amber-500/20 rounded-lg p-2 flex flex-col justify-center shadow-lg">
                  <div className="text-[10px] text-amber-500/70 uppercase tracking-wider font-semibold mb-1 flex items-center gap-1">
                    <span>👑</span> RAFT Leader
                  </div>
                  <div className="text-amber-200/90 font-mono text-xs font-bold tracking-wide">
                    {metrics[metrics.length - 1]?.raft_leader || 'DU-1'}
                  </div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2 flex flex-col justify-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1">Global State</div>
                  <div className="text-slate-400 font-mono text-xs flex justify-between">
                    <span>T: <span className="text-emerald-500/80">{metrics[metrics.length - 1]?.raft_term || 452}</span></span>
                    <span>Idx: <span className="text-teal-500/80">{(metrics[metrics.length - 1]?.raft_log_index || 18970).toLocaleString()}</span></span>
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
                className={`flex-1 py-3 text-sm font-medium transition-all ${activeTab === 'config' ? 'bg-slate-800/80 text-emerald-400 border-t-2 border-emerald-400 shadow-inner text-shadow-sm shadow-emerald-500/20' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-900'}`}
                onClick={() => setActiveTab('config')}
              >
                Configuration
              </button>
              <button
                className={`flex-1 py-3 text-sm font-medium transition-all border-l border-slate-800 ${activeTab === 'history' ? 'bg-slate-800/80 text-teal-400 border-t-2 border-teal-400 shadow-inner text-shadow-sm shadow-teal-500/20' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-900'}`}
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
                    <select className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-emerald-500 transition-colors shadow-inner appearance-none cursor-pointer">
                      <option>DDPG Edge AI (Active)</option>
                      <option>Stackelberg Game Theory</option>
                      <option>Static Capacity PF</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">RUs (Radio Units)</label>
                        <select value={configRu} onChange={(e) => setConfigRu(Number(e.target.value))} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-emerald-500 shadow-inner font-mono appearance-none cursor-pointer">
                          {[3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(num => (
                            <option key={`ru-${num}`} value={num}>{num} RUs {num === 5 ? '(Default)' : ''}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">DUs (Distributed Units)</label>
                        <select value={configDu} onChange={(e) => setConfigDu(Number(e.target.value))} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-emerald-500 shadow-inner font-mono appearance-none cursor-pointer">
                          {[3, 5, 7, 9].map(num => (
                            <option key={`du-${num}`} value={num}>{num} DUs {num === 5 ? '(Default)' : ''}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Max UEs / Cell</label>
                      <input type="number" value={configUes} onChange={(e) => setConfigUes(Number(e.target.value))} className="w-full bg-slate-950/80 border border-slate-700/50 rounded-lg p-2.5 text-sm text-slate-200 outline-none focus:border-emerald-500 shadow-inner font-mono" />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-1.5">
                      <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Cloud Sync Interval</label>
                      <span className="text-xs text-emerald-400 font-mono">{syncInterval}s</span>
                    </div>
                    <input type="range" min="1" max="60" value={syncInterval} onChange={(e) => setSyncInterval(e.target.value)} className="w-full accent-emerald-500 h-1.5 rounded-lg appearance-none bg-slate-800 cursor-pointer" />
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
                    className={`w-full mt-2 font-medium py-2.5 rounded-lg shadow-xl transition-all flex justify-center items-center gap-2 border border-emerald-400/20 active:scale-[0.98] ${isApplying ? 'bg-emerald-800/80 text-emerald-100 cursor-wait' : 'bg-gradient-to-r from-emerald-600 to-teal-700 hover:from-emerald-500 hover:to-teal-600 text-white'}`}
                  >
                    {isApplying ? <div className="w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></div> : <Settings className="w-4 h-4" />}
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
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-500"></span>CPU (%)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-teal-500"></span>Mem (MB)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-slate-500"></span>PRB</span>
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
                        <Line yAxisId="left" type="monotone" dataKey="CPU" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line yAxisId="left" type="monotone" dataKey="Storage" stroke="#0d9488" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line yAxisId="right" type="monotone" dataKey="Spectrum" stroke="#64748b" strokeWidth={2} dot={false} isAnimationActive={false} />
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
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="monotone" dataKey="throughput" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorTp)" isAnimationActive={false} />
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
                          <stop offset="5%" stopColor="#0d9488" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#0d9488" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="step" dataKey="latency" stroke="#0d9488" strokeWidth={2} fillOpacity={1} fill="url(#colorLat)" isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                {/* Metric: Users */}
                <div className="bg-slate-950/50 border border-slate-800/50 p-2 rounded-lg flex flex-col items-center justify-center">
                  <div className="text-[10px] text-slate-400 mb-1">Active UEs</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono tracking-tighter">{metrics[metrics.length - 1]?.users || 0}</div>
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
                    <div className="bg-emerald-500 h-full transition-all duration-500" style={{ width: `${metrics[metrics.length - 1]?.tdd_dl || 50}%` }}></div>
                    <div className="bg-teal-600 h-full transition-all duration-500" style={{ width: `${metrics[metrics.length - 1]?.tdd_ul || 50}%` }}></div>
                  </div>
                  <div className="flex justify-between w-full text-[9px] font-mono font-bold">
                    <span className="text-emerald-400/90">DL: {metrics[metrics.length - 1]?.tdd_dl || 50}%</span>
                    <span className="text-teal-500/90">UL: {metrics[metrics.length - 1]?.tdd_ul || 50}%</span>
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
                      <Bar dataKey="spectrum" name="Spectrum (PRBs)" fill="#059669" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="compute" name="Compute (%)" fill="#0d9488" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="storage" name="Storage (Buffer MB)" fill="#64748b" radius={[2, 2, 0, 0]} />
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
              {log.level === 'INFO' && <span className="text-emerald-500 font-bold">{log.ts} | INFO</span>}
              {log.msg}
            </span>
          ))}
          {/* Duplicate for infinite effect */}
          {logs.map((log, i) => (
            <span key={`ticker-dup-${i}`} className={`flex items-center gap-2 ${log.level === 'CRIT' ? 'text-rose-200' : 'text-slate-300'}`}>
              {log.level === 'CRIT' && <span className="text-rose-500 font-bold">{log.ts} | CRIT</span>}
              {log.level === 'WARN' && <span className="text-amber-500 font-bold">{log.ts} | WARN</span>}
              {log.level === 'INFO' && <span className="text-emerald-500 font-bold">{log.ts} | INFO</span>}
              {log.msg}
            </span>
          ))}
        </div>
      </div>

    </div >
  );
};

export default App;
