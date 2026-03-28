import React, { useState, useEffect } from 'react';
import './InsightsPanel.css';

const getPrevMonth = () => {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

const getThisMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

function InsightsPanel({ selectedMonth, onMonthChange, subcategories = {}, goals = {}, setGoals, groupedData = [], totalExpenses = 0, avgMonthlyIncome = 0, COLORS = [], formatCurrency, forcedTab }) {
  const [currentMonth, setCurrentMonth] = useState(selectedMonth || getPrevMonth());
  const [tempMonth, setTempMonth] = useState(selectedMonth || getPrevMonth());
  const [insights, setInsights] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [trends, setTrends] = useState(null);
  const [budgetSuggestions, setBudgetSuggestions] = useState(null);
  const [budgetComparison, setBudgetComparison] = useState(null);
  const [oneTimeExpenses, setOneTimeExpenses] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatAvailable, setChatAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [availableMonths, setAvailableMonths] = useState([]);
  const [savingsGoal, setSavingsGoal] = useState('');
  const [activeTab, setActiveTab] = useState(forcedTab || 'insights');
  const [planSection, setPlanSection] = useState('budget'); // 'budget' | 'forecast' | 'one-time'

  // Keep internal tab in sync when parent controls it
  useEffect(() => {
    if (forcedTab) setActiveTab(forcedTab);
  }, [forcedTab]);
  const [insightsError, setInsightsError] = useState(null);
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [editingGoal, setEditingGoal] = useState(null);

  const saveGoal = (category, value) => {
    const updated = { ...goals, [category]: value === '' ? undefined : parseFloat(value) };
    if (setGoals) setGoals(updated);
    localStorage.setItem('budgetGoals', JSON.stringify(updated));
    setEditingGoal(null);
  };

  // Auto-populate Your Goal from AI suggestions when they first load
  useEffect(() => {
    if (!budgetSuggestions?.suggested_budgets || !setGoals) return;
    const updated = { ...goals };
    let changed = false;
    for (const [cat, entry] of Object.entries(budgetSuggestions.suggested_budgets)) {
      if (updated[cat] === undefined || updated[cat] === null || isNaN(updated[cat])) {
        updated[cat] = entry.suggested_amount;
        changed = true;
      }
    }
    if (changed) {
      setGoals(updated);
      localStorage.setItem('budgetGoals', JSON.stringify(updated));
    }
  }, [budgetSuggestions]); // intentionally omit goals/setGoals to avoid loops

  // Build sub→parent reverse map from subcategories
  const parentMap = {};
  for (const [parent, subs] of Object.entries(subcategories)) {
    for (const sub of subs) parentMap[sub] = parent;
  }

  // Group a flat category list by parent, rolling up subcategory amounts
  const groupCategories = (catList) => {
    const groups = new Map();
    for (const cat of catList) {
      const parent = parentMap[cat.category] || cat.category;
      if (!groups.has(parent)) groups.set(parent, { category: parent, amount: 0, subcategories: [] });
      const g = groups.get(parent);
      g.amount += cat.amount;
      if (parentMap[cat.category]) g.subcategories.push(cat);
    }
    return Array.from(groups.values()).sort((a, b) => b.amount - a.amount);
  };

  useEffect(() => {
    // Sync with parent's selectedMonth
    if (selectedMonth) {
      setCurrentMonth(selectedMonth);
      setTempMonth(selectedMonth);
      loadData(selectedMonth);
      setChatMessages([]); // Clear chat history when month changes
    } else {
      // Default to previous complete month
      const monthStr = getPrevMonth();
      setCurrentMonth(monthStr);
      setTempMonth(monthStr);
      loadData(monthStr);
      setChatMessages([]); // Clear chat history on initial load
    }
    
    // Check if chat is available
    const checkChatAvailability = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/chat/available');
        const data = await response.json();
        setChatAvailable(data.available);
      } catch (error) {
        console.error('Failed to check chat availability:', error);
        setChatAvailable(false);
      }
    };
    
    checkChatAvailability();

    // Fetch available months for error hint
    fetch('http://localhost:8000/api/available-months')
      .then(r => r.json())
      .then(months => setAvailableMonths(months))
      .catch(() => {});
  }, [selectedMonth]);

  const handleMonthUpdate = () => {
    setCurrentMonth(tempMonth);
    loadData(tempMonth);
    // Update parent component's selected month
    if (onMonthChange) {
      onMonthChange(tempMonth);
    }
  };

  const loadData = async (month) => {
    setLoading(true);
    setInsightsError(null);
    try {
      // Load insights for selected month
      const insightsRes = await fetch(`http://localhost:8000/api/insights/${month}`);
      if (insightsRes.ok) {
        const insightsData = await insightsRes.json();
        if (insightsData.error) {
          setInsightsError(insightsData.error);
          setInsights(null);
        } else {
          setInsights(insightsData);
        }
      } else {
        setInsightsError('Failed to load insights');
        setInsights(null);
      }

      // Load forecast
      const forecastRes = await fetch('http://localhost:8000/api/forecast?months_ahead=1');
      if (forecastRes.ok) {
        const forecastData = await forecastRes.json();
        setForecast(forecastData);
      }

      // Load trends
      const trendsRes = await fetch('http://localhost:8000/api/trends?months=6');
      if (trendsRes.ok) {
        const trendsData = await trendsRes.json();
        setTrends(trendsData);
      }

      // Load budget suggestions
      loadBudgetData(month);
      
    } catch (error) {
      console.error('Failed to load insights:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadBudgetData = async (month) => {
    try {
      // Load AI budget suggestions
      const suggRes = await fetch('http://localhost:8000/api/budget-suggestions?analysis_months=3');
      if (suggRes.ok) {
        const suggData = await suggRes.json();
        setBudgetSuggestions(suggData);
      }

      // Load budget comparison for current month
      const compRes = await fetch(`http://localhost:8000/api/budget/${month}`);
      if (compRes.ok) {
        const compData = await compRes.json();
        setBudgetComparison(compData);
      } else {
        setBudgetComparison(null);
      }

      // Load one-time expenses
      const otRes = await fetch('http://localhost:8000/api/one-time-expenses');
      if (otRes.ok) {
        const otData = await otRes.json();
        setOneTimeExpenses(Array.isArray(otData) ? otData : []);
      }
    } catch (error) {
      console.error('Failed to load budget data:', error);
    }
  };

  const saveBudgets = async () => {
    if (!budgetSuggestions || !budgetSuggestions.suggested_budgets) return;

    try {
      const response = await fetch('http://localhost:8000/api/budget/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(budgetSuggestions.suggested_budgets)
      });

      if (response.ok) {
        alert('Budget goals saved successfully!');
        loadBudgetData(currentMonth);
      }
    } catch (error) {
      console.error('Failed to save budgets:', error);
      alert('Failed to save budgets');
    }
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim()) return;
    
    const userMessage = chatInput.trim();
    setChatInput('');
    setChatLoading(true);
    
    // Add user message to chat
    const updatedMessages = [...chatMessages, { role: 'user', content: userMessage }];
    setChatMessages(updatedMessages);
    
    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache'
        },
        cache: 'no-store',
        body: JSON.stringify({
          message: userMessage,
          conversation_history: chatMessages
        })
      });
      
      const data = await response.json();
      
      // Add assistant response to chat
      setChatMessages(data.conversation_history || [
        ...updatedMessages,
        { role: 'assistant', content: data.response, expenses: data.expenses, actions_taken: data.actions_taken }
      ]);
    } catch (error) {
      console.error('Chat error:', error);
      setChatMessages([
        ...updatedMessages,
        { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleForecastWithGoal = async () => {
    if (!savingsGoal || isNaN(savingsGoal)) return;
    
    try {
      const res = await fetch(
        `http://localhost:8000/api/forecast?months_ahead=1&savings_goal=${savingsGoal}`
      );
      if (res.ok) {
        const data = await res.json();
        setForecast(data);
      }
    } catch (error) {
      console.error('Failed to load forecast with goal:', error);
    }
  };

  if (loading) {
    return <div className="insights-panel loading">Loading insights...</div>;
  }

  return (
    <div className="insights-panel">
      <div className="insights-header">
        <div className="insights-header-top">
          <h2>💡 AI Financial Insights</h2>
          {insights && insights.ai_generated && insights.model_name && (
            <div className="ai-badge">
              <span>🤖</span>
              <span>AI: {insights.model_name}</span>
            </div>
          )}
          {insights && !insights.ai_generated && (
            <div className="ai-badge" style={{ background: 'rgba(255,255,255,.15)' }}>
              <span>📊 Rule-based</span>
            </div>
          )}
        </div>
        {!forcedTab && (
          <div className="tabs">
            <button 
              className={activeTab === 'insights' ? 'active' : ''} 
              onClick={() => setActiveTab('insights')}
            >
              Insights
            </button>
            <button 
              className={activeTab === 'trends' ? 'active' : ''} 
              onClick={() => setActiveTab('trends')}
            >
              Trends
            </button>
            {chatAvailable && (
              <button 
                className={activeTab === 'chat' ? 'active' : ''} 
                onClick={() => setActiveTab('chat')}
              >
                💬 Chat
              </button>
            )}
          </div>
        )}
      </div>

      {activeTab === 'insights' && (
        <div className="tab-content">
          {insightsError && (
            <div className="error-message">
              <p>⚠️ {insightsError}</p>
              <p className="error-hint">📊 Insights are available for: <strong>{availableMonths.length > 0 ? `${new Date(availableMonths[availableMonths.length - 1] + '-02').toLocaleString('default', { month: 'long', year: 'numeric' })} – ${new Date(availableMonths[0] + '-02').toLocaleString('default', { month: 'long', year: 'numeric' })}` : 'no processed months yet'}</strong></p>
              <p className="error-hint">Process statements for this month to generate insights.</p>
            </div>
          )}
          
          {insights && (
          <>
          {/* Summary Stats */}
          <div className="summary-cards">
            <div className="stat-card">
              <div className="stat-label">Total Spending</div>
              <div className="stat-value">
                ${(insights.month_over_month?.current ?? insights.top_categories?.reduce((sum, cat) => sum + cat.amount, 0) ?? 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </div>
            </div>
            {insights.month_over_month && (
              <div className="stat-card">
                <div className="stat-label">vs Last Month</div>
                <div className={`stat-value ${insights.month_over_month.change_percent > 0 ? 'negative' : 'positive'}`}>
                  {insights.month_over_month.change_percent > 0 ? '+' : ''}
                  {insights.month_over_month.change_percent.toFixed(1)}%
                </div>
              </div>
            )}
            <div className="stat-card">
              <div className="stat-label">Top Category</div>
              <div className="stat-value small">
                {insights.top_categories?.[0]?.category || 'N/A'}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Anomalies Detected</div>
              <div className="stat-value">
                {insights.anomalies?.length || 0}
              </div>
            </div>
          </div>

          {/* Top Categories */}
          {insights.top_categories && insights.top_categories.length > 0 && (
            <div className="insights-section">
              <h3>📊 Top Spending Categories</h3>
              <div className="category-list">
                {groupCategories(insights.top_categories).map((group) => {
                  const hasSubs = group.subcategories.length > 0;
                  const isExpanded = expandedGroups.has(group.category);
                  const toggle = () => setExpandedGroups(prev => {
                    const next = new Set(prev);
                    next.has(group.category) ? next.delete(group.category) : next.add(group.category);
                    return next;
                  });
                  return (
                    <React.Fragment key={group.category}>
                      <div className={`category-item${hasSubs ? ' expandable' : ''}`} onClick={hasSubs ? toggle : undefined}>
                        <div className="category-name">
                          {group.category}
                          {hasSubs && <span className={`category-expand-icon${isExpanded ? ' expanded' : ''}`}>▶</span>}
                        </div>
                        <div className="category-amount">${group.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
                      </div>
                      {hasSubs && isExpanded && group.subcategories
                        .sort((a, b) => b.amount - a.amount)
                        .map((sub) => (
                          <div key={sub.category} className="subcategory-item">
                            <div className="subcategory-name">↳ {sub.category}</div>
                            <div className="subcategory-amount">${sub.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
                          </div>
                        ))}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
          )}

          {/* Significant Changes */}
          {insights.category_changes && insights.category_changes.length > 0 && (
            <div className="insights-section">
              <h3>📈 Significant Changes</h3>
              <div className="changes-list">
                {insights.category_changes.slice(0, 5).map((change, idx) => (
                  <div key={idx} className={`change-item ${change.change_percent > 0 ? 'increase' : 'decrease'}`}>
                    <div className="change-header">
                      <span className="change-category">{change.category}</span>
                      <span className={`change-badge ${change.change_percent > 0 ? 'bad' : 'good'}`}>
                        {change.change_percent > 0 ? '↑' : '↓'} {Math.abs(change.change_percent).toFixed(1)}%
                      </span>
                    </div>
                    <div className="change-amounts">
                      ${change.previous.toFixed(2)} → ${change.current.toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Unusual Transactions (Anomalies) */}
          {insights.anomalies && insights.anomalies.length > 0 && (
            <div className="insights-section anomalies">
              <h3>⚠️ Unusual Transactions</h3>
              <p className="section-description">
                These transactions are significantly higher than normal for their category
              </p>
              <div className="anomalies-list">
                {insights.anomalies.map((anomaly, idx) => (
                  <div key={idx} className="anomaly-item">
                    <div className="anomaly-header">
                      <span className="anomaly-place">{anomaly.place}</span>
                      <span className="anomaly-amount">${anomaly.amount.toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                    </div>
                    <div className="anomaly-details">
                      <span className="anomaly-category">{anomaly.category}</span>
                      <span className="anomaly-date">{anomaly.date}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {insights.recommendations && insights.recommendations.length > 0 && (
            <div className="insights-section recommendations">
              <h3>💡 Recommendations</h3>
              <ul>
                {insights.recommendations.map((rec, idx) => (
                  <li key={idx}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
          </>
          )}
        </div>
      )}

      {activeTab === 'plan' && (
        <div className="tab-content">

          {/* Sub-section toggle */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap' }}>
            <button
              onClick={() => setPlanSection('budget')}
              style={{
                padding: '8px 20px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                fontWeight: '600', fontSize: '14px',
                background: planSection === 'budget' ? 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)' : '#f1f5f9',
                color: planSection === 'budget' ? 'white' : '#475569', transition: 'all 0.18s ease'
              }}
            >
              💰 Budget Goals
            </button>
            <button
              onClick={() => setPlanSection('forecast')}
              style={{
                padding: '8px 20px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                fontWeight: '600', fontSize: '14px',
                background: planSection === 'forecast' ? 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)' : '#f1f5f9',
                color: planSection === 'forecast' ? 'white' : '#475569', transition: 'all 0.18s ease'
              }}
            >
              📈 Next Month Forecast
            </button>
            <button
              onClick={() => setPlanSection('one-time')}
              style={{
                padding: '8px 20px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                fontWeight: '600', fontSize: '14px',
                background: planSection === 'one-time' ? 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)' : '#f1f5f9',
                color: planSection === 'one-time' ? 'white' : '#475569', transition: 'all 0.18s ease'
              }}
            >
              ⚡ One-Time Expenses {oneTimeExpenses.length > 0 && `(${oneTimeExpenses.length})`}
            </button>
          </div>

          {/* ── FORECAST SECTION ── */}
          {planSection === 'forecast' && forecast && (
            <>
              <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                <h3 style={{ marginTop: 0 }}>📈 Next Month Forecast: {forecast.forecast_date}</h3>
                <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
                  <div style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '8px', flex: 1 }}>
                    <div style={{ fontSize: '14px', color: '#666' }}>Predicted Spending</div>
                    <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#FF8042' }}>
                      ${forecast.total_forecast.toFixed(2)}
                    </div>
                  </div>
                  <div style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '8px', flex: 1 }}>
                    <div style={{ fontSize: '14px', color: '#666' }}>Confidence Range</div>
                    <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#0088FE' }}>
                      ${forecast.confidence_low.toFixed(2)} – ${forecast.confidence_high.toFixed(2)}
                    </div>
                  </div>
                </div>

                <div className="savings-goal-input" style={{ marginBottom: '16px' }}>
                  <h4 style={{ marginTop: 0 }}>🎯 Set a Monthly Savings Goal</h4>
                  <div className="input-group">
                    <input
                      type="number"
                      placeholder="e.g. 500"
                      value={savingsGoal}
                      onChange={(e) => setSavingsGoal(e.target.value)}
                    />
                    <button onClick={handleForecastWithGoal}>Update</button>
                  </div>
                </div>

                {forecast.recommendations && (
                  <div className="budget-recommendations">
                    {forecast.recommendations.savings_potential && (
                      <div className="savings-alert">
                        <p>
                          To meet your ${forecast.recommendations.savings_potential.goal.toFixed(2)} savings goal,
                          reduce spending by ${forecast.recommendations.savings_potential.cut_needed.toFixed(2)} ({forecast.recommendations.savings_potential.cut_percentage.toFixed(1)}%)
                        </p>
                      </div>
                    )}
                    {forecast.recommendations.adjustments && forecast.recommendations.adjustments.length > 0 && (
                      <div className="adjustments">
                        {forecast.recommendations.adjustments.map((adj, idx) => (
                          <div key={idx} className={`adjustment ${adj.type}`}>
                            <p>{adj.message}</p>
                            {adj.potential_savings && (
                              <p className="savings-potential">Potential savings: ${adj.potential_savings.toFixed(2)}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '8px' }}>
                <h4 style={{ marginTop: 0 }}>Category Forecasts</h4>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                      <th style={{ padding: '12px', textAlign: 'left' }}>Category</th>
                      <th style={{ padding: '12px', textAlign: 'right' }}>Forecast</th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>Trend</th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>Confidence Range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(forecast.categories || {})
                      .sort((a, b) => b[1].forecast - a[1].forecast)
                      .map(([category, catData]) => (
                        <tr key={category} style={{ borderBottom: '1px solid #f0f0f0' }}>
                          <td style={{ padding: '12px' }}>{category}</td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: '600' }}>${catData.forecast.toFixed(2)}</td>
                          <td style={{ padding: '12px' }} className={`trend-${catData.trend || 'stable'}`}>
                            {catData.trend === 'increasing' ? '📈' : catData.trend === 'decreasing' ? '📉' : '➡️'}
                            {' '}{catData.trend || 'stable'}
                          </td>
                          <td style={{ padding: '12px', color: '#666' }}>
                            ${catData.confidence_low.toFixed(2)} – ${catData.confidence_high.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {planSection === 'forecast' && !forecast && (
            <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
              <p>Loading forecast...</p>
            </div>
          )}

          {/* ── BUDGET SECTION ── */}
          {planSection === 'budget' && budgetSuggestions && (
            <>
              <div className="budget-header" style={{ marginBottom: '24px', backgroundColor: '#fff', padding: '20px', borderRadius: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>💰 AI Budget Recommendations</h3>
                  {budgetSuggestions.ai_generated && budgetSuggestions.model_name && (
                    <div style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '4px 12px',
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      color: 'white',
                      borderRadius: '20px',
                      fontSize: '12px',
                      fontWeight: '600'
                    }}>
                      <span>🤖 {budgetSuggestions.model_name}</span>
                    </div>
                  )}
                </div>
                <p style={{ color: '#666', margin: '8px 0 16px 0' }}>
                  Based on {budgetSuggestions.analysis_period} months of spending history
                </p>
                <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
                  <div style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '8px', flex: 1 }}>
                    <div style={{ fontSize: '14px', color: '#666' }}>Total Suggested Budget</div>
                    <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#00C49F' }}>
                      ${budgetSuggestions.total_budget?.toLocaleString('en-US', {minimumFractionDigits: 2}) || '0.00'}
                    </div>
                  </div>
                  {budgetComparison && (
                    <>
                      <div style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '8px', flex: 1 }}>
                        <div style={{ fontSize: '14px', color: '#666' }}>Actual Spending ({currentMonth})</div>
                        <div style={{ fontSize: '24px', fontWeight: 'bold', color: budgetComparison.on_track ? '#00C49F' : '#FF8042' }}>
                          ${budgetComparison.total_actual?.toFixed(2) || '0.00'}
                        </div>
                      </div>
                      <div style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '8px', flex: 1 }}>
                        <div style={{ fontSize: '14px', color: '#666' }}>Status</div>
                        <div style={{ fontSize: '24px', fontWeight: 'bold', color: budgetComparison.on_track ? '#00C49F' : '#FF8042' }}>
                          {budgetComparison.on_track ? '✓ On Track' : '⚠ Over Budget'}
                        </div>
                      </div>
                    </>
                  )}
                </div>
                <button 
                  onClick={saveBudgets}
                  style={{
                    padding: '10px 20px',
                    backgroundColor: '#667eea',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    transition: 'background-color 0.2s'
                  }}
                  onMouseOver={(e) => e.target.style.backgroundColor = '#5568d3'}
                  onMouseOut={(e) => e.target.style.backgroundColor = '#667eea'}
                >
                  💾 Save Budget Goals
                </button>
              </div>

              {/* Over-income warning banner */}
              {(() => {
                const totalGoals = Object.values(goals || {}).reduce((s, v) => s + (v || 0), 0);
                const isOver = avgMonthlyIncome > 0 && totalGoals > avgMonthlyIncome;
                if (!isOver) return null;
                const overage = totalGoals - avgMonthlyIncome;
                return (
                  <div style={{
                    backgroundColor: '#fef2f2',
                    border: '1px solid #fca5a5',
                    borderRadius: 8,
                    padding: '12px 16px',
                    marginBottom: 16,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    animation: 'goalOverPulse 1.5s ease-in-out infinite'
                  }}>
                    <span style={{ fontSize: 20 }}>🚨</span>
                    <div>
                      <div style={{ fontWeight: 700, color: '#dc2626', fontSize: 14 }}>Your goals exceed 100% of income</div>
                      <div style={{ color: '#b91c1c', fontSize: 12, marginTop: 2 }}>
                        Total goals <strong>{formatCurrency ? formatCurrency(totalGoals) : `$${totalGoals.toFixed(2)}`}</strong> is{' '}
                        <strong>{formatCurrency ? formatCurrency(overage) : `$${overage.toFixed(2)}`} over</strong> your avg monthly income of{' '}
                        <strong>{formatCurrency ? formatCurrency(avgMonthlyIncome) : `$${avgMonthlyIncome.toFixed(2)}`}</strong>.
                        Adjust your goals below.
                      </div>
                    </div>
                  </div>
                );
              })()}

              <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <h4 style={{ margin: 0 }}>Category Budget Goals</h4>
                  {(() => {
                    const seen = new Set(groupedData.map(g => g.category));
                    const extras = [];
                    Object.keys(goals || {}).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0 }); } });
                    Object.keys(budgetSuggestions?.suggested_budgets || {}).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0 }); } });
                    const all = [...groupedData, ...extras];
                    const withGoals = all.filter(g => goals[g.category]);
                    const over = withGoals.filter(g => g.amount > goals[g.category]).length;
                    const onTrack = withGoals.filter(g => g.amount <= goals[g.category]).length;
                    const noGoal = all.filter(g => !goals[g.category]).length;
                    return (
                      <div style={{ display: 'flex', gap: 8 }}>
                        {[
                          { label: 'On Track', count: onTrack, color: '#22c55e', bg: '#f0fdf4' },
                          { label: 'Over', count: over, color: '#ef4444', bg: '#fef2f2' },
                          { label: 'No Goal', count: noGoal, color: '#94a3b8', bg: '#f8fafc' },
                        ].map(b => (
                          <div key={b.label} style={{ background: b.bg, border: `1px solid ${b.color}33`, borderRadius: 6, padding: '4px 10px', textAlign: 'center' }}>
                            <span style={{ fontSize: 15, fontWeight: 800, color: b.color }}>{b.count}</span>
                            <span style={{ fontSize: 10, color: b.color, fontWeight: 600, marginLeft: 4 }}>{b.label}</span>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                      <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#475569' }}>Category</th>
                      <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#475569' }}>Priority</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>AI Suggested</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>Your Goal</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>Actual</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>% of Total</th>
                      <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#475569', minWidth: 160 }}>Progress vs Goal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      // Build a full category list: current-month spending + any saved goal + any AI suggestion
                      // so categories with $0 spending this month still appear if they have a goal or history.
                      const seen = new Set(groupedData.map(g => g.category));
                      const extras = [];
                      // Add categories from saved goals
                      Object.keys(goals || {}).forEach(cat => {
                        if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0, subcategories: [] }); }
                      });
                      // Add categories from AI suggestions
                      Object.keys(budgetSuggestions?.suggested_budgets || {}).forEach(cat => {
                        if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0, subcategories: [] }); }
                      });
                      const allCategories = [
                        ...groupedData,
                        ...extras.sort((a, b) => a.category.localeCompare(b.category)),
                      ];
                      const totalGoals = allCategories.reduce((s, g) => s + (goals[g.category] || 0), 0);
                      const isOverIncome = avgMonthlyIncome > 0 && totalGoals > avgMonthlyIncome;
                      return allCategories.map((group, idx) => {
                      const aiEntry = budgetSuggestions?.suggested_budgets?.[group.category];
                      const comparison = budgetComparison?.categories?.[group.category];
                      const goal = goals[group.category];
                      const actual = group.amount;
                      const over = goal && actual > goal;
                      const nearLimit = goal && !over && (actual / goal) >= 0.85;
                      const barColor = !goal ? '#cbd5e1' : over ? '#ef4444' : nearLimit ? '#f59e0b' : '#22c55e';
                      const pct = goal ? Math.min((actual / goal) * 100, 100) : null;
                      const ofTotalPct = totalExpenses > 0 ? (actual / totalExpenses * 100) : 0;
                      const isEditing = editingGoal === group.category;

                      return (
                        <tr key={group.category} style={{ borderBottom: '1px solid #f0f0f0' }}>
                          {/* Category */}
                          <td style={{ padding: '11px 12px', fontWeight: 600 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                              <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, backgroundColor: COLORS[idx % COLORS.length], flexShrink: 0 }} />
                              {group.category}
                              {group.subcategories?.length > 0 && <span style={{ fontSize: 10, color: '#94a3b8' }}>({group.subcategories.length})</span>}
                            </div>
                          </td>
                          {/* Priority from AI */}
                          <td style={{ padding: '11px 12px' }}>
                            {aiEntry ? (
                              <span style={{
                                padding: '3px 8px', borderRadius: 12, fontSize: 11,
                                backgroundColor: aiEntry.priority === 'Essential' ? '#ffebee' : aiEntry.priority === 'Important' ? '#e3f2fd' : '#f1f8e9',
                                color: aiEntry.priority === 'Essential' ? '#c62828' : aiEntry.priority === 'Important' ? '#1565c0' : '#558b2f',
                              }}>{aiEntry.priority}</span>
                            ) : <span style={{ color: '#cbd5e1' }}>—</span>}
                          </td>
                          {/* AI Suggested */}
                          <td style={{ padding: '11px 12px', textAlign: 'right', color: '#475569' }}>
                            {aiEntry ? (formatCurrency ? formatCurrency(aiEntry.suggested_amount) : `$${aiEntry.suggested_amount.toFixed(2)}`) : <span style={{ color: '#cbd5e1' }}>—</span>}
                            {aiEntry?.change_from_average !== 0 && aiEntry && (
                              <div style={{ fontSize: 10, color: aiEntry.change_from_average < 0 ? '#22c55e' : '#ef4444', marginTop: 2 }}>
                                {aiEntry.change_from_average > 0 ? '+' : ''}{aiEntry.change_from_average.toFixed(1)}% from avg
                              </div>
                            )}
                          </td>
                          {/* Your Goal — inline editable */}
                          <td style={{
                            padding: '11px 12px', textAlign: 'right',
                            borderRadius: 4,
                            transition: 'box-shadow 0.25s',
                            boxShadow: isOverIncome ? '0 0 0 2px #ef4444' : 'none',
                            backgroundColor: isOverIncome ? '#fff5f5' : 'transparent',
                          }}>
                            {isEditing ? (
                              <input
                                type="number"
                                defaultValue={goal || ''}
                                autoFocus
                                style={{
                                  width: 82, padding: '3px 7px', borderRadius: 4, fontSize: 13, textAlign: 'right',
                                  border: isOverIncome ? '2px solid #ef4444' : '1px solid #4f46e5',
                                  boxShadow: isOverIncome ? '0 0 6px #ef444488' : 'none',
                                  outline: 'none',
                                }}
                                onBlur={e => saveGoal(group.category, e.target.value)}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') saveGoal(group.category, e.target.value);
                                  if (e.key === 'Escape') setEditingGoal(null);
                                }}
                              />
                            ) : (
                              <span
                                onClick={() => setEditingGoal(group.category)}
                                style={{
                                  cursor: 'pointer',
                                  color: isOverIncome ? '#dc2626' : goal ? '#0f172a' : '#94a3b8',
                                  fontWeight: goal ? 600 : 400,
                                  fontSize: 13,
                                  borderBottom: isOverIncome ? '1px dashed #ef4444' : '1px dashed #cbd5e1',
                                  paddingBottom: 1,
                                  textShadow: isOverIncome ? '0 0 8px #ef444466' : 'none',
                                }}
                                title={isOverIncome ? 'Total goals exceed your income — adjust to stay under 100%' : 'Click to adjust your goal'}
                              >
                                {goal ? (formatCurrency ? formatCurrency(goal) : `$${goal.toFixed(2)}`) : 'Set goal'}
                              </span>
                            )}
                          </td>
                          {/* Actual */}
                          <td style={{ padding: '11px 12px', textAlign: 'right', fontWeight: 600, color: over ? '#ef4444' : '#0f172a' }}>
                            {formatCurrency ? formatCurrency(actual) : `$${actual.toFixed(2)}`}
                            {over && <div style={{ fontSize: 10, color: '#ef4444' }}>+{formatCurrency ? formatCurrency(actual - goal) : `$${(actual-goal).toFixed(2)}`} over</div>}
                          </td>
                          {/* % of Total */}
                          <td style={{ padding: '11px 12px', textAlign: 'right', color: '#64748b', fontSize: 13 }}>
                            {ofTotalPct.toFixed(1)}%
                          </td>
                          {/* Progress bar vs your goal */}
                          <td style={{ padding: '11px 12px' }}>
                            {goal ? (
                              <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                  <span style={{ fontSize: 10, color: barColor, fontWeight: 700 }}>
                                    {over ? `${((actual/goal)*100).toFixed(0)}%` : `${pct.toFixed(0)}%`}
                                  </span>
                                  {!over && <span style={{ fontSize: 10, color: '#94a3b8' }}>{formatCurrency ? formatCurrency(goal - actual) : `$${(goal-actual).toFixed(2)}`} left</span>}
                                </div>
                                <div style={{ height: 7, backgroundColor: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
                                  <div style={{ height: '100%', width: `${over ? 100 : pct}%`, backgroundColor: barColor, borderRadius: 99, transition: 'width .3s' }} />
                                </div>
                              </div>
                            ) : <span style={{ color: '#cbd5e1', fontSize: 12 }}>—</span>}
                          </td>
                        </tr>
                      );
                    });
                  })()}
                    {/* Totals */}
                    <tr style={{ backgroundColor: '#f1f5f9', fontWeight: 700, borderTop: '2px solid #e2e8f0' }}>
                      <td style={{ padding: '11px 12px' }}>TOTAL</td>
                      <td />
                      <td style={{ padding: '11px 12px', textAlign: 'right', color: '#475569' }}>
                        {budgetSuggestions ? (formatCurrency ? formatCurrency(budgetSuggestions.total_budget) : `$${budgetSuggestions.total_budget?.toFixed(2)}`) : '—'}
                      </td>
                      <td style={{ padding: '11px 12px', textAlign: 'right', color: '#4f46e5' }}>
                        {formatCurrency ? formatCurrency(Object.values(goals || {}).reduce((s, v) => s + (v || 0), 0)) : '—'}
                      </td>
                      <td style={{ padding: '11px 12px', textAlign: 'right' }}>
                        {formatCurrency ? formatCurrency(totalExpenses) : `$${totalExpenses.toFixed(2)}`}
                      </td>
                      <td style={{ padding: '11px 12px', textAlign: 'right' }}>100%</td>
                      <td />
                    </tr>
                  </tbody>
                </table>
                <p style={{ fontSize: 12, color: '#94a3b8', margin: '10px 0 0' }}>💡 Goals are pre-filled by the AI. Click any value to adjust — saved in your browser. Goals glow red if their total exceeds your monthly income.</p>
              </div>
            </>
          )}

          {planSection === 'budget' && !budgetSuggestions && !loading && (
            <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
              <p>Loading budget suggestions...</p>
            </div>
          )}

          {/* ── ONE-TIME EXPENSES SECTION ── */}
          {planSection === 'one-time' && (
            <div>
              <div style={{ marginBottom: 16, padding: '12px 16px', background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8 }}>
                <strong style={{ color: '#92400e' }}>⚡ One-Time Expenses</strong>
                <p style={{ margin: '4px 0 0', fontSize: 13, color: '#78350f' }}>
                  These expenses are excluded from your monthly budget projections because they are unusually large compared to your typical spending in that category.
                  Change a label to <em>Recurring</em> if it was misclassified — it will be included in next month's budget average.
                </p>
              </div>
              {oneTimeExpenses.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
                  <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
                  <p>No one-time expenses detected. Re-run <code>aggregate_monthly.py</code> to classify your transactions.</p>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 140, background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '12px 16px' }}>
                      <div style={{ fontSize: 12, color: '#ea580c', fontWeight: 700 }}>TOTAL ONE-TIME</div>
                      <div style={{ fontSize: 22, fontWeight: 800, color: '#c2410c' }}>
                        ${oneTimeExpenses.reduce((s, r) => s + r.amount, 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div style={{ flex: 1, minWidth: 140, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 16px' }}>
                      <div style={{ fontSize: 12, color: '#475569', fontWeight: 700 }}>TRANSACTIONS</div>
                      <div style={{ fontSize: 22, fontWeight: 800, color: '#334155' }}>{oneTimeExpenses.length}</div>
                    </div>
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc' }}>
                          <th style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'left' }}>Date</th>
                          <th style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'left' }}>Merchant</th>
                          <th style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'left' }}>Category</th>
                          <th style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'right' }}>Amount</th>
                          <th style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'left' }}>Month</th>
                          <th style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'center' }}>Classification</th>
                        </tr>
                      </thead>
                      <tbody>
                        {oneTimeExpenses.sort((a, b) => b.amount - a.amount).map((row, idx) => (
                          <tr key={idx} style={{ background: idx % 2 ? '#f8fafc' : '#fff' }}>
                            <td style={{ border: '1px solid #e2e8f0', padding: '8px 12px' }}>{row.date}</td>
                            <td style={{ border: '1px solid #e2e8f0', padding: '8px 12px' }}>{row.place}</td>
                            <td style={{ border: '1px solid #e2e8f0', padding: '8px 12px', color: '#6366f1' }}>{row.category}</td>
                            <td style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#dc2626' }}>
                              ${row.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </td>
                            <td style={{ border: '1px solid #e2e8f0', padding: '8px 12px', color: '#64748b' }}>{row.month}</td>
                            <td style={{ border: '1px solid #e2e8f0', padding: '8px 12px', textAlign: 'center' }}>
                              <select
                                value={row.label || 'one-time'}
                                onChange={async (e) => {
                                  const newLabel = e.target.value;
                                  await fetch('http://localhost:8000/api/expense/label', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ date: row.date, place: row.place, amount: row.amount, month: row.month, label: newLabel }),
                                  });
                                  setOneTimeExpenses(prev => prev.map(r =>
                                    r.date === row.date && r.place === row.place && r.amount === row.amount
                                      ? { ...r, label: newLabel }
                                      : r
                                  ).filter(r => r.label === 'one-time'));
                                }}
                                style={{
                                  border: '1px solid #e2e8f0', borderRadius: 6, padding: '4px 8px', fontSize: 12,
                                  background: row.label === 'one-time' ? '#fff7ed' : '#f0fdf4',
                                  color: row.label === 'one-time' ? '#c2410c' : '#15803d',
                                  fontWeight: 600, cursor: 'pointer',
                                }}
                              >
                                <option value="one-time">⚡ One-Time</option>
                                <option value="recurring">🔁 Recurring</option>
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'trends' && trends && (
        <div className="tab-content">
          <h3>6-Month Spending Trends</h3>
          <div className="trends-grid">
            {(() => {
              const sorted = Object.entries(trends).sort((a, b) => Math.abs(b[1].percent_change || 0) - Math.abs(a[1].percent_change || 0));
              const reordered = [];
              const seen = new Set();
              // Place parents first, immediately followed by their subcategories
              for (const [cat, data] of sorted) {
                if (seen.has(cat) || parentMap[cat]) continue;
                reordered.push([cat, data]);
                seen.add(cat);
                if (subcategories[cat]) {
                  for (const sub of subcategories[cat]) {
                    if (trends[sub] && !seen.has(sub)) { reordered.push([sub, trends[sub]]); seen.add(sub); }
                  }
                }
              }
              // Append any remaining (orphan subcategories not yet seen)
              for (const [cat, data] of sorted) { if (!seen.has(cat)) reordered.push([cat, data]); }
              return reordered.map(([category, data]) => {
                const parentCat = parentMap[category];
                return (
                  <div key={category} className={`trend-card${parentCat ? ' trend-card-sub' : ''}`}>
                    <div className="trend-header">
                      <div>
                        <h4>{category}</h4>
                        {parentCat && <div className="trend-parent-label">{parentCat}</div>}
                      </div>
                      <span className={`trend-badge ${data.trend}`}>
                        {data.trend === 'increasing' ? '📈' : data.trend === 'decreasing' ? '📉' : '➡️'}
                      </span>
                    </div>
                    <div className="trend-stats">
                      <div className="stat">
                        <span className="label">vs Prior Avg:</span>
                        <span className={`value ${data.percent_change > 0 ? 'positive' : 'negative'}`}>
                          {data.percent_change > 0 ? '+' : ''}{data.percent_change.toFixed(1)}%
                        </span>
                      </div>
                      <div className="stat">
                        <span className="label">This Month:</span>
                        <span className="value">${data.current_month.toFixed(2)}</span>
                      </div>
                      <div className="stat">
                        <span className="label">6-Mo Avg:</span>
                        <span className="value">${data.average.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </div>
      )}

      {activeTab === 'chat' && (
        <div className="tab-content chat-container">
          {/* Welcome screen (no messages yet) */}
          {chatMessages.length === 0 && (
            <div className="chat-welcome">
              <div className="chat-welcome-header">
                <div className="chat-avatar">🤖</div>
                <h3>Your AI Financial Advisor</h3>
                <p>
                  Powered by a two-model AI pipeline — I parse your intent, query your real spending data,
                  then give you tailored financial advice. Ask anything about your budget and finances.
                </p>
              </div>

              <div className="chat-capabilities">
                {[
                  { icon: '📊', title: 'Spending Analysis', desc: 'Break down expenses by category, merchant, or time period across all months' },
                  { icon: '💰', title: 'Budget Planning', desc: 'Get AI-suggested budgets based on your 6-month spending history' },
                  { icon: '🎯', title: 'Savings Goals', desc: 'Calculate timelines and monthly targets to reach any financial goal' },
                  { icon: '📈', title: 'Trend Insights', desc: 'Spot rising or falling categories and understand what\'s driving changes' },
                ].map((cap, i) => (
                  <div key={i} className="capability-card">
                    <div className="capability-icon">{cap.icon}</div>
                    <div className="capability-title">{cap.title}</div>
                    <div className="capability-desc">{cap.desc}</div>
                  </div>
                ))}
              </div>

              <div className="chat-prompts-section">
                <h4>Try asking</h4>
                <div className="prompt-chips">
                  {[
                    'What did I spend most on last month?',
                    'Suggest a budget for next month',
                    'How long to save $10,000 for a car?',
                    'Am I spending too much on dining?',
                    'Show my top 5 largest purchases',
                    "What's my average monthly income?",
                    'Which categories increased this year?',
                    'How can I save $500/month?',
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      className="prompt-chip"
                      onClick={() => {
                        setChatInput(prompt);
                        // Focus the input after setting value
                        setTimeout(() => document.querySelector('.chat-input-bar input')?.focus(), 50);
                      }}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Message list */}
          {chatMessages.length > 0 && (
            <div className="chat-messages-list" ref={(el) => { if (el) el.scrollTop = el.scrollHeight; }}>
              {chatMessages.map((msg, idx) => (
                <div key={idx} className={`chat-message-row ${msg.role}`}>
                  <div className={`chat-msg-avatar ${msg.role === 'user' ? 'user' : 'bot'}`}>
                    {msg.role === 'user' ? 'You' : '🤖'}
                  </div>
                  <div className="chat-msg-content">
                    <div className={`chat-msg-bubble ${msg.role === 'user' ? 'user' : 'bot'}`}>
                      {msg.content}

                      {/* Expense list */}
                      {msg.expenses && msg.expenses.length > 0 && (
                        <div className="chat-expense-list">
                          <div style={{ padding: '8px 12px', fontSize: 12, fontWeight: 700, color: '#475569', borderBottom: '1px solid #e2e8f0' }}>
                            {msg.expenses.length} expense{msg.expenses.length > 1 ? 's' : ''} found
                          </div>
                          {msg.expenses.map((expense, expIdx) => (
                            <div key={expIdx} className="chat-expense-item">
                              <div>
                                <div className="merchant">{expense.merchant}</div>
                                <div className="meta">{expense.date} · {expense.category}</div>
                              </div>
                              <div className="amount">${expense.amount.toFixed(2)}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Actions taken */}
                      {msg.actions_taken && msg.actions_taken.length > 0 && (
                        <div style={{ marginTop: 8, fontSize: 12, color: '#10b981', fontWeight: 600 }}>
                          ✓ {msg.actions_taken.length} action{msg.actions_taken.length > 1 ? 's' : ''} completed
                        </div>
                      )}
                    </div>
                    <div className="chat-msg-time">
                      {msg.role === 'user' ? 'You' : 'Assistant'}
                    </div>
                  </div>
                </div>
              ))}

              {chatLoading && (
                <div className="chat-message-row bot">
                  <div className="chat-msg-avatar bot">🤖</div>
                  <div className="chat-msg-content">
                    <div className="chat-msg-bubble bot">
                      <div className="typing-indicator">
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Input bar */}
          <div className="chat-input-bar">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !chatLoading && sendChatMessage()}
              placeholder="Ask me about your budget, spending, or savings goals…"
              disabled={chatLoading}
            />
            <button
              className="chat-send-btn"
              onClick={sendChatMessage}
              disabled={chatLoading || !chatInput.trim()}
            >
              {chatLoading ? '…' : 'Send →'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default InsightsPanel;
