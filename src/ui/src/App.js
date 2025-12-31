import React, { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, BarChart, Bar, ComposedChart } from "recharts";

const COLORS = [
  "#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#A28CFF", "#FF6699", "#33CC99", "#FF4444", "#FFB347", "#B6D7A8",
  "#FFD700", "#FF7F50", "#6495ED", "#DC143C", "#20B2AA", "#FF6347", "#4682B4", "#32CD32"
];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
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

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch("http://localhost:8000/api/expense-categories").then(res => res.json()),
      fetch("http://localhost:8000/api/expenses-by-month").then(res => res.json()),
      fetch("http://localhost:8000/api/income-by-month").then(res => res.json())
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
  }, []);


  const handlePieClick = (data, index) => {
    setSelectedCategory(data.category === selectedCategory ? null : data.category);
  };

  const filteredData = selectedCategory
    ? data.filter((d) => d.category === selectedCategory)
    : data;

  // Calculate totals
  const totalExpenses = data.reduce((sum, d) => sum + d.amount, 0);
  const totalIncome = incomeData.reduce((sum, d) => sum + d.income, 0);
  const avgMonthlyExpense = totalExpenses / (data.length > 0 ? 1 : 1); // Previous month only
  const avgMonthlyIncome = incomeData.length > 0 ? totalIncome / incomeData.length : 0;
  
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
      savings: (income ? income.income : 0) - (expense ? expense.total : 0)
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

  return (
    <div style={{ padding: 32, fontFamily: 'sans-serif', backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <h1 style={{ marginBottom: 8 }}>💰 Automated Budgeting Dashboard</h1>
        <p style={{ color: '#666', marginBottom: 32 }}>
          Track your expenses and income across time
        </p>

        {/* Summary Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 32 }}>
          <div style={{ backgroundColor: '#fff', padding: 20, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: 14, color: '#666', marginBottom: 8 }}>Last Month Expenses</div>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#FF8042' }}>{formatCurrency(totalExpenses)}</div>
          </div>
          <div style={{ backgroundColor: '#fff', padding: 20, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: 14, color: '#666', marginBottom: 8 }}>Avg Monthly Income</div>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#00C49F' }}>{formatCurrency(avgMonthlyIncome)}</div>
          </div>
          <div style={{ backgroundColor: '#fff', padding: 20, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: 14, color: '#666', marginBottom: 8 }}>Avg Monthly Savings</div>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: avgMonthlyIncome - avgMonthlyExpense > 0 ? '#00C49F' : '#FF4444' }}>
              {formatCurrency(avgMonthlyIncome - avgMonthlyExpense)}
            </div>
          </div>
          <div style={{ backgroundColor: '#fff', padding: 20, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: 14, color: '#666', marginBottom: 8 }}>Categories</div>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#0088FE' }}>{categories.length}</div>
          </div>
        </div>

        {/* Income vs Expense Comparison */}
        <div style={{ backgroundColor: '#fff', padding: 24, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginBottom: 24 }}>
          <h3 style={{ marginTop: 0 }}>📊 Income vs Expenses (12 Months)</h3>
          <ResponsiveContainer width="100%" height={350}>
            <ComposedChart data={incomeVsExpenseData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Bar dataKey="income" fill="#00C49F" name="Income" />
              <Bar dataKey="expense" fill="#FF8042" name="Expenses" />
              <Line type="monotone" dataKey="savings" stroke="#0088FE" strokeWidth={2} name="Savings" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(500px, 1fr))', gap: 24 }}>
          {/* Expense Trends */}
          <div style={{ backgroundColor: '#fff', padding: 24, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <h3 style={{ marginTop: 0 }}>📈 Expense Trends by Category</h3>
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
          <div style={{ backgroundColor: '#fff', padding: 24, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <h3 style={{ marginTop: 0 }}>🥧 Last Month Category Breakdown</h3>
            <ResponsiveContainer width="100%" height={350}>
              <PieChart>
                <Pie
                  data={data}
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
                  {data.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                      stroke={selectedCategory === entry.category ? "#222" : "#fff"}
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
        <div style={{ backgroundColor: '#fff', padding: 24, borderRadius: 8, boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginTop: 24 }}>
          <h3 style={{ marginTop: 0 }}>
            📋 Expense Details
            {selectedCategory && <span style={{ color: '#0088FE', fontWeight: 'normal' }}> - Filtered by: {selectedCategory}</span>}
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
                {filteredData
                  .sort((a, b) => b.amount - a.amount)
                  .map((row, idx) => (
                    <tr 
                      key={row.category} 
                      style={{ 
                        backgroundColor: idx % 2 ? '#f8f9fa' : '#fff',
                        cursor: 'pointer'
                      }}
                      onClick={() => setSelectedCategory(row.category === selectedCategory ? null : row.category)}
                    >
                      <td style={{ border: '1px solid #dee2e6', padding: 12 }}>
                        <span style={{ 
                          display: 'inline-block', 
                          width: 12, 
                          height: 12, 
                          backgroundColor: COLORS[data.indexOf(row) % COLORS.length],
                          marginRight: 8,
                          borderRadius: 2
                        }}></span>
                        {row.category}
                      </td>
                      <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right', fontWeight: 'bold' }}>
                        {formatCurrency(row.amount)}
                      </td>
                      <td style={{ border: '1px solid #dee2e6', padding: 12, textAlign: 'right' }}>
                        {((row.amount / totalExpenses) * 100).toFixed(1)}%
                      </td>
                    </tr>
                  ))}
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

        <div style={{ textAlign: 'center', marginTop: 32, color: '#999', fontSize: 14 }}>
          <p>Data refreshes automatically when the page loads</p>
        </div>
      </div>
    </div>
  );
}

export default App;
