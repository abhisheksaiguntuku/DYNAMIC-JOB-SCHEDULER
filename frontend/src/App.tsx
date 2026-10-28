import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { 
  Cpu, FastForward, PlusCircle, 
  Layers, Activity, BarChart2, Zap,
  Clock, AlertTriangle, CheckCircle, RefreshCw,
  Search, Filter, Trash2, X, Plus, Info
} from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001/api').replace(/\/+$/, '');

interface Machine {
  machine_id: string;
  name: string;
  capability: string;
  status: string;
  current_job_id: string | null;
  current_operation_seq: number | null;
  remaining_processing_time: number;
}

interface Operation {
  sequence: number;
  name: string;
  machine_id: string;
  duration: number;
  status: string;
  start_time?: number | null;
  end_time?: number | null;
  setup_time?: number;
}

interface Job {
  job_id: string;
  name: string;
  product_type: string;
  quantity: number;
  arrival_time: number;
  due_date: number;
  priority: number;
  status: string;
  operations: Operation[];
}

interface ScheduledTask {
  job_id: string;
  job_name: string;
  operation_sequence: number;
  operation_name: string;
  machine_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  is_running: boolean;
  is_completed: boolean;
}

interface ScheduleResult {
  schedule_id: string;
  algorithm: string;
  created_at_sim_time: number;
  tasks: ScheduledTask[];
  metrics: {
    makespan: number;
    total_tardiness: number;
    max_tardiness: number;
    late_jobs_count: number;
    avg_waiting_time: number;
    avg_utilization: number;
    computation_time_ms: number;
    solver_status: string;
    machine_utilization?: Record<string, number>;
  };
  explanation: any;
}

// Lifecycle Status Enum / Types
type LifecycleStatus = 'COMPLETED' | 'IN_PROGRESS' | 'NEAR_COMPLETION' | 'LATE_AT_RISK' | 'QUEUED';

interface JobLifecycleView {
  job: Job;
  lifecycleStatus: LifecycleStatus;
  statusLabel: string;
  statusColor: string;
  statusBg: string;
  completedOps: number;
  totalOps: number;
  currentOpName: string;
  assignedMachine: string;
  actualOrSimStart: number | null;
  estimatedCompletion: number | null;
  remainingProcessing: number;
  dueTime: number;
  isLate: boolean;
  isAtRisk: boolean;
}

export default function App() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [schedule, setSchedule] = useState<ScheduleResult | null>(null);
  const [comparison, setComparison] = useState<any>(null);
  const [recommendation, setRecommendation] = useState<any>(null);
  const [simStatus, setSimStatus] = useState<any>({ sim_time: 0 });
  const [selectedAlgo, setSelectedAlgo] = useState('CPSAT');
  const [loading, setLoading] = useState(false);
  const [showAddJob, setShowAddJob] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Lifecycle Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [machineFilter, setMachineFilter] = useState<string>('ALL');

  // Gantt Hover Tooltip
  const [hoveredTask, setHoveredTask] = useState<ScheduledTask | null>(null);

  // New Job Form State
  const [newJob, setNewJob] = useState({
    job_id: `JOB_DYN_${Math.floor(100 + Math.random() * 900)}`,
    name: '',
    product_type: 'Custom Fabricated Component',
    quantity: 1,
    arrival_time: 0,
    due_date: 250,
    priority: 3,
    operations: [
      { sequence: 1, name: 'Pattern Making', machine_id: 'M1', duration: 0, status: 'PENDING' }
    ]
  });

  const fetchData = async () => {
    try {
      const [mRes, jRes, simRes, recRes] = await Promise.all([
        axios.get(`${API_BASE}/machines`),
        axios.get(`${API_BASE}/jobs`),
        axios.get(`${API_BASE}/simulation/status`),
        axios.get(`${API_BASE}/ml/recommend`)
      ]);
      setMachines(mRes.data);
      setJobs(jRes.data);
      setSimStatus(simRes.data);
      setRecommendation(recRes.data);
    } catch (e: any) {
      console.error("Error fetching data", e);
    }
  };

  const runRecalculation = async (algo = selectedAlgo) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await axios.post(`${API_BASE}/schedules/recalculate?algorithm=${algo}`);
      setSchedule(res.data);
      const compRes = await axios.get(`${API_BASE}/schedules/compare`);
      setComparison(compRes.data);
      await fetchData();
    } catch (e: any) {
      console.error(e);
      setErrorMessage(e.response?.data?.detail || "Recalculation failed.");
    } finally {
      setLoading(false);
    }
  };

  const advanceSim = async (mins: number) => {
    try {
      await axios.post(`${API_BASE}/simulation/advance?step_minutes=${mins}`);
      await runRecalculation();
    } catch (e: any) {
      console.error(e);
    }
  };

  const toggleMachineDowntime = async (m: Machine) => {
    setErrorMessage(null);
    try {
      if (m.status === 'DOWN' || m.status === 'MAINTENANCE') {
        await axios.post(`${API_BASE}/machines/${m.machine_id}/recover`);
      } else {
        await axios.post(`${API_BASE}/machines/${m.machine_id}/downtime?duration=20`);
      }
      await runRecalculation();
    } catch (e: any) {
      setErrorMessage(e.response?.data?.detail || "Machine state update failed.");
    }
  };

  const resetToDemo = async () => {
    if (!window.confirm("Reset all jobs to the original 10 baseline demo jobs? Any newly registered dynamic jobs will be removed. Benchmarks remain completely preserved.")) {
      return;
    }
    try {
      setLoading(true);
      await axios.post(`${API_BASE}/data/reset-demo`);
      await runRecalculation();
    } catch (e: any) {
      alert("Failed to reset demo: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  // Add Operation to Form
  const handleAddOperation = () => {
    setNewJob(prev => {
      const nextSeq = prev.operations.length + 1;
      // Default to next machine modulo 10
      const defaultMachine = machines.length > 0 
        ? machines[(nextSeq - 1) % machines.length].machine_id 
        : 'M1';
      const mObj = machines.find(m => m.machine_id === defaultMachine);
      const opName = mObj ? mObj.capability : `Stage ${nextSeq}`;
      return {
        ...prev,
        operations: [
          ...prev.operations,
          {
            sequence: nextSeq,
            name: opName,
            machine_id: defaultMachine,
            duration: 0, // Explicitly 0 placeholder, user must enter > 0
            status: 'PENDING'
          }
        ]
      };
    });
  };

  // Remove Operation from Form
  const handleRemoveOperation = (index: number) => {
    if (newJob.operations.length <= 1) {
      alert("A job must contain at least one operation.");
      return;
    }
    setNewJob(prev => {
      const filtered = prev.operations.filter((_, i) => i !== index);
      // Re-index sequences
      const reindexed = filtered.map((op, idx) => ({ ...op, sequence: idx + 1 }));
      return { ...prev, operations: reindexed };
    });
  };

  // Form Submission Validation
  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    // Validation 1: Job ID
    if (!newJob.job_id.trim()) {
      alert("Job ID cannot be blank.");
      return;
    }

    // Validation 2: Job Name
    if (!newJob.name.trim()) {
      alert("Job name / product name cannot be blank.");
      return;
    }

    // Validation 3: Operations count
    if (newJob.operations.length === 0) {
      alert("A job must contain at least one operation.");
      return;
    }

    // Validation 4: Positive duration check
    for (const op of newJob.operations) {
      if (op.duration <= 0) {
        alert(`Operation ${op.sequence} (${op.name}) duration must be greater than zero minutes. (Zero is just a placeholder).`);
        return;
      }
      if (!op.machine_id) {
        alert(`Operation ${op.sequence} must have an eligible machine selected.`);
        return;
      }
    }

    // Validation 5: Due date
    if (newJob.due_date <= 0) {
      alert("Due date must be a positive number of minutes.");
      return;
    }

    try {
      await axios.post(`${API_BASE}/jobs`, newJob);
      setShowAddJob(false);
      await runRecalculation();
      // Generate next random ID and reset form with empty positive fields
      setNewJob({
        job_id: `JOB_DYN_${Math.floor(100 + Math.random() * 900)}`,
        name: '',
        product_type: 'Custom Component',
        quantity: 1,
        arrival_time: simStatus.sim_time,
        due_date: simStatus.sim_time + 200,
        priority: 3,
        operations: [
          { sequence: 1, name: 'Pattern Making', machine_id: 'M1', duration: 0, status: 'PENDING' }
        ]
      });
    } catch (e: any) {
      alert(e.response?.data?.detail || "Failed to add job.");
    }
  };

  useEffect(() => {
    fetchData();
    runRecalculation('CPSAT');
  }, []);

  // Compute Job Lifecycle States
  const currentSim = simStatus.sim_time || 0;
  const scheduledTasks = schedule?.tasks || [];

  const lifecycleData: JobLifecycleView[] = useMemo(() => {
    return jobs.map(j => {
      const ops = j.operations || [];
      const totalOps = ops.length;
      const completedOps = ops.filter(o => o.status === 'COMPLETED').length;
      const runningOp = ops.find(o => o.status === 'RUNNING');
      const pendingOps = ops.filter(o => o.status === 'PENDING');

      // Remaining duration
      const remainingProcessing = ops.reduce((acc, op) => {
        if (op.status === 'COMPLETED') return acc;
        if (op.status === 'RUNNING') {
          const m = machines.find(mach => mach.machine_id === op.machine_id);
          return acc + (m ? m.remaining_processing_time : op.duration);
        }
        return acc + op.duration;
      }, 0);

      // Estimated completion from schedule
      const jTasks = scheduledTasks.filter(t => t.job_id === j.job_id);
      const estimatedCompletion = jTasks.length > 0 
        ? Math.max(...jTasks.map(t => t.end_time))
        : null;

      // Start time
      const actualOrSimStart = jTasks.length > 0 
        ? Math.min(...jTasks.map(t => t.start_time))
        : (ops[0]?.start_time ?? null);

      // Current op & machine
      let currentOpName = 'All Completed';
      let assignedMachine = '-';
      if (runningOp) {
        currentOpName = `Op ${runningOp.sequence}: ${runningOp.name}`;
        assignedMachine = runningOp.machine_id;
      } else if (pendingOps.length > 0) {
        currentOpName = `Op ${pendingOps[0].sequence}: ${pendingOps[0].name}`;
        assignedMachine = pendingOps[0].machine_id;
      }

      // 1. Fully Completed: All operations completed or marked completed
      const isCompleted = j.status === 'COMPLETED' || (totalOps > 0 && completedOps === totalOps);

      // 2. Really started with unfinished work remaining (cannot be completed)
      const hasStartedUnfinished = !isCompleted && totalOps > 0 && completedOps < totalOps && (
        Boolean(runningOp) || completedOps > 0
      );

      // 3. Near completion: has started, still has unfinished work, and meets >= 70% ops done or <= 35m remaining
      const isNearCompletion = hasStartedUnfinished && (
        (totalOps > 1 && (completedOps / totalOps) >= 0.70) ||
        remainingProcessing <= 35.0
      );

      // 4. In Progress: has started with unfinished work, but has not yet reached Near Completion
      const isInProgress = hasStartedUnfinished && !isNearCompletion;

      // 5. Late / At Risk definitions
      const isLateAlready = !isCompleted && currentSim > j.due_date;
      const isPredictedLate = !isCompleted && estimatedCompletion !== null && estimatedCompletion > j.due_date;
      const isAtRisk = isLateAlready || isPredictedLate;

      let lifecycleStatus: LifecycleStatus = 'QUEUED';
      let statusLabel = 'Queued';
      let statusColor = '#38bdf8';
      let statusBg = 'rgba(56, 189, 248, 0.15)';

      if (isCompleted) {
        lifecycleStatus = 'COMPLETED';
        statusLabel = 'Completed';
        statusColor = '#10b981';
        statusBg = 'rgba(16, 185, 129, 0.15)';
      } else if (isNearCompletion) {
        lifecycleStatus = 'NEAR_COMPLETION';
        statusLabel = 'Near Completion';
        statusColor = '#a855f7';
        statusBg = 'rgba(168, 85, 247, 0.18)';
      } else if (isInProgress) {
        lifecycleStatus = 'IN_PROGRESS';
        statusLabel = 'In Progress';
        statusColor = '#eab308';
        statusBg = 'rgba(234, 179, 8, 0.15)';
      } else {
        lifecycleStatus = 'QUEUED';
        statusLabel = 'Queued';
        statusColor = '#38bdf8';
        statusBg = 'rgba(56, 189, 248, 0.15)';
      }

      return {
        job: j,
        lifecycleStatus,
        statusLabel,
        statusColor,
        statusBg,
        completedOps,
        totalOps,
        currentOpName,
        assignedMachine,
        actualOrSimStart,
        estimatedCompletion,
        remainingProcessing: round1(remainingProcessing),
        dueTime: j.due_date,
        isLate: isLateAlready,
        isAtRisk
      };
    });
  }, [jobs, machines, scheduledTasks, currentSim]);

  // Filtered Lifecycle Data
  const filteredLifecycle = useMemo(() => {
    return lifecycleData.filter(item => {
      // Search
      const matchesSearch = 
        item.job.job_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.job.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.job.product_type.toLowerCase().includes(searchQuery.toLowerCase());
      if (!matchesSearch) return false;

      // Status
      if (statusFilter !== 'ALL') {
        if (statusFilter === 'LATE_AT_RISK') {
          if (!item.isAtRisk && !item.isLate) return false;
        } else if (item.lifecycleStatus !== statusFilter) {
          return false;
        }
      }

      // Machine
      if (machineFilter !== 'ALL') {
        const hasMachine = item.job.operations.some(op => op.machine_id === machineFilter);
        if (!hasMachine) return false;
      }

      return true;
    });
  }, [lifecycleData, searchQuery, statusFilter, machineFilter]);

  // Lifecycle Summary Counts
  const summaryCounts = useMemo(() => {
    const counts = { QUEUED: 0, IN_PROGRESS: 0, NEAR_COMPLETION: 0, COMPLETED: 0, LATE_AT_RISK: 0 };
    lifecycleData.forEach(item => {
      counts[item.lifecycleStatus]++;
      if (item.isLate || item.isAtRisk) {
        counts.LATE_AT_RISK++;
      }
    });
    return counts;
  }, [lifecycleData]);

  const maxHorizon = schedule?.metrics.makespan ? Math.max(schedule.metrics.makespan, 200) : 250;

  function round1(v: number) {
    return Math.round(v * 10) / 10;
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#0b1120', color: '#f8fafc', fontFamily: 'system-ui, -apple-system, sans-serif', padding: '20px 24px' }}>
      
      {/* Top Header */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid #1e293b', paddingBottom: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Cpu style={{ color: '#38bdf8', width: 34, height: 34 }} />
            <div>
              <h1 style={{ fontSize: '22px', fontWeight: 800, margin: 0, letterSpacing: '-0.5px' }}>
                AI Dynamic Job-Shop Scheduling System
              </h1>
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                Stage 6: Industrial Production Lifecycle, Flexible Multi-Machine Routing &amp; 10-Machine Telemetry
              </span>
            </div>
          </div>
        </div>

        {/* Action Controls & Clock */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Workload separation banner */}
          <div style={{ backgroundColor: '#1e293b', padding: '6px 12px', borderRadius: '6px', border: '1px solid #334155', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Info size={14} color="#38bdf8" />
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>
              Workload: <strong style={{ color: '#cbd5e1' }}>Demo Workload + Dynamic User Jobs</strong>
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', backgroundColor: '#1e293b', padding: '6px 14px', borderRadius: '8px', border: '1px solid #334155' }}>
            <div>
              <span style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', display: 'block' }}>Sim Clock</span>
              <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#38bdf8' }}>{currentSim} min</div>
            </div>
            <button 
              onClick={() => advanceSim(5)} 
              style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: '#2563eb', border: 'none', color: '#fff', padding: '7px 12px', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, fontSize: '12px' }}
            >
              <FastForward size={14} /> +5 min
            </button>
            <button 
              onClick={() => advanceSim(15)} 
              style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: '#1d4ed8', border: 'none', color: '#fff', padding: '7px 12px', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, fontSize: '12px' }}
            >
              <FastForward size={14} /> +15 min
            </button>
            <button 
              onClick={() => setShowAddJob(true)}
              style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: '#059669', border: 'none', color: '#fff', padding: '7px 14px', borderRadius: '6px', cursor: 'pointer', fontWeight: 700, fontSize: '12px' }}
            >
              <PlusCircle size={15} /> Add Dynamic Job
            </button>
            <button 
              onClick={resetToDemo}
              title="Reset dynamic additions back to clean demo workload (preserves benchmark instances)"
              style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: '#334155', border: 'none', color: '#cbd5e1', padding: '7px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '12px' }}
            >
              <RefreshCw size={13} /> Reset Demo
            </button>
          </div>
        </div>
      </header>

      {/* Error alert banner */}
      {errorMessage && (
        <div style={{ backgroundColor: '#451a03', border: '1px solid #b45309', color: '#fed7aa', padding: '10px 14px', borderRadius: '6px', marginBottom: '16px', fontSize: '13px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span><strong>Notice:</strong> {errorMessage}</span>
          <button onClick={() => setErrorMessage(null)} style={{ background: 'none', border: 'none', color: '#fed7aa', cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* Quick Metrics Bar */}
      {schedule && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '14px', marginBottom: '20px' }}>
          <div style={{ backgroundColor: '#1e293b', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #38bdf8' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>Makespan (Cmax)</span>
            <div style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '2px' }}>{schedule.metrics.makespan} min</div>
          </div>
          <div style={{ backgroundColor: '#1e293b', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #f43f5e' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>Total Tardiness</span>
            <div style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '2px', color: schedule.metrics.total_tardiness > 0 ? '#f87171' : '#f8fafc' }}>{schedule.metrics.total_tardiness} min</div>
          </div>
          <div style={{ backgroundColor: '#1e293b', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #eab308' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>Late Jobs</span>
            <div style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '2px', color: schedule.metrics.late_jobs_count > 0 ? '#facc15' : '#f8fafc' }}>{schedule.metrics.late_jobs_count} of {jobs.length}</div>
          </div>
          <div style={{ backgroundColor: '#1e293b', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #10b981' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>Avg Waiting Time</span>
            <div style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '2px' }}>{schedule.metrics.avg_waiting_time} min</div>
          </div>
          <div style={{ backgroundColor: '#1e293b', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #8b5cf6' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>Machine Utilization</span>
            <div style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '2px' }}>{schedule.metrics.avg_utilization}%</div>
            <span style={{ fontSize: '10px', color: '#64748b' }}>denom: Makespan ({schedule.metrics.makespan}m)</span>
          </div>
          <div style={{ backgroundColor: '#1e293b', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #06b6d4' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>Solver Status / Latency</span>
            <div style={{ fontSize: '15px', fontWeight: 'bold', marginTop: '2px', color: '#38bdf8' }}>{schedule.metrics.solver_status}</div>
            <span style={{ fontSize: '11px', color: '#64748b' }}>{schedule.metrics.computation_time_ms} ms</span>
          </div>
        </div>
      )}

      {/* TASK 3: PRODUCTION JOB LIFECYCLE DASHBOARD */}
      <div style={{ backgroundColor: '#1e293b', padding: '18px 20px', borderRadius: '8px', border: '1px solid #334155', marginBottom: '22px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Clock size={19} color="#38bdf8" />
            <h2 style={{ fontSize: '17px', fontWeight: 800, margin: 0 }}>
              Production Job Lifecycle Dashboard
            </h2>
            <span style={{ fontSize: '11px', color: '#94a3b8', backgroundColor: '#0f172a', padding: '2px 8px', borderRadius: '4px' }}>
              Real-Time Shop Floor State
            </span>
          </div>

          {/* Lifecycle Summary Badges */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11px', padding: '4px 10px', borderRadius: '6px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', fontWeight: 600 }}>
              Queued: {summaryCounts.QUEUED}
            </span>
            <span style={{ fontSize: '11px', padding: '4px 10px', borderRadius: '6px', backgroundColor: 'rgba(234, 179, 8, 0.15)', color: '#facc15', fontWeight: 600 }}>
              In Progress: {summaryCounts.IN_PROGRESS}
            </span>
            <span style={{ fontSize: '11px', padding: '4px 10px', borderRadius: '6px', backgroundColor: 'rgba(168, 85, 247, 0.15)', color: '#c084fc', fontWeight: 600 }}>
              Near Completion: {summaryCounts.NEAR_COMPLETION}
            </span>
            <span style={{ fontSize: '11px', padding: '4px 10px', borderRadius: '6px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', fontWeight: 600 }}>
              Completed: {summaryCounts.COMPLETED}
            </span>
            <span style={{ fontSize: '11px', padding: '4px 10px', borderRadius: '6px', backgroundColor: 'rgba(244, 63, 94, 0.18)', color: '#fb7185', fontWeight: 600 }}>
              Late / At Risk: {summaryCounts.LATE_AT_RISK}
            </span>
          </div>
        </div>

        {/* Filter / Search Bar */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '14px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1', minWidth: '200px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '10px', color: '#64748b' }} />
            <input 
              type="text" 
              placeholder="Search by Job ID, Product Name, or Type..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{ width: '100%', padding: '7px 10px 7px 32px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '6px', fontSize: '12px', boxSizing: 'border-box' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Filter size={14} color="#94a3b8" />
            <select 
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#cbd5e1', padding: '6px 10px', borderRadius: '6px', fontSize: '12px' }}
            >
              <option value="ALL">All Statuses ({jobs.length})</option>
              <option value="QUEUED">Queued / Waiting ({summaryCounts.QUEUED})</option>
              <option value="IN_PROGRESS">In Progress ({summaryCounts.IN_PROGRESS})</option>
              <option value="NEAR_COMPLETION">Near Completion ({summaryCounts.NEAR_COMPLETION})</option>
              <option value="COMPLETED">Completed ({summaryCounts.COMPLETED})</option>
              <option value="LATE_AT_RISK">Late / At Risk ({summaryCounts.LATE_AT_RISK})</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>Machine:</span>
            <select 
              value={machineFilter}
              onChange={e => setMachineFilter(e.target.value)}
              style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#cbd5e1', padding: '6px 10px', borderRadius: '6px', fontSize: '12px' }}
            >
              <option value="ALL">All Machines (M1–M10)</option>
              {machines.map(m => (
                <option key={m.machine_id} value={m.machine_id}>{m.machine_id} - {m.name}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Lifecycle Table */}
        <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid #334155' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px', minWidth: '980px' }}>
            <thead>
              <tr style={{ backgroundColor: '#0f172a', borderBottom: '1px solid #334155', color: '#94a3b8' }}>
                <th style={{ padding: '9px 12px' }}>Job ID / Product</th>
                <th style={{ padding: '9px 12px' }}>Status</th>
                <th style={{ padding: '9px 12px' }}>Current / Next Stage</th>
                <th style={{ padding: '9px 12px' }}>Assigned M/C</th>
                <th style={{ padding: '9px 12px' }}>Progress</th>
                <th style={{ padding: '9px 12px' }}>Sim Start</th>
                <th style={{ padding: '9px 12px' }}>Est. Done</th>
                <th style={{ padding: '9px 12px' }}>Due Time</th>
                <th style={{ padding: '9px 12px' }}>Remaining</th>
                <th style={{ padding: '9px 12px' }}>Risk Indicator</th>
              </tr>
            </thead>
            <tbody>
              {filteredLifecycle.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                    No jobs match the current filter or search criteria.
                  </td>
                </tr>
              ) : (
                filteredLifecycle.map((item) => (
                  <tr 
                    key={item.job.job_id} 
                    style={{ 
                      borderBottom: '1px solid #1e293b', 
                      backgroundColor: item.isLate ? 'rgba(244, 63, 94, 0.05)' : 'transparent' 
                    }}
                  >
                    <td style={{ padding: '9px 12px' }}>
                      <div style={{ fontWeight: 700, color: '#f8fafc' }}>{item.job.job_id}</div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>{item.job.name} ({item.job.product_type})</div>
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      <span style={{ 
                        fontSize: '11px', 
                        fontWeight: 700, 
                        padding: '3px 8px', 
                        borderRadius: '4px',
                        backgroundColor: item.statusBg,
                        color: item.statusColor,
                        whiteSpace: 'nowrap'
                      }}>
                        {item.statusLabel}
                      </span>
                    </td>
                    <td style={{ padding: '9px 12px', color: '#cbd5e1' }}>
                      {item.currentOpName}
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      {item.assignedMachine !== '-' ? (
                        <span style={{ fontWeight: 700, color: '#38bdf8' }}>{item.assignedMachine}</span>
                      ) : (
                        <span style={{ color: '#64748b' }}>-</span>
                      )}
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontWeight: 600 }}>{item.completedOps}/{item.totalOps}</span>
                        <div style={{ width: '50px', height: '6px', backgroundColor: '#334155', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ 
                            width: `${item.totalOps > 0 ? (item.completedOps / item.totalOps) * 100 : 0}%`, 
                            height: '100%', 
                            backgroundColor: item.completedOps === item.totalOps ? '#10b981' : '#38bdf8' 
                          }} />
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '9px 12px', color: '#cbd5e1' }}>
                      {item.actualOrSimStart !== null ? `${item.actualOrSimStart}m` : '-'}
                    </td>
                    <td style={{ padding: '9px 12px', color: item.isAtRisk ? '#f43f5e' : '#cbd5e1', fontWeight: item.isAtRisk ? 700 : 400 }}>
                      {item.estimatedCompletion !== null ? `${item.estimatedCompletion}m` : '-'}
                    </td>
                    <td style={{ padding: '9px 12px', color: '#cbd5e1' }}>
                      {item.dueTime}m
                    </td>
                    <td style={{ padding: '9px 12px', color: '#cbd5e1' }}>
                      {item.remainingProcessing > 0 ? `${item.remainingProcessing}m` : '0m'}
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      {item.isLate ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', color: '#f43f5e', fontSize: '11px', fontWeight: 700 }}>
                          <AlertTriangle size={12} /> Late ({round1(currentSim - item.dueTime)}m)
                        </span>
                      ) : item.isAtRisk ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', color: '#f97316', fontSize: '11px', fontWeight: 600 }}>
                          <AlertTriangle size={12} /> Risk (Slack &lt; 0)
                        </span>
                      ) : item.lifecycleStatus === 'COMPLETED' ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', color: '#10b981', fontSize: '11px' }}>
                          <CheckCircle size={12} /> Complete
                        </span>
                      ) : (
                        <span style={{ color: '#10b981', fontSize: '11px' }}>On Schedule</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Main Grid: Machine Telemetry & AI Strategy Recommendation */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px', marginBottom: '22px' }}>
        
        {/* Machine Telemetry Grid (All 10 Machines) */}
        <div style={{ backgroundColor: '#1e293b', padding: '18px 20px', borderRadius: '8px', border: '1px solid #334155' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h2 style={{ fontSize: '17px', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={19} color="#38bdf8" /> 10-Machine Real-Time Factory Floor Telemetry
            </h2>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>M1–M5 Primary Stages | M6–M10 Parallel Aux Stations</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
            {machines.map(m => {
              const utilVal = schedule?.metrics?.machine_utilization?.[m.machine_id] ?? 0;
              const isDown = m.status === 'DOWN' || m.status === 'MAINTENANCE';
              return (
                <div 
                  key={m.machine_id}
                  style={{ 
                    backgroundColor: '#0f172a', 
                    padding: '10px 12px', 
                    borderRadius: '6px', 
                    border: isDown ? '1px solid #f43f5e' : m.status === 'BUSY' ? '1px solid #f59e0b' : '1px solid #334155',
                    position: 'relative'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 'bold', fontSize: '13px', color: '#38bdf8' }}>{m.machine_id}</span>
                    <span style={{ 
                      fontSize: '9px', 
                      fontWeight: 'bold', 
                      padding: '2px 5px', 
                      borderRadius: '3px',
                      backgroundColor: isDown ? '#881337' : m.status === 'BUSY' ? '#78350f' : '#064e3b',
                      color: isDown ? '#fda4af' : m.status === 'BUSY' ? '#fcd34d' : '#6ee7b7'
                    }}>
                      {m.status}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: '#cbd5e1', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {m.name}
                  </div>
                  <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
                    Cap: {m.capability}
                  </div>
                  {/* Utilization denominator explanation */}
                  <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '4px' }}>
                    Util: <strong style={{ color: utilVal > 0 ? '#38bdf8' : '#64748b' }}>{utilVal}%</strong>
                  </div>
                  {m.status === 'BUSY' && (
                    <div style={{ marginTop: '6px', fontSize: '10px', color: '#f59e0b', backgroundColor: '#451a03', padding: '3px', borderRadius: '3px' }}>
                      Job {m.current_job_id} (rem: {m.remaining_processing_time}m)
                    </div>
                  )}
                  {isDown && (
                    <div style={{ marginTop: '6px', fontSize: '10px', color: '#fda4af', backgroundColor: '#4c0519', padding: '3px', borderRadius: '3px' }}>
                      Down (repair: {m.remaining_processing_time}m)
                    </div>
                  )}
                  <div style={{ marginTop: '6px' }}>
                    <button
                      onClick={() => toggleMachineDowntime(m)}
                      style={{
                        width: '100%',
                        fontSize: '10px',
                        padding: '3px 6px',
                        borderRadius: '4px',
                        border: 'none',
                        cursor: 'pointer',
                        fontWeight: 600,
                        backgroundColor: isDown ? '#059669' : '#334155',
                        color: isDown ? '#fff' : '#cbd5e1'
                      }}
                    >
                      {isDown ? 'Recover M/C' : 'Sim Breakdown (+20m)'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* AI & Optimization Control Panel */}
        <div style={{ backgroundColor: '#1e293b', padding: '18px 20px', borderRadius: '8px', border: '1px solid #334155' }}>
          <h2 style={{ fontSize: '17px', fontWeight: 800, margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Zap size={19} color="#eab308" /> AI Strategy Advisor &amp; Dispatch
          </h2>

          {recommendation && (
            <div style={{ backgroundColor: '#0f172a', padding: '12px 14px', borderRadius: '6px', border: '1px solid #ca8a04', marginBottom: '14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', color: '#fef08a', fontWeight: 'bold' }}>ML RECOMMENDED STRATEGY:</span>
                <span style={{ fontSize: '11px', color: '#a3e635' }}>Confidence: {(recommendation.confidence * 100).toFixed(0)}%</span>
              </div>
              <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#fde047', marginTop: '3px' }}>
                {recommendation.recommended_algorithm}
              </div>
              <p style={{ fontSize: '11px', color: '#cbd5e1', margin: '4px 0 0 0' }}>
                {recommendation.reason}
              </p>
            </div>
          )}

          <div style={{ marginBottom: '14px' }}>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Active Scheduling Engine:</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <select 
                value={selectedAlgo} 
                onChange={(e) => setSelectedAlgo(e.target.value)}
                style={{ flex: 1, backgroundColor: '#0f172a', border: '1px solid #475569', color: '#fff', padding: '7px 10px', borderRadius: '6px', fontSize: '12px' }}
              >
                <option value="CPSAT">Google OR-Tools CP-SAT (Optimal/Exact)</option>
                <option value="EPN">PyTorch Pointer Network (Liu et al. IEEE TASE 2024)</option>
                <option value="EDD">EDD (Earliest Due Date)</option>
                <option value="SPT">SPT (Shortest Processing Time)</option>
                <option value="CR">Critical Ratio (Slack-Aware)</option>
                <option value="AGING">Aging / Anti-Starvation Heuristic</option>
                <option value="FCFS">FCFS (First Come First Served)</option>
              </select>
              <button 
                onClick={() => runRecalculation(selectedAlgo)}
                disabled={loading}
                style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '7px 14px', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer', fontSize: '12px' }}
              >
                {loading ? 'Solving...' : 'Re-Solve'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* TASK 4: ENHANCED DYNAMIC PRODUCTION GANTT CHART */}
      <div style={{ backgroundColor: '#1e293b', padding: '18px 20px', borderRadius: '8px', border: '1px solid #334155', marginBottom: '22px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h2 style={{ fontSize: '17px', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BarChart2 size={19} color="#38bdf8" /> 10-Machine Dynamic Production Gantt Schedule
            </h2>
            <span style={{ fontSize: '11px', color: '#64748b' }}>
              All machines M1–M10 displayed | Current Sim Time: <strong style={{ color: '#38bdf8' }}>{currentSim}m</strong> | Horizon: 0 to {Math.ceil(maxHorizon)}m
            </span>
          </div>

          {/* Gantt Legend */}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', fontSize: '11px', color: '#94a3b8' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '10px', height: '10px', backgroundColor: '#10b981', borderRadius: '2px' }}></span> Completed
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '10px', height: '10px', backgroundColor: '#eab308', borderRadius: '2px' }}></span> Running (Sim Lock)
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '10px', height: '10px', backgroundColor: '#0284c7', borderRadius: '2px' }}></span> Planned / Planned Future
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '10px', height: '10px', backgroundColor: '#f43f5e', borderRadius: '2px' }}></span> Late / Slack Deficit
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '2px', height: '14px', backgroundColor: '#f43f5e', display: 'inline-block' }}></span> Clock Marker
            </span>
          </div>
        </div>

        {/* Hover Task Detail Panel (fixed height prevents Gantt layout shift / hover oscillation flicker) */}
        <div style={{ 
          backgroundColor: '#0f172a', 
          padding: '8px 14px', 
          borderRadius: '6px', 
          border: hoveredTask ? '1px solid #38bdf8' : '1px dashed #334155', 
          marginBottom: '10px', 
          display: 'flex', 
          gap: '16px', 
          fontSize: '12px', 
          alignItems: 'center',
          minHeight: '38px',
          boxSizing: 'border-box'
        }}>
          {hoveredTask ? (
            <>
              <div><strong style={{ color: '#38bdf8' }}>{hoveredTask.job_id}</strong>: {hoveredTask.job_name}</div>
              <div>Op {hoveredTask.operation_sequence}: <strong style={{ color: '#cbd5e1' }}>{hoveredTask.operation_name}</strong></div>
              <div>M/C: <strong style={{ color: '#fde047' }}>{hoveredTask.machine_id}</strong></div>
              <div>Window: <strong style={{ color: '#34d399' }}>{hoveredTask.start_time}m &rarr; {hoveredTask.end_time}m</strong> ({hoveredTask.duration}m)</div>
              <div>Status: <span style={{ color: hoveredTask.is_completed ? '#34d399' : hoveredTask.is_running ? '#facc15' : '#38bdf8', fontWeight: 600 }}>
                {hoveredTask.is_completed ? 'COMPLETED (Historical)' : hoveredTask.is_running ? 'RUNNING (Locked)' : 'PLANNED FUTURE'}
              </span></div>
            </>
          ) : (
            <span style={{ color: '#64748b', fontSize: '11px', fontStyle: 'italic' }}>
              💡 Hover over any operation block in the Gantt chart below to inspect its scheduled window, assigned machine, and execution status.
            </span>
          )}
        </div>

        {/* Gantt Canvas View */}
        <div style={{ backgroundColor: '#0f172a', padding: '14px', borderRadius: '6px', overflowX: 'auto' }}>
          
          {/* Time axis scale ticks */}
          <div style={{ display: 'flex', marginBottom: '8px', paddingLeft: '140px' }}>
            {[0, 0.25, 0.5, 0.75, 1.0].map((frac, idx) => (
              <div key={idx} style={{ flex: 1, fontSize: '10px', color: '#64748b', borderLeft: '1px dashed #334155', paddingLeft: '4px' }}>
                {Math.round(frac * maxHorizon)}m
              </div>
            ))}
          </div>

          {machines.map((m) => {
            const mTasks = schedule?.tasks.filter(t => t.machine_id === m.machine_id) || [];
            const isIdle = mTasks.length === 0;

            return (
              <div key={m.machine_id} style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                {/* Machine Label Column */}
                <div style={{ width: '140px', fontSize: '11px', color: '#cbd5e1', flexShrink: 0, paddingRight: '10px' }}>
                  <div style={{ fontWeight: 700, color: '#38bdf8' }}>{m.machine_id}</div>
                  <div style={{ fontSize: '10px', color: '#64748b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {m.name}
                  </div>
                </div>

                {/* Machine Timeline Bar */}
                <div style={{ flex: 1, height: '32px', backgroundColor: '#1e293b', borderRadius: '4px', position: 'relative', overflow: 'hidden' }}>
                  
                  {/* Current Sim Time Indicator Line */}
                  {currentSim > 0 && currentSim <= maxHorizon && (
                    <div 
                      title={`Current Simulation Clock: ${currentSim}m`}
                      style={{
                        position: 'absolute',
                        left: `${(currentSim / maxHorizon) * 100}%`,
                        top: 0,
                        bottom: 0,
                        width: '2px',
                        backgroundColor: '#f43f5e',
                        zIndex: 10,
                        boxShadow: '0 0 6px #f43f5e'
                      }}
                    />
                  )}

                  {/* Machine Downtime Window Block */}
                  {(m.status === 'DOWN' || m.status === 'MAINTENANCE') && m.remaining_processing_time > 0 && (
                    <div
                      title={`${m.machine_id} DOWN until ${currentSim + m.remaining_processing_time}m`}
                      style={{
                        position: 'absolute',
                        left: `${(currentSim / maxHorizon) * 100}%`,
                        width: `${Math.min(100 - (currentSim / maxHorizon) * 100, (m.remaining_processing_time / maxHorizon) * 100)}%`,
                        height: '100%',
                        backgroundColor: 'rgba(244, 63, 94, 0.28)',
                        border: '1px dashed #f43f5e',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '9px',
                        color: '#fda4af',
                        fontWeight: 700,
                        zIndex: 5
                      }}
                    >
                      DOWN ({m.remaining_processing_time}m)
                    </div>
                  )}

                  {/* Idle Machine Notice */}
                  {isIdle && (
                    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#64748b', fontStyle: 'italic' }}>
                      Idle — No operations routed to {m.machine_id} ({m.capability})
                    </div>
                  )}

                  {/* Scheduled Operation Blocks */}
                  {mTasks.map((t, idx) => {
                    const leftPct = (t.start_time / maxHorizon) * 100;
                    const widthPct = Math.max((t.duration / maxHorizon) * 100, 1.5);

                    // Color coding according to state
                    let bgColor = '#0284c7';
                    if (t.is_completed) {
                      bgColor = '#10b981';
                    } else if (t.is_running) {
                      bgColor = '#eab308';
                    } else {
                      // Check if job is at risk
                      const jMatch = jobs.find(j => j.job_id === t.job_id);
                      if (jMatch && t.end_time > jMatch.due_date) {
                        bgColor = '#f43f5e';
                      }
                    }

                    return (
                      <div 
                        key={idx}
                        onMouseEnter={() => setHoveredTask(t)}
                        onMouseLeave={() => setHoveredTask(null)}
                        title={`${t.job_name} (${t.job_id}): ${t.operation_name} [${t.start_time}m - ${t.end_time}m, dur: ${t.duration}m]`}
                        style={{
                          position: 'absolute',
                          left: `${leftPct}%`,
                          width: `${widthPct}%`,
                          height: '100%',
                          backgroundColor: bgColor,
                          borderRadius: '3px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '10px',
                          fontWeight: 'bold',
                          color: '#fff',
                          overflow: 'hidden',
                          whiteSpace: 'nowrap',
                          padding: '0 4px',
                          boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.25)',
                          cursor: 'pointer',
                          transition: 'filter 0.15s ease'
                        }}
                      >
                        {t.job_id.replace('JOB_', '')}-Op{t.operation_sequence}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Algorithm Benchmark Comparison Matrix */}
      {comparison && (
        <div style={{ backgroundColor: '#1e293b', padding: '18px 20px', borderRadius: '8px', border: '1px solid #334155' }}>
          <h2 style={{ fontSize: '17px', fontWeight: 800, margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={19} color="#10b981" /> Fair Algorithm Benchmark &amp; Performance Matrix
          </h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #475569', color: '#94a3b8' }}>
                <th style={{ padding: '8px 10px' }}>Algorithm</th>
                <th style={{ padding: '8px 10px' }}>Makespan (min)</th>
                <th style={{ padding: '8px 10px' }}>Total Tardiness (min)</th>
                <th style={{ padding: '8px 10px' }}>Late Jobs</th>
                <th style={{ padding: '8px 10px' }}>Avg Wait Time (min)</th>
                <th style={{ padding: '8px 10px' }}>Avg Machine Util</th>
                <th style={{ padding: '8px 10px' }}>Compute Latency</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(comparison).map(([name, data]: [string, any]) => (
                <tr key={name} style={{ borderBottom: '1px solid #334155', backgroundColor: name.includes('CP-SAT') ? '#0284c715' : 'transparent' }}>
                  <td style={{ padding: '8px 10px', fontWeight: 'bold', color: name.includes('CP-SAT') ? '#38bdf8' : '#cbd5e1' }}>{name}</td>
                  <td style={{ padding: '8px 10px' }}>{data.makespan}</td>
                  <td style={{ padding: '8px 10px', color: data.total_tardiness > 0 ? '#f43f5e' : '#10b981' }}>{data.total_tardiness}</td>
                  <td style={{ padding: '8px 10px' }}>{data.late_jobs_count}</td>
                  <td style={{ padding: '8px 10px' }}>{data.avg_waiting_time}</td>
                  <td style={{ padding: '8px 10px' }}>{data.avg_utilization}%</td>
                  <td style={{ padding: '8px 10px', color: '#94a3b8' }}>{data.computation_time_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TASK 1: REDESIGNED FLEXIBLE DYNAMIC JOB REGISTRATION MODAL */}
      {showAddJob && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: '16px' }}>
          <div style={{ backgroundColor: '#1e293b', padding: '24px', borderRadius: '12px', width: '680px', maxWidth: '100%', border: '1px solid #475569', maxHeight: '92vh', overflowY: 'auto' }}>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid #334155', paddingBottom: '10px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 'bold', color: '#38bdf8' }}>
                  Register Dynamic Manufacturing Job
                </h3>
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                  Configure arbitrary valid operation routes across eligible machines M1–M10
                </span>
              </div>
              <button 
                onClick={() => setShowAddJob(false)}
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateJob}>
              {/* Job Identification */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Job ID *</label>
                  <input 
                    type="text" 
                    value={newJob.job_id} 
                    onChange={e => setNewJob({...newJob, job_id: e.target.value})}
                    style={{ width: '100%', padding: '8px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '12px', boxSizing: 'border-box' }}
                    required 
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Product / Job Name *</label>
                  <input 
                    type="text" 
                    placeholder="e.g. Turbine Impeller Rotor"
                    value={newJob.name} 
                    onChange={e => setNewJob({...newJob, name: e.target.value})}
                    style={{ width: '100%', padding: '8px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '12px', boxSizing: 'border-box' }}
                    required 
                  />
                </div>
              </div>

              {/* Product Type, Priority, Due Date */}
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Product Type</label>
                  <input 
                    type="text" 
                    value={newJob.product_type} 
                    onChange={e => setNewJob({...newJob, product_type: e.target.value})}
                    style={{ width: '100%', padding: '8px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '12px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Priority (1-5)</label>
                  <input 
                    type="number" 
                    value={newJob.priority} 
                    min={1} 
                    max={5}
                    onChange={e => setNewJob({...newJob, priority: parseInt(e.target.value) || 1})}
                    style={{ width: '100%', padding: '8px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '12px', boxSizing: 'border-box' }}
                    required 
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Due Date (mins) *</label>
                  <input 
                    type="number" 
                    min={1}
                    value={newJob.due_date} 
                    onChange={e => setNewJob({...newJob, due_date: parseFloat(e.target.value) || 0})}
                    style={{ width: '100%', padding: '8px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '12px', boxSizing: 'border-box' }}
                    required 
                  />
                </div>
              </div>

              {/* Dynamic Operations List */}
              <div style={{ marginBottom: '18px', backgroundColor: '#0f172a', padding: '14px', borderRadius: '8px', border: '1px solid #334155' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc' }}>
                      Operation Routing Sequence
                    </span>
                    <span style={{ fontSize: '11px', color: '#94a3b8', display: 'block' }}>
                      Arbitrary machine routes supported. Machines M1–M10 are populated from the backend.
                    </span>
                  </div>
                  <button 
                    type="button" 
                    onClick={handleAddOperation}
                    style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#2563eb', color: '#fff', border: 'none', padding: '5px 10px', borderRadius: '4px', cursor: 'pointer', fontSize: '11px', fontWeight: 600 }}
                  >
                    <Plus size={13} /> Add Operation
                  </button>
                </div>

                {newJob.operations.map((op, idx) => (
                  <div key={idx} style={{ display: 'grid', gridTemplateColumns: '28px 1fr 1.6fr 90px 32px', gap: '8px', alignItems: 'center', marginBottom: '8px', backgroundColor: '#1e293b', padding: '8px', borderRadius: '6px' }}>
                    {/* Seq */}
                    <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#38bdf8', textAlign: 'center' }}>
                      #{op.sequence}
                    </span>

                    {/* Op Name */}
                    <input 
                      type="text"
                      placeholder="Operation name"
                      value={op.name}
                      onChange={e => {
                        const updated = [...newJob.operations];
                        updated[idx].name = e.target.value;
                        setNewJob({...newJob, operations: updated});
                      }}
                      style={{ padding: '6px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '11px' }}
                      required
                    />

                    {/* Machine Selector from Backend M1–M10 */}
                    <select 
                      value={op.machine_id}
                      onChange={e => {
                        const chosenMid = e.target.value;
                        const mObj = machines.find(m => m.machine_id === chosenMid);
                        const updated = [...newJob.operations];
                        updated[idx].machine_id = chosenMid;
                        if (mObj && (!updated[idx].name || updated[idx].name.startsWith('Stage') || updated[idx].name.includes('Making') || updated[idx].name.includes('Casting'))) {
                          updated[idx].name = mObj.capability;
                        }
                        setNewJob({...newJob, operations: updated});
                      }}
                      style={{ padding: '6px', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#cbd5e1', borderRadius: '4px', fontSize: '11px' }}
                    >
                      {machines.map(m => (
                        <option key={m.machine_id} value={m.machine_id}>
                          {m.machine_id} - {m.name} ({m.capability})
                        </option>
                      ))}
                    </select>

                    {/* Duration Input - initialized to 0, user must fill > 0 */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <input 
                        type="number"
                        min="1"
                        step="1"
                        placeholder="dur > 0"
                        value={op.duration === 0 ? '' : op.duration}
                        onChange={e => {
                          const val = parseFloat(e.target.value);
                          const updated = [...newJob.operations];
                          updated[idx].duration = isNaN(val) ? 0 : val;
                          setNewJob({...newJob, operations: updated});
                        }}
                        style={{ 
                          width: '56px', 
                          padding: '6px 4px', 
                          backgroundColor: '#0f172a', 
                          border: op.duration <= 0 ? '1px solid #f43f5e' : '1px solid #334155', 
                          color: '#fff', 
                          borderRadius: '4px', 
                          fontSize: '11px',
                          textAlign: 'center'
                        }}
                        required
                      />
                      <span style={{ fontSize: '10px', color: '#64748b' }}>min</span>
                    </div>

                    {/* Remove Op */}
                    <button 
                      type="button" 
                      onClick={() => handleRemoveOperation(idx)}
                      disabled={newJob.operations.length <= 1}
                      style={{ background: 'none', border: 'none', color: newJob.operations.length <= 1 ? '#475569' : '#f43f5e', cursor: newJob.operations.length <= 1 ? 'not-allowed' : 'pointer', padding: '4px' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>

              {/* Form Buttons */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button 
                  type="button" 
                  onClick={() => setShowAddJob(false)}
                  style={{ backgroundColor: '#475569', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontSize: '12px' }}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  style={{ backgroundColor: '#059669', color: '#fff', border: 'none', padding: '8px 18px', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', fontSize: '12px' }}
                >
                  Register Job &amp; Re-Optimize
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
