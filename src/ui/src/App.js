import React, { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, BarChart, Bar, ComposedChart } from "recharts";
import InsightsPanel from "./InsightsPanel";
import TransactionsTab from "./TransactionsTab";

const COLORS = [
  "#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#A28CFF", "#FF6699", "#33CC99", "#FF4444", "#FFB347", "#B6D7A8",
  "#FFD700", "#FF7F50", "#6495ED", "#DC143C", "#20B2AA", "#FF6347", "#4682B4", "#32CD32"
];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
};

const formatMonth = (ym) => {
  if (!ym) return ym;
  const [year, month] = ym.split('-');
  return new Date(+year, +month - 1, 2).toLocaleString('default', { month: 'long', year: 'numeric' });
};

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div style={{ backgroundColor: '#fff', padding: '10px', border: '1px solid #ccc', borderRadius: '4px' }}>
        <p style={{ margin: '0 0 5px 0', fontWeight: 'bold' }}>{label}</p>
        {payload.map((entry, index) => (
          <p key={index} style={{ margin: '2px 0', color: entry.color }}>
            {entry.name}: {formatCurrency(entry.value)}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

function App() {
  const [data, setData] = useState([]); 
  const [lineData, setLineData] = useState([]); 
  const [incomeData, setIncomeData] = useState([]); 

  const [selectedCategory, setSelectedCategory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() - 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  }); // Default to previous complete month
  const [hierarchy, setHierarchy] = useState({});
  const [expandedParents, setExpandedParents] = useState(new Set());
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('activeTab') || 'overview');
  const setActiveTabPersisted = (tab) => { localStorage.setItem('activeTab', tab); setActiveTab(tab); };
  const [transfers, setTransfers] = useState([]);
  const [transfersLoading, setTransfersLoading] = useState(false);
  const [incomeEntries, setIncomeEntries] = useState([]);
  const [invFilterMonth, setInvFilterMonth] = useState(selectedMonth);
  const [statementsData, setStatementsData] = useState([]);
  const [stmtUploadMonth, setStmtUploadMonth] = useState('');
  // Once statementsData loads, default to the month after the latest existing statement month.
  const stmtUploadMonthInitialised = React.useRef(false);
  React.useEffect(() => {
    if (stmtUploadMonthInitialised.current || statementsData.length === 0) return;
    stmtUploadMonthInitialised.current = true;
    const months = statementsData.map(s => s.month).filter(Boolean).sort();
    const latest = months[months.length - 1]; // e.g. "2024-05"
    if (latest) {
      const [y, m] = latest.split('-').map(Number);
      const next = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
      setStmtUploadMonth(next);
    } else {
      const d = new Date(); d.setDate(1);
      setStmtUploadMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
    }
  }, [statementsData]);
  const [stmtUploading, setStmtUploading] = useState(false);
  const [stmtProcessing, setStmtProcessing] = useState(false);
  const [stmtForce, setStmtForce] = useState(false);
  const [stmtLog, setStmtLog] = useState('');
  const [stmtDragOver, setStmtDragOver] = useState(false);
  const [stmtError, setStmtError] = useState('');
  const [availableCategories, setAvailableCategories] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [goals, setGoals] = useState(() => {
    try { return JSON.parse(localStorage.getItem('budgetGoals') || '{}'); }
    catch { return {}; }
  });

  useEffect(() => {
    Promise.all([
      fetch('http://localhost:8000/api/category-hierarchy').then(r => r.json()),
      fetch('http://localhost:8000/api/categories').then(r => r.json()),
      fetch('http://localhost:8000/api/available-months').then(r => r.json()),
    ])
      .then(([hier, cats, months]) => {
        setHierarchy(hier || {});
        setAvailableCategories(Array.isArray(cats) ? cats.map(c => c.category || c).filter(Boolean) : []);
        if (Array.isArray(months) && months.length > 0) {
          setSelectedMonth(prev => months.includes(prev) ? prev : months[0]);
        }
      })
      .catch(err => console.error('Failed to load config:', err));
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`http://localhost:8000/api/expense-categories?month=${selectedMonth}`).then(res => res.json()),
      fetch("http://localhost:8000/api/expenses-by-month").then(res => res.json()),
      fetch("http://localhost:8000/api/income-by-month").then(res => res.json()),
    ])
      .then(([expenseCategories, expensesByMonth, income]) => {
        setData(expenseCategories);
        setLineData(expensesByMonth);
        setIncomeData(income);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [selectedMonth, refreshKey]);

  useEffect(() => {
    if (activeTab !== 'statements') return;
    // Reset so the month picker re-targets the next unprocessed month on each visit
    stmtUploadMonthInitialised.current = false;
    setStmtLog('');
    setStmtError('');
    setStmtForce(false);
    fetch('http://localhost:8000/api/statements').then(r => r.json()).then(d => setStatementsData(Array.isArray(d) ? d : []));
  }, [activeTab]);

  useEffect(() => { setInvFilterMonth(selectedMonth); }, [selectedMonth]);

  useEffect(() => {
    if (activeTab !== 'investments') return;
    setTransfersLoading(true);
    Promise.all([
        fetch('http://localhost:8000/api/transfers').then(r => r.json()),
        fetch('http://localhost:8000/api/income-entries').then(r => r.json()),
      ])
      .then(([t, inc]) => {
        setTransfers(Array.isArray(t) ? t : []);
        setIncomeEntries(Array.isArray(inc) ? inc : []);
        setTransfersLoading(false);
      })
      .catch(() => setTransfersLoading(false));
  }, [activeTab]);

  const handlePieClick = (data, index) => {
    setSelectedCategory(data.category === selectedCategory ? null : data.category);
  };

  const handleExpenseLabel = async (row, label) => {
    await fetch('http://localhost:8000/api/expense/label', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: row.date, place: row.place, amount: row.amount, month: row.month, label }),
    });
  };

  const handleTransferLabel = async (row, label) => {
    await fetch('http://localhost:8000/api/transfers/label', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: row.date, place: row.place, amount: row.amount, label: label || null }),
    });
    setTransfers(prev => prev.map(t =>
      t.date === row.date && t.place === row.place && t.amount === row.amount
        ? { ...t, label: label || null }
        : t
    ));
  };

  // Build sub→parent reverse map
  const parentMap = {};
  for (const [parent, subs] of Object.entries(hierarchy)) {
    for (const sub of subs) parentMap[sub] = parent;
  }

  // Roll subcategories into parent groups for pie + table display
  const groupedData = (() => {
    const groups = new Map();
    for (const item of data) {
      const parent = parentMap[item.category] || item.category;
      if (!groups.has(parent)) groups.set(parent, { category: parent, amount: 0, subcategories: [] });
      const g = groups.get(parent);
      g.amount += item.amount;
      if (parentMap[item.category]) g.subcategories.push(item);
    }
    return Array.from(groups.values()).sort((a, b) => b.amount - a.amount);
  })();

  const filteredData = selectedCategory
    ? data.filter((d) => {
        const parent = parentMap[d.category] || d.category;
        return d.category === selectedCategory || parent === selectedCategory;
      })
    : data;

  // Calculate totals
  const totalExpenses = data.reduce((sum, d) => sum + d.amount, 0);
  // Use only recurring income for the budget baseline average
  const totalRecurringIncome = incomeData.reduce((sum, d) => sum + (d.income || 0), 0);
  const totalBonusIncome = incomeData.reduce((sum, d) => sum + (d.bonus || 0), 0);
  const avgMonthlyIncome = incomeData.length > 0 ? totalRecurringIncome / incomeData.length : 0;
  
  // Prepare line chart data: group by month, each category as a line
  const months = Array.from(new Set(lineData.map(d => d.month))).sort();
  const categories = Array.from(new Set(lineData.map(d => d.category)));
  const lineChartData = months.map(month => {
    const entry = { month };
    let total = 0;
    categories.forEach(cat => {
      const found = lineData.find(d => d.month === month && d.category === cat);
      const amount = found ? found.amount : 0;
      entry[cat] = amount;
      total += amount;
    });
    entry.total = total;
    return entry;
  });

  // Combine income and expense data for comparison chart
  const incomeVsExpenseData = months.map(month => {
    const expense = lineChartData.find(d => d.month === month);
    const income = incomeData.find(d => d.month === month);
    return {
      month,
      expense: expense ? expense.total : 0,
      income: income ? income.income : 0,
      bonus: income ? (income.bonus || 0) : 0,
    };
  });

  if (loading) {
    return (
      <div style={{ padding: 32, fontFamily: 'sans-serif', textAlign: 'center' }}>
        <h2>Loading Dashboard...</h2>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32, fontFamily: 'sans-serif' }}>
        <h2 style={{ color: 'red' }}>Error Loading Data</h2>
        <p>{error}</p>
        <p>Make sure the backend server is running on port 8000.</p>
      </div>
    );
  }

  const cardStyle = {
    backgroundColor: '#fff',
    padding: '20px 24px',
    borderRadius: 10,
    boxShadow: '0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.05)',
    border: '1px solid #e2e8f0',
    position: 'relative',
    overflow: 'hidden',
  };

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", backgroundColor: '#f1f5f9', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)', padding: '28px 32px' }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 style={{ margin: 0, color: '#fff', fontSize: 26, fontWeight: 800, letterSpacing: '-.02em' }}>
              💰 Automated Budgeting
            </h1>
            <p style={{ margin: '4px 0 0', color: 'rgba(255,255,255,.75)', fontSize: 14 }}>
              AI-powered financial insights for {formatMonth(selectedMonth)}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {[
              { label: `${formatMonth(selectedMonth)} Spend`, value: formatCurrency(totalExpenses), color: '#fbbf24' },
              { label: 'Avg Monthly Income', value: formatCurrency(avgMonthlyIncome), color: '#34d399' },
              { label: 'Categories', value: categories.length, color: '#a5b4fc' },
            ].map((s, i) => (
              <div key={i} style={{ background: 'rgba(255,255,255,.12)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,.2)', borderRadius: 10, padding: '10px 18px', textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,.7)', fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase', marginBottom: 4 }}>{s.label}</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '0 32px' }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', display: 'flex', gap: 0 }}>
          {[
            { key: 'overview', label: '📊 Overview' },
            { key: 'budget', label: '📋 Budget & Forecast' },
            { key: 'investments', label: '💼 Investments' },
            { key: 'transactions', label: '✏️ Transactions' },
            { key: 'statements', label: '⬆️ Statements' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTabPersisted(tab.key)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '14px 22px', fontSize: 14, fontWeight: 600,
                color: activeTab === tab.key ? '#4f46e5' : '#64748b',
                borderBottom: activeTab === tab.key ? '2px solid #4f46e5' : '2px solid transparent',
                transition: 'all .15s',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Transactions Tab ── */}
      {activeTab === 'transactions' && (
        <TransactionsTab
          formatCurrency={formatCurrency}
          categories={availableCategories}
          selectedMonth={selectedMonth}
          onRefreshData={() => setRefreshKey(k => k + 1)}
        />
      )}


      {/* ── Budget & Forecast Tab ── */}
      {activeTab === 'budget' && (
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 32px' }}>
          <InsightsPanel
            forcedTab="plan"
            selectedMonth={selectedMonth}
            onMonthChange={setSelectedMonth}
            hierarchy={hierarchy}
            goals={goals}
            setGoals={setGoals}
            groupedData={groupedData}
            totalExpenses={totalExpenses}
            avgMonthlyIncome={avgMonthlyIncome}
            COLORS={COLORS}
            formatCurrency={formatCurrency}
          />
        </div>
      )}

      {/* ── Overview Tab ── */}
      {activeTab === 'overview' && (
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 32px' }}>

        {/* Income vs Expense Comparison */}
        <div style={{ ...cardStyle, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0, color: '#0f172a', fontWeight: 700, fontSize: 16 }}>📊 Income vs Expenses — 12 Months</h3>
          <p style={{ margin: '-8px 0 12px', fontSize: 12, color: '#94a3b8' }}>💡 Click a month to view its overview</p>
          <ResponsiveContainer width="100%" height={350}>
            <ComposedChart
              data={incomeVsExpenseData}
              margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
              style={{ cursor: 'pointer' }}
              onClick={e => {
                const month = e?.activeLabel || e?.activePayload?.[0]?.payload?.month;
                if (month) { setSelectedMonth(month); window.scrollTo({ top: 0, behavior: 'smooth' }); }
              }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Bar dataKey="income" fill="#00C49F" name="Regular Income" stackId="income"
                stroke={null}
                radius={[0, 0, 0, 0]}
                isAnimationActive={false}
              />
              <Bar dataKey="bonus" fill="#f59e0b" name="Bonus Income" stackId="income"
                isAnimationActive={false}
              />
              <Bar dataKey="expense" name="Expenses" isAnimationActive={false}
                fill={null}
                shape={(props) => {
                  const { x, y, width, height, payload } = props;
                  const isSelected = payload.month === selectedMonth;
                  return <rect x={x} y={y} width={width} height={height} fill={isSelected ? '#e05010' : '#FF8042'} stroke={isSelected ? '#a03000' : 'none'} strokeWidth={isSelected ? 2 : 0} />;
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* AI Insights Panel */}
        <InsightsPanel 
          selectedMonth={selectedMonth}
          onMonthChange={setSelectedMonth}
          hierarchy={hierarchy}
          goals={goals}
          setGoals={setGoals}
          groupedData={groupedData}
          totalExpenses={totalExpenses}
          avgMonthlyIncome={avgMonthlyIncome}
          COLORS={COLORS}
          formatCurrency={formatCurrency}
        />

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(500px, 1fr))', gap: 24 }}>
          {/* Expense Trends */}
          <div style={{ ...cardStyle }}>
            <h3 style={{ marginTop: 0, color: '#0f172a', fontWeight: 700, fontSize: 16 }}>📈 Expense Trends by Category</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={lineChartData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {categories.slice(0, 8).map((cat, idx) => (
                  <Line key={cat} type="monotone" dataKey={cat} stroke={COLORS[idx % COLORS.length]} strokeWidth={2} dot={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
            {categories.length > 8 && (
              <p style={{ fontSize: 12, color: '#666', marginTop: 8 }}>
                * Showing top 8 categories. Total: {categories.length}
              </p>
            )}
          </div>

          {/* Pie Chart */}
          <div style={{ ...cardStyle }}>
            <h3 style={{ marginTop: 0, color: '#0f172a', fontWeight: 700, fontSize: 16 }}>🥧 {formatMonth(selectedMonth)} Category Breakdown</h3>
            <ResponsiveContainer width="100%" height={350}>
              <PieChart>
                <Pie
                  data={groupedData}
                  dataKey="amount"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  outerRadius={130}
                  fill="#8884d8"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  onClick={handlePieClick}
                  isAnimationActive={true}
                >
                  {groupedData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                      stroke={selectedCategory === entry.category || (parentMap[selectedCategory] === undefined && entry.subcategories?.some(s => s.category === selectedCategory)) ? "#222" : "#fff"}
                      strokeWidth={selectedCategory === entry.category ? 3 : 1}
                      cursor="pointer"
                    />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => formatCurrency(value)} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ marginTop: 16, textAlign: 'center' }}>
              <div style={{ fontSize: 14, color: '#666', marginBottom: 8 }}>
                💡 Click a slice to filter the table below
              </div>
              {selectedCategory && (
                <button 
                  style={{ 
                    padding: '8px 16px', 
                    backgroundColor: '#0088FE', 
                    color: '#fff', 
                    border: 'none', 
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 14
                  }} 
                  onClick={() => setSelectedCategory(null)}
                >
                  Clear Filter ({selectedCategory})
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Expense Table */}
        <div style={{ ...cardStyle, marginTop: 24 }}>
          <h3 style={{ marginTop: 0, color: '#0f172a', fontWeight: 700, fontSize: 16 }}>
            📋 Expense Details - {formatMonth(selectedMonth)}
            {selectedCategory && <span style={{ color: '#0088FE', fontWeight: 'normal' }}> (Filtered by: {selectedCategory})</span>}
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8f9fa' }}>
                  <th style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'left' }}>Category</th>
                  <th style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>Amount</th>
                  <th style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>% of Total</th>
                </tr>
              </thead>
              <tbody>
                {selectedCategory ? (
                  // Filtered view: flat rows matching selected category
                  filteredData.sort((a, b) => b.amount - a.amount).map((row, idx) => (
                    <tr
                      key={row.category}
                      style={{ backgroundColor: idx % 2 ? '#f8f9fa' : '#fff', cursor: 'pointer' }}
                      onClick={() => setSelectedCategory(row.category === selectedCategory ? null : row.category)}
                    >
                      <td style={{ border: '1px solid #dee2e6', padding: 12 }}>
                        <span style={{ display: 'inline-block', width: 12, height: 12, backgroundColor: COLORS[groupedData.findIndex(g => g.category === (parentMap[row.category] || row.category)) % COLORS.length], marginRight: 8, borderRadius: 2 }}></span>
                        {parentMap[row.category] && <span style={{ color: '#64748b', fontSize: 12, marginRight: 6 }}>↳</span>}
                        {row.category}
                      </td>
                      <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right', fontWeight: 'bold' }}>{formatCurrency(row.amount)}</td>
                      <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>{((row.amount / totalExpenses) * 100).toFixed(1)}%</td>
                    </tr>
                  ))
                ) : (
                  // Grouped view: parent rows expandable to show subcategories
                  groupedData.map((group, idx) => {
                    const hasSubs = group.subcategories.length > 0;
                    const isExpanded = expandedParents.has(group.category);
                    const colorIdx = idx % COLORS.length;
                    const toggleParent = () => {
                      if (!hasSubs) return;
                      setExpandedParents(prev => {
                        const next = new Set(prev);
                        next.has(group.category) ? next.delete(group.category) : next.add(group.category);
                        return next;
                      });
                    };
                    return (
                      <React.Fragment key={group.category}>
                        <tr
                          style={{ backgroundColor: idx % 2 ? '#f8f9fa' : '#fff', cursor: hasSubs ? 'pointer' : 'default' }}
                          onClick={hasSubs ? toggleParent : () => setSelectedCategory(group.category)}
                        >
                          <td style={{ border: '1px solid #dee2e6', padding: 12 }}>
                            <span style={{ display: 'inline-block', width: 12, height: 12, backgroundColor: COLORS[colorIdx], marginRight: 8, borderRadius: 2 }}></span>
                            {hasSubs && <span style={{ marginRight: 6, fontSize: 10, color: '#64748b' }}>{isExpanded ? '▼' : '▶'}</span>}
                            {group.category}
                            {hasSubs && <span style={{ marginLeft: 8, fontSize: 11, color: '#94a3b8' }}>({group.subcategories.length} subcategories)</span>}
                          </td>
                          <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right', fontWeight: 'bold' }}>{formatCurrency(group.amount)}</td>
                          <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>{((group.amount / totalExpenses) * 100).toFixed(1)}%</td>
                        </tr>
                        {hasSubs && isExpanded && group.subcategories.sort((a, b) => b.amount - a.amount).map((sub) => (
                          <tr
                            key={sub.category}
                            style={{ backgroundColor: '#eef2ff', cursor: 'pointer' }}
                            onClick={() => setSelectedCategory(sub.category)}
                          >
                            <td style={{ border: '1px solid #dee2e6', padding: '8px 12px 8px 36px', color: '#4f46e5' }}>
                              <span style={{ marginRight: 6 }}>↳</span>
                              {sub.category}
                            </td>
                            <td style={{ border: '1px solid #dee2e6', padding: '8px 12px', textAlign: 'right', fontWeight: 500 }}>{formatCurrency(sub.amount)}</td>
                            <td style={{ border: '1px solid #dee2e6', padding: '8px 12px', textAlign: 'right', color: '#64748b' }}>{((sub.amount / totalExpenses) * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </React.Fragment>
                    );
                  })
                )}
                <tr style={{ backgroundColor: '#e9ecef', fontWeight: 'bold' }}>
                  <td style={{ border: '1px solid #dee2e6', padding: 12 }}>TOTAL</td>
                  <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>
                    {formatCurrency(filteredData.reduce((sum, d) => sum + d.amount, 0))}
                  </td>
                  <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>100%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ textAlign: 'center', marginTop: 32, color: '#94a3b8', fontSize: 13 }}>
          <p>Data refreshes automatically when the page loads</p>
        </div>
      </div>
      )} {/* end overview tab */}

      {/* ── Investments Tab ── */}
      {activeTab === 'investments' && (() => {
        const availableInvMonths = Array.from(new Set(transfers.map(t => t.month))).sort().reverse();
        const monthRows = transfers.filter(t => t.month === invFilterMonth);
        const netOut = rows => rows.filter(t => t.direction === 'Out').reduce((s, t) => s + t.amount, 0)
                             - rows.filter(t => t.direction === 'In').reduce((s, t) => s + t.amount, 0);
        const totalInvested  = rows => rows.filter(t => t.direction === 'Out').reduce((s, t) => s + t.amount, 0);
        const totalReturned  = rows => rows.filter(t => t.direction === 'In').reduce((s, t) => s + t.amount, 0);

        const SummaryCard = ({ label, rows, accent }) => {
          const out = totalInvested(rows), inp = totalReturned(rows);
          return (
            <div style={{ ...cardStyle, flex: 1, minWidth: 220 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: accent, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>{label}</div>
              <div style={{ display: 'flex', gap: 24 }}>
                <div>
                  <div style={{ fontSize: 10, color: '#ef4444', fontWeight: 700, marginBottom: 2 }}>INVESTED</div>
                  <div style={{ fontWeight: 700, fontSize: 18, color: '#0f172a' }}>{formatCurrency(out)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: '#22c55e', fontWeight: 700, marginBottom: 2 }}>RETURNED</div>
                  <div style={{ fontWeight: 700, fontSize: 18, color: '#0f172a' }}>{formatCurrency(inp)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: '#64748b', fontWeight: 700, marginBottom: 2 }}>NET OUT</div>
                  <div style={{ fontWeight: 700, fontSize: 18, color: out - inp > 0 ? '#ef4444' : '#22c55e' }}>{formatCurrency(out - inp)}</div>
                </div>
              </div>
            </div>
          );
        };

        return (
          <div style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 32px' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ margin: '0 0 6px 0', color: '#0f172a' }}>💼 Investment Transfers</h2>
                <p style={{ margin: 0, color: '#64748b', fontSize: 14 }}>Transactions categorised as Investment or Investment Transfer. Excluded from expense totals.</p>
              </div>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Month</div>
                <select
                  value={invFilterMonth}
                  onChange={e => setInvFilterMonth(e.target.value)}
                  style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 13, background: '#fff', fontWeight: 600, color: '#0f172a', minWidth: 130 }}
                >
                  {availableInvMonths.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            </div>

            {transfersLoading && <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>Loading transfers…</div>}

            {!transfersLoading && (
              <>
                {/* Summary cards */}
                <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
                  <SummaryCard label={`${invFilterMonth} — month total`} rows={monthRows} accent='#4f46e5' />
                  <SummaryCard label='All time — grand total' rows={transfers} accent='#0891b2' />
                </div>

                {/* Tag Investment Returns section */}
                {(() => {
                  // Find income entries for invFilterMonth that are from investment-likely sources
                  // and not yet tagged as Investment Return
                  const INVESTMENT_PLACES = ['investment', 'brokerage', 'trading', 'portfolio', 'securities', 'fund',
                    'robinhood', 'edward jones', 'cash app', 'vanguard', 'fidelity', 'schwab', 'ameritrade',
                    'webull', 'acorns', 'stash', 'betterment', 'wealthfront', 'sofi'];
                  const potential = incomeEntries.filter(e =>
                    e.month === invFilterMonth &&
                    e.category !== 'Investment Return' &&
                    INVESTMENT_PLACES.some(p => e.place.toLowerCase().includes(p))
                  );
                  const alreadyTagged = incomeEntries.filter(e =>
                    e.month === invFilterMonth && e.category === 'Investment Return'
                  );
                  if (potential.length === 0 && alreadyTagged.length === 0) return null;
                  return (
                    <div style={{ ...cardStyle, marginBottom: 24 }}>
                      <h3 style={{ margin: '0 0 4px 0', color: '#0f172a', fontSize: 15 }}>💰 Investment Income — {invFilterMonth}</h3>
                      <p style={{ margin: '0 0 14px 0', fontSize: 12, color: '#64748b' }}>Money received from investment accounts. These are automatically counted in the ↓ In totals above.</p>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                          <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                            <th style={{ padding: '9px 12px', textAlign: 'left', color: '#475569', fontWeight: 600 }}>Date</th>
                            <th style={{ padding: '9px 12px', textAlign: 'left', color: '#475569', fontWeight: 600 }}>From</th>
                            <th style={{ padding: '9px 12px', textAlign: 'right', color: '#475569', fontWeight: 600 }}>Amount</th>
                            <th style={{ padding: '9px 12px', textAlign: 'center', color: '#475569', fontWeight: 600 }}>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...alreadyTagged, ...potential].sort((a,b) => a.date < b.date ? 1 : -1).map((e, i) => (
                            <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '9px 12px', color: '#64748b' }}>{e.date}</td>
                              <td style={{ padding: '9px 12px', fontWeight: 600 }}>{e.place}</td>
                              <td style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 700, color: '#16a34a' }}>+{formatCurrency(e.amount)}</td>
                              <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                                <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 10, fontWeight: 700, background: '#f0fdf4', color: '#16a34a' }}>✓ Auto-detected</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}

                {transfers.length === 0 ? (
                  <div style={{ ...cardStyle, textAlign: 'center', padding: 48, color: '#94a3b8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>💭</div>
                    <p style={{ margin: '0 0 8px 0', fontWeight: 600 }}>No investment transfers found</p>
                    <p style={{ margin: 0, fontSize: 13 }}>Categorise a transaction as Investment in the All Expenses tab to see it here.</p>
                  </div>
                ) : monthRows.length === 0 ? (
                  <div style={{ ...cardStyle, textAlign: 'center', padding: 48, color: '#94a3b8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
                    <p style={{ margin: 0, fontWeight: 600 }}>No investment transfers for {invFilterMonth}</p>
                  </div>
                ) : (
                  <div style={{ ...cardStyle }}>
                    <h3 style={{ margin: '0 0 16px 0', color: '#0f172a', fontSize: 15 }}>Transfers — {invFilterMonth}</h3>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                          <th style={{ padding: '10px 12px', textAlign: 'left', color: '#475569', fontWeight: 600 }}>Date</th>
                          <th style={{ padding: '10px 12px', textAlign: 'left', color: '#475569', fontWeight: 600 }}>Firm</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right', color: '#475569', fontWeight: 600 }}>Amount</th>
                          <th style={{ padding: '10px 12px', textAlign: 'center', color: '#475569', fontWeight: 600 }}>Direction</th>
                          <th style={{ padding: '10px 12px', textAlign: 'center', color: '#475569', fontWeight: 600 }}>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...monthRows].sort((a, b) => (a.date < b.date ? 1 : -1)).map((t, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '9px 12px', color: '#64748b' }}>{t.date}</td>
                            <td style={{ padding: '9px 12px', fontWeight: 600, color: '#0f172a' }}>{t.place}</td>
                            <td style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 700, color: t.direction === 'In' ? '#16a34a' : '#dc2626' }}>
                              {t.direction === 'In' ? '+' : '-'}{formatCurrency(t.amount)}
                            </td>
                            <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 700, background: t.direction === 'In' ? '#f0fdf4' : '#fef2f2', color: t.direction === 'In' ? '#16a34a' : '#dc2626' }}>
                                {t.direction === 'In' ? '↓ In' : '↑ Out'}
                              </span>
                            </td>
                            <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                              <select
                                value={t.label || ''}
                                onChange={e => handleTransferLabel(t, e.target.value || null)}
                                style={{ fontSize: 12, padding: '4px 8px', borderRadius: 5, border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', color: t.label === 'Retirement' ? '#4f46e5' : t.label === 'Personal' ? '#0891b2' : '#94a3b8', fontWeight: t.label ? 700 : 400 }}
                              >
                                <option value=''>Unlabeled</option>
                                <option value='Retirement'>🏦 Retirement</option>
                                <option value='Personal'>📈 Personal</option>
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        );
      })()} {/* end investments tab */}

      {/* ── Statements Tab ── */}
      {activeTab === 'statements' && (() => {
        const currentMonthFiles = (statementsData.find(s => s.month === stmtUploadMonth) || {}).files || [];
        const pdfs = currentMonthFiles.filter(f => f.type === 'pdf');

        const uploadFiles = async (fileList) => {
          setStmtUploading(true);
          setStmtError('');
          for (const file of fileList) {
            if (!file.name.toLowerCase().endsWith('.pdf')) continue;
            const form = new FormData();
            form.append('file', file);
            try {
              const res = await fetch(`http://localhost:8000/api/statements/${stmtUploadMonth}/upload`, { method: 'POST', body: form });
              const data = await res.json();
              if (!res.ok) throw new Error(data.error || 'Upload failed');
            } catch (err) {
              setStmtError(`Upload failed: ${err.message}`);
            }
          }
          const updated = await fetch('http://localhost:8000/api/statements').then(r => r.json());
          setStatementsData(Array.isArray(updated) ? updated : []);
          setStmtUploading(false);
        };

        const processMonth = async () => {
          setStmtProcessing(true);
          setStmtLog('⏳ Starting ' + stmtUploadMonth + '...');
          setStmtError('');
          try {
            const res = await fetch(`http://localhost:8000/api/statements/${stmtUploadMonth}/process${stmtForce ? '?force=true' : ''}`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Processing failed');
            const jobId = data.job_id;
            // Poll until done
            while (true) {
              await new Promise(r => setTimeout(r, 4000));
              const poll = await fetch(`http://localhost:8000/api/jobs/${jobId}`).then(r => r.json());
              const lines = (poll.output || '').split('\n');
              const lastLines = lines.slice(-6).join('\n');
              setStmtLog('⏳ Processing ' + stmtUploadMonth + '...\n\n' + lastLines);
              if (poll.status === 'done') {
                setStmtLog(poll.output || '✅ Done');
                const updated = await fetch('http://localhost:8000/api/statements').then(r => r.json());
                setStatementsData(Array.isArray(updated) ? updated : []);
                break;
              } else if (poll.status === 'error') {
                const errOutput = poll.output || poll.errors || '';
                if (errOutput) setStmtLog(errOutput);
                throw new Error(poll.error_msg || 'Processing failed');
              }
            }
          } catch (err) {
            setStmtError(err.message);
            // intentionally keep stmtLog so the user can see what failed
          } finally {
            setStmtProcessing(false);
          }
        };

        return (
          <div style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 32px' }}>
            <h2 style={{ margin: '0 0 6px 0', color: '#0f172a' }}>⬆️ Statements</h2>
            <p style={{ margin: '0 0 28px 0', color: '#64748b', fontSize: 14 }}>Upload bank statement PDFs and process them to update all reports.</p>

            {/* Upload panel */}
            <div style={{ ...cardStyle, marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 18, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: 4 }}>Month</div>
                  <input
                    type="month"
                    value={stmtUploadMonth}
                    onChange={e => { setStmtUploadMonth(e.target.value); setStmtLog(''); setStmtError(''); }}
                    style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 13, fontWeight: 600 }}
                  />
                </div>
                <div style={{ fontSize: 12, color: '#94a3b8', paddingTop: 18 }}>Select the month these statements belong to</div>
              </div>

              {/* Drop zone */}
              <div
                onDragOver={e => { e.preventDefault(); setStmtDragOver(true); }}
                onDragLeave={() => setStmtDragOver(false)}
                onDrop={e => { e.preventDefault(); setStmtDragOver(false); uploadFiles(Array.from(e.dataTransfer.files)); }}
                onClick={() => document.getElementById('stmtFileInput').click()}
                style={{
                  border: `2px dashed ${stmtDragOver ? '#4f46e5' : '#cbd5e1'}`,
                  borderRadius: 12,
                  padding: '36px 24px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  background: stmtDragOver ? '#eef2ff' : '#f8fafc',
                  transition: 'all .15s',
                  marginBottom: 16,
                }}
              >
                <div style={{ fontSize: 32, marginBottom: 8 }}>{stmtUploading ? '⏳' : '📄'}</div>
                <div style={{ fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                  {stmtUploading ? 'Uploading...' : 'Drop PDF files here or click to select'}
                </div>
                <div style={{ fontSize: 12, color: '#94a3b8' }}>Bank statement PDFs only</div>
                <input
                  id="stmtFileInput"
                  type="file"
                  multiple
                  accept=".pdf"
                  style={{ display: 'none' }}
                  onChange={e => uploadFiles(Array.from(e.target.files))}
                />
              </div>

              {stmtError && <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 7, padding: '8px 14px', marginBottom: 12, color: '#dc2626', fontSize: 13 }}>{stmtError}</div>}

              {/* Uploaded PDFs for this month */}
              {pdfs.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: 8 }}>PDFs for {formatMonth(stmtUploadMonth)}</div>
                  {pdfs.map(f => (
                    <div key={f.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 12px', background: '#f1f5f9', borderRadius: 7, marginBottom: 5, fontSize: 13 }}>
                      <span style={{ fontWeight: 500 }}>📄 {f.name} <span style={{ color: '#94a3b8', fontWeight: 400 }}>({(f.size / 1024).toFixed(0)} KB)</span></span>
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (!window.confirm(`Delete ${f.name}?`)) return;
                          await fetch(`http://localhost:8000/api/statements/${stmtUploadMonth}/${encodeURIComponent(f.name)}`, { method: 'DELETE' });
                          const updated = await fetch('http://localhost:8000/api/statements').then(r => r.json());
                          setStatementsData(Array.isArray(updated) ? updated : []);
                        }}
                        style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 14, padding: '2px 6px' }}
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}

              <button
                disabled={stmtProcessing || pdfs.length === 0}
                onClick={processMonth}
                style={{
                  padding: '10px 28px', background: stmtProcessing ? '#94a3b8' : pdfs.length === 0 ? '#e2e8f0' : '#4f46e5',
                  color: pdfs.length === 0 ? '#94a3b8' : '#fff', border: 'none', borderRadius: 8,
                  fontSize: 14, fontWeight: 700, cursor: stmtProcessing || pdfs.length === 0 ? 'not-allowed' : 'pointer',
                }}
              >
                {stmtProcessing ? '⏳ Processing…' : '▶️ Process ' + formatMonth(stmtUploadMonth)}
              </button>
              <label style={{ marginLeft: 16, fontSize: 12, color: '#64748b', display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer', userSelect: 'none' }}>
                <input type="checkbox" checked={stmtForce} onChange={e => setStmtForce(e.target.checked)} />
                Force reprocess <span style={{ color: '#94a3b8' }}>(discards manual category edits)</span>
              </label>
              {pdfs.length === 0 && <span style={{ marginLeft: 12, fontSize: 12, color: '#94a3b8' }}>Upload at least one PDF first</span>}

              {stmtLog && (
                <pre style={{ marginTop: 16, background: '#0f172a', color: '#e2e8f0', borderRadius: 8, padding: '14px 16px', fontSize: 12, overflowX: 'auto', maxHeight: 320, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>{stmtLog}</pre>
              )}
            </div>

            {/* Existing months */}
            <div style={{ ...cardStyle }}>
              <h3 style={{ margin: '0 0 16px 0', color: '#0f172a', fontSize: 15 }}>All Statement Months</h3>
              {statementsData.length === 0 ? (
                <div style={{ color: '#94a3b8', textAlign: 'center', padding: 32 }}>No statement months found</div>
              ) : (
                <div style={{ maxHeight: 340, overflowY: 'auto', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 1 }}>
                      <th style={{ padding: '9px 14px', textAlign: 'left', color: '#475569', fontWeight: 600, background: '#f8fafc' }}>Month</th>
                      <th style={{ padding: '9px 14px', textAlign: 'left', color: '#475569', fontWeight: 600, background: '#f8fafc' }}>PDFs</th>
                      <th style={{ padding: '9px 14px', textAlign: 'left', color: '#475569', fontWeight: 600, background: '#f8fafc' }}>Processed</th>
                      <th style={{ padding: '9px 14px', textAlign: 'center', color: '#475569', fontWeight: 600, background: '#f8fafc' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {statementsData.map(s => {
                      const pdfCount = s.files.filter(f => f.type === 'pdf').length;
                      const hasCSV = s.files.some(f => f.type === 'csv' && f.name === 'expenses.csv');
                      return (
                        <tr
                          key={s.month}
                          onClick={() => { setStmtUploadMonth(s.month); setStmtLog(''); setStmtError(''); window.scrollTo(0,0); }}
                          style={{ borderBottom: '1px solid #f1f5f9', cursor: 'pointer', background: stmtUploadMonth === s.month ? '#f0f4ff' : 'transparent', transition: 'background 0.15s' }}
                          onMouseEnter={e => { if (stmtUploadMonth !== s.month) e.currentTarget.style.background = '#f8fafc'; }}
                          onMouseLeave={e => { e.currentTarget.style.background = stmtUploadMonth === s.month ? '#f0f4ff' : 'transparent'; }}>
                          <td style={{ padding: '9px 14px', fontWeight: 700 }}>{s.month}</td>
                          <td style={{ padding: '9px 14px', color: '#64748b' }}>{pdfCount} PDF{pdfCount !== 1 ? 's' : ''}</td>
                          <td style={{ padding: '9px 14px' }}>
                            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 700, background: hasCSV ? '#f0fdf4' : '#fef9c3', color: hasCSV ? '#16a34a' : '#b45309' }}>
                              {hasCSV ? '✓ Yes' : '⏳ Not yet'}
                            </span>
                          </td>
                          <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                await fetch(`http://localhost:8000/api/statements/${s.month}`, { method: 'DELETE' });
                                const updated = await fetch('http://localhost:8000/api/statements').then(r => r.json());
                                setStatementsData(Array.isArray(updated) ? updated : []);
                                if (stmtUploadMonth === s.month) { setStmtLog(''); setStmtError(''); }
                              }}
                              style={{ fontSize: 12, padding: '4px 10px', borderRadius: 6, border: '1px solid #fca5a5', background: '#fff', cursor: 'pointer', color: '#ef4444', fontWeight: 600 }}>
                              🗑
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                </div>
              )}
            </div>
          </div>
        );
      })()}

    </div>
  );
}

export default App;
