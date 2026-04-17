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
  const [budgetHistory, setBudgetHistory] = useState([]);
  const [budgetDebrief, setBudgetDebrief] = useState(null);
  const [debriefLoading, setDebriefLoading] = useState(false);
  const [savingsTargetInput, setSavingsTargetInput] = useState('');
  const [bucketOverrides, setBucketOverrides] = useState({});
  const [strategy, setStrategy] = useState('50/30/20');
  const [oneTimeExpenses, setOneTimeExpenses] = useState([]);
  const [goalMonths, setGoalMonths] = useState([]);        // months that have saved goals
  const [hasMonthGoals, setHasMonthGoals] = useState(false); // whether currentMonth has saved goals
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatAvailable, setChatAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [availableMonths, setAvailableMonths] = useState([]);
  const [savingsGoal, setSavingsGoal] = useState('');
  const [activeTab, setActiveTab] = useState(forcedTab || 'insights');
  const [planSection, setPlanSection] = useState(
    () => localStorage.getItem('budgetPlanSection') || 'budget'
  );

  // Keep internal tab in sync when parent controls it
  useEffect(() => {
    if (forcedTab) setActiveTab(forcedTab);
  }, [forcedTab]);

  // Persist planSection to localStorage
  const handleSetPlanSection = (section) => {
    setPlanSection(section);
    localStorage.setItem('budgetPlanSection', section);
  };

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
      // Load saved goals from DB for this specific month (falls back to global template)
      const goalsRes = await fetch(`http://localhost:8000/api/budget/goals?month=${month}`);
      if (goalsRes.ok) {
        const goalsData = await goalsRes.json();
        setHasMonthGoals(!!goalsData.has_month_goals);
        setGoalMonths(goalsData.saved_months || []);
        if (goalsData.has_month_goals || goalsData.has_goals) {
          // Use month-specific goals if present; otherwise use global template
          const merged = { ...goals, ...goalsData.goals };
          if (setGoals) setGoals(merged);
          localStorage.setItem('budgetGoals', JSON.stringify(merged));
        }
        // Restore savings target from settings
        if (goalsData.settings?.savings_target_amount) {
          setSavingsTargetInput(String(goalsData.settings.savings_target_amount));
        } else if (goalsData.settings?.savings_target_pct && goalsData.settings?.avg_monthly_income_used) {
          const amt = goalsData.settings.avg_monthly_income_used * goalsData.settings.savings_target_pct / 100;
          setSavingsTargetInput(String(Math.round(amt)));
        }
        // Restore bucket overrides
        const overrides = {};
        for (const [cat, detail] of Object.entries(goalsData.goal_details || {})) {
          if (detail.bucket) overrides[cat] = detail.bucket;
        }
        setBucketOverrides(overrides);
        // Restore strategy
        if (goalsData.settings?.strategy) {
          setStrategy(goalsData.settings.strategy);
        }
      }

      // Load AI budget suggestions (fresh baseline — used for AI Cap column)
      const suggRes = await fetch('http://localhost:8000/api/budget-suggestions?analysis_months=3');
      if (suggRes.ok) {
        const suggData = await suggRes.json();
        if (!suggData.error) setBudgetSuggestions(suggData);
      }

      // Load budget comparison for current month
      const compRes = await fetch(`http://localhost:8000/api/budget/${month}`);
      if (compRes.ok) {
        const compData = await compRes.json();
        setBudgetComparison(compData);
      } else {
        setBudgetComparison(null);
      }

      // Load budget history for trend chart (last 6 months)
      const histRes = await fetch('http://localhost:8000/api/budget/history?months=6');
      if (histRes.ok) {
        const histData = await histRes.json();
        setBudgetHistory(Array.isArray(histData) ? histData : []);
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

  const loadDebrief = async (month) => {
    if (debriefLoading) return;
    setDebriefLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/budget/debrief/${month}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setBudgetDebrief(data.coaching_note);
      }
    } catch (e) {
      console.error('Failed to load debrief:', e);
    } finally {
      setDebriefLoading(false);
    }
  };

  const saveBudgets = async () => {
    if (!goals || Object.keys(goals).length === 0) return;

    try {
      // Save the user's current goal values (flat {category: amount} map) to the DB
      const flat = {};
      for (const [cat, val] of Object.entries(goals)) {
        if (val !== undefined && val !== null && !isNaN(val)) flat[cat] = val;
      }
      const savingsAmt = parseFloat(savingsTargetInput) || null;
      const response = await fetch('http://localhost:8000/api/budget/goals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          month: currentMonth,
          budgets: flat,
          settings: { ...(savingsAmt ? { savings_target_amount: savingsAmt } : {}), strategy }
        })
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

  // Copy goals from a previous month into state (user can then review and save)
  const copyFromMonth = async (sourceMonth) => {
    try {
      const res = await fetch(`http://localhost:8000/api/budget/goals?month=${sourceMonth}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.goals && Object.keys(data.goals).length > 0) {
        if (setGoals) setGoals(data.goals);
        localStorage.setItem('budgetGoals', JSON.stringify(data.goals));
      }
    } catch (e) {
      console.error('Failed to copy from month:', e);
    }
  };

  // Reload suggestions when savings target or strategy changes
  const reloadSuggestionsWithTarget = async (targetAmt, strat) => {
    try {
      const params = new URLSearchParams({ analysis_months: '3' });
      if (targetAmt) params.set('savings_target', targetAmt);
      params.set('strategy', strat || strategy || '50/30/20');
      const res = await fetch(`http://localhost:8000/api/budget-suggestions?${params}`);
      if (res.ok) {
        const data = await res.json();
        if (!data.error) setBudgetSuggestions(data);
      }
    } catch (e) { /* ignore */ }
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
              onClick={() => handleSetPlanSection('budget')}
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
              onClick={() => handleSetPlanSection('forecast')}
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
              onClick={() => handleSetPlanSection('one-time')}
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
              {/* ── Month context bar ── */}
              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 16px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 13 }}>
                <span style={{ fontWeight: 700, color: '#334155' }}>📅 Budget for: {currentMonth}</span>
                {hasMonthGoals
                  ? <span style={{ color: '#16a34a', fontWeight: 600 }}>✓ Goals saved for this month</span>
                  : <span style={{ color: '#f59e0b', fontWeight: 600 }}>No goals saved for this month yet</span>
                }
                {goalMonths.length > 0 && (
                  <span style={{ color: '#94a3b8' }}>
                    · History: {goalMonths.slice(0, 5).join(', ')}{goalMonths.length > 5 ? ` +${goalMonths.length - 5} more` : ''}
                  </span>
                )}
              </div>

              {/* ── No goals callout — offer to copy or use AI suggestions ── */}
              {!hasMonthGoals && goalMonths.length > 0 && (
                <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '12px 16px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
                  <span style={{ color: '#92400e' }}>No goals saved for <strong>{currentMonth}</strong> yet.</span>
                  <button
                    onClick={() => copyFromMonth(goalMonths[0])}
                    style={{ padding: '5px 12px', background: '#f59e0b', color: 'white', border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer', fontSize: 12 }}
                  >📋 Copy from {goalMonths[0]}</button>
                  <span style={{ color: '#b45309' }}>or adjust the AI suggestions below and click Save.</span>
                </div>
              )}

              {/* ── Strategy Picker ── */}
              <div style={{ background: '#fff', borderRadius: 8, padding: '14px 20px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: '#334155' }}>📊 Strategy:</span>
                {[['50/30/20', '50/30/20 Standard'], ['60/20/20', '60/20/20 High-Housing'], ['70/20/10', '70/20/10 Tight Budget']].map(([val, label]) => (
                  <label key={val} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, fontWeight: strategy === val ? 700 : 400, color: strategy === val ? '#4f46e5' : '#475569' }}>
                    <input
                      type="radio" name="strategy" value={val} checked={strategy === val}
                      onChange={() => { setStrategy(val); reloadSuggestionsWithTarget(parseFloat(savingsTargetInput) || null, val); }}
                      style={{ accentColor: '#4f46e5' }}
                    />
                    {label}
                  </label>
                ))}
              </div>

              {/* ── Pay Yourself First ── */}
              <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '12px 16px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: '#15803d' }}>💰 Pay Yourself First:</span>
                <input
                  type="number" placeholder="e.g. 800" value={savingsTargetInput}
                  onChange={e => setSavingsTargetInput(e.target.value)}
                  style={{ width: 110, padding: '6px 10px', borderRadius: 6, border: '1px solid #86efac', fontSize: 13 }}
                />
                <button
                  onClick={() => reloadSuggestionsWithTarget(parseFloat(savingsTargetInput) || null, strategy)}
                  style={{ padding: '6px 14px', background: '#16a34a', color: 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                >Apply</button>
                {budgetSuggestions.spendable_income > 0 && (
                  <span style={{ fontSize: 13, color: '#166534' }}>
                    Spendable pool: <strong>${budgetSuggestions.spendable_income.toLocaleString('en-US', { minimumFractionDigits: 2 })}/mo</strong>
                    {budgetSuggestions.savings_target > 0 && ` · Savings target: $${budgetSuggestions.savings_target.toFixed(2)}/mo`}
                  </span>
                )}
              </div>

              {/* ── Personalized split banner ── */}
              {budgetSuggestions.personalized_split && (
                <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '10px 16px', marginBottom: 10, fontSize: 13, color: '#92400e' }}>
                  💡 {budgetSuggestions.personalized_split}
                </div>
              )}

              {/* ── Fixed-cost coaching banner ── */}
              {budgetSuggestions.fixed_cost_coaching && (
                <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '10px 16px', marginBottom: 10, fontSize: 13, color: '#991b1b' }}>
                  ⚠️ {budgetSuggestions.fixed_cost_coaching}
                </div>
              )}

              {/* ── 50/30/20 Health Bars ── */}
              <div style={{ background: '#fff', borderRadius: 8, padding: '16px 20px', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <h4 style={{ margin: 0, fontSize: 14 }}>Budget Health</h4>
                  <span style={{ fontSize: 12, color: '#94a3b8' }}>{strategy} rule · Based on {budgetSuggestions.analysis_period} months</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {[
                    { label: 'Needs',   pctKey: 'need_pct',    target: strategy === '60/20/20' ? 60 : strategy === '70/20/10' ? 70 : 50, color: '#3b82f6' },
                    { label: 'Wants',   pctKey: 'want_pct',    target: strategy === '70/20/10' ? 20 : strategy === '60/20/20' ? 20 : 30, color: '#f59e0b' },
                    { label: 'Savings', pctKey: 'savings_pct', target: strategy === '70/20/10' ? 10 : 20, color: '#22c55e' },
                  ].map(({ label, pctKey, target, color }) => {
                    const pct = budgetSuggestions[pctKey] || 0;
                    const isNeedsOrWants = label !== 'Savings';
                    const isOver = isNeedsOrWants ? pct > target : pct < target;
                    const barColor = isOver ? (isNeedsOrWants ? '#ef4444' : '#f59e0b') : color;
                    return (
                      <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ width: 60, fontSize: 12, fontWeight: 700, color }}>{label}</div>
                        <div style={{ flex: 1, height: 12, background: '#f1f5f9', borderRadius: 99, overflow: 'visible', position: 'relative' }}>
                          <div style={{ position: 'absolute', left: `${Math.min(target, 100)}%`, top: -2, bottom: -2, width: 2, background: color, opacity: 0.5, zIndex: 1, borderRadius: 1 }} />
                          <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`, background: barColor, borderRadius: 99, transition: 'width .4s', opacity: 0.85 }} />
                        </div>
                        <div style={{ width: 90, fontSize: 12, textAlign: 'right', color: isOver ? '#ef4444' : '#475569' }}>
                          <strong style={{ color: isOver ? '#ef4444' : color }}>{pct.toFixed(1)}%</strong>
                          <span style={{ color: '#94a3b8' }}> / {target}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* ── Over-income warning ── */}
              {(() => {
                const totalGoals = Object.values(goals || {}).reduce((s, v) => s + (v || 0), 0);
                const isOver = avgMonthlyIncome > 0 && totalGoals > avgMonthlyIncome;
                if (!isOver) return null;
                const overage = totalGoals - avgMonthlyIncome;
                return (
                  <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 20 }}>🚨</span>
                    <div>
                      <div style={{ fontWeight: 700, color: '#dc2626', fontSize: 14 }}>Goals exceed 100% of income</div>
                      <div style={{ color: '#b91c1c', fontSize: 12, marginTop: 2 }}>
                        Total goals <strong>${totalGoals.toFixed(2)}</strong> is <strong>${overage.toFixed(2)} over</strong> avg income <strong>${avgMonthlyIncome.toFixed(2)}</strong>.
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* ── Budget Table ── */}
              <div style={{ background: '#fff', borderRadius: 8, padding: '20px', marginBottom: 16 }}>
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
                        {[{ label: 'On Track', count: onTrack, color: '#22c55e', bg: '#f0fdf4' }, { label: 'Over', count: over, color: '#ef4444', bg: '#fef2f2' }, { label: 'No Goal', count: noGoal, color: '#94a3b8', bg: '#f8fafc' }].map(b => (
                          <div key={b.label} style={{ background: b.bg, border: `1px solid ${b.color}33`, borderRadius: 6, padding: '4px 10px', textAlign: 'center' }}>
                            <span style={{ fontSize: 15, fontWeight: 800, color: b.color }}>{b.count}</span>
                            <span style={{ fontSize: 10, color: b.color, fontWeight: 600, marginLeft: 4 }}>{b.label}</span>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
                    <thead>
                      <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                        <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#475569' }}>Category</th>
                        <th style={{ padding: '10px 12px', textAlign: 'center', fontSize: 13, color: '#475569' }}>Bucket</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>3-mo Avg</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>AI Cap</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>Your Goal</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>Actual</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>%</th>
                        <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#475569', minWidth: 130 }}>Progress</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const seen = new Set(groupedData.map(g => g.category));
                        const extras = [];
                        Object.keys(goals || {}).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0, subcategories: [] }); } });
                        Object.keys(budgetSuggestions?.suggested_budgets || {}).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0, subcategories: [] }); } });
                        const allCategories = [...groupedData.filter(g => !g.one_time), ...extras.sort((a, b) => a.category.localeCompare(b.category))];
                        const totalGoals = allCategories.reduce((s, g) => s + (goals[g.category] || 0), 0);
                        const isOverIncome = avgMonthlyIncome > 0 && totalGoals > avgMonthlyIncome;
                        return allCategories.map((group, idx) => {
                          const aiEntry = budgetSuggestions?.suggested_budgets?.[group.category];
                          const goal = goals[group.category];
                          const actual = group.amount;
                          const over = goal && actual > goal;
                          const nearLimit = goal && !over && (actual / goal) >= 0.85;
                          const barColor = !goal ? '#cbd5e1' : over ? '#ef4444' : nearLimit ? '#f59e0b' : '#22c55e';
                          const pct = goal ? Math.min((actual / goal) * 100, 100) : null;
                          const ofTotalPct = totalExpenses > 0 ? (actual / totalExpenses * 100) : 0;
                          const isEditing = editingGoal === group.category;
                          const bucket = bucketOverrides[group.category] || aiEntry?.bucket || '';
                          const isFixed = aiEntry?.is_fixed_cost;
                          const trendDir = aiEntry?.trend_direction;
                          const trendIcon = trendDir === 'increasing' ? '📈' : trendDir === 'decreasing' ? '📉' : null;
                          const bucketColor = bucket === 'Need' ? '#3b82f6' : bucket === 'Want' ? '#f59e0b' : bucket === 'Saving' ? '#22c55e' : '#94a3b8';
                          return (
                            <tr key={group.category} style={{ borderBottom: '1px solid #f0f0f0' }}>
                              {/* Category */}
                              <td style={{ padding: '11px 12px', fontWeight: 600 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                  <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, backgroundColor: COLORS[idx % COLORS.length], flexShrink: 0 }} />
                                  <span>{group.category}</span>
                                  {trendIcon && <span title={`Trending ${trendDir}`} style={{ fontSize: 11 }}>{trendIcon}</span>}
                                  {group.subcategories?.length > 0 && <span style={{ fontSize: 10, color: '#94a3b8' }}>({group.subcategories.length})</span>}
                                </div>
                              </td>
                              {/* Bucket dropdown */}
                              <td style={{ padding: '11px 12px', textAlign: 'center' }}>
                                <select
                                  value={bucket}
                                  onChange={async (e) => {
                                    const newBucket = e.target.value;
                                    if (!newBucket) return;
                                    setBucketOverrides(prev => ({ ...prev, [group.category]: newBucket }));
                                    try {
                                      await fetch('http://localhost:8000/api/budget/goals', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ budgets: {}, bucket_overrides: { [group.category]: newBucket } })
                                      });
                                    } catch (_) {}
                                    reloadSuggestionsWithTarget(parseFloat(savingsTargetInput) || null, strategy);
                                  }}
                                  style={{ border: `1px solid ${bucketColor}55`, borderRadius: 12, padding: '3px 8px', fontSize: 11, background: bucket === 'Need' ? '#eff6ff' : bucket === 'Want' ? '#fffbeb' : bucket === 'Saving' ? '#f0fdf4' : '#f8fafc', color: bucketColor, fontWeight: 600, cursor: 'pointer', minWidth: 75 }}
                                >
                                  <option value="">—</option>
                                  <option value="Need">🏠 Need</option>
                                  <option value="Want">🎯 Want</option>
                                  <option value="Saving">💰 Saving</option>
                                </select>
                              </td>
                              {/* 3-mo Avg */}
                              <td style={{ padding: '11px 12px', textAlign: 'right', color: '#64748b', fontSize: 13 }}>
                                {aiEntry ? `$${aiEntry.historical_avg.toFixed(2)}` : <span style={{ color: '#cbd5e1' }}>—</span>}
                              </td>
                              {/* AI Cap */}
                              <td style={{ padding: '11px 12px', textAlign: 'right' }}>
                                {aiEntry?.ai_cap != null ? (
                                  <span style={{ fontSize: 13, color: '#6366f1', fontWeight: 600 }}>${aiEntry.ai_cap.toFixed(2)}</span>
                                ) : <span style={{ color: '#cbd5e1' }}>—</span>}
                              </td>
                              {/* Your Goal */}
                              <td style={{ padding: '11px 12px', textAlign: 'right', backgroundColor: isOverIncome ? '#fff5f5' : 'transparent' }}>
                                {isFixed ? (
                                  <span style={{ fontSize: 13, color: '#475569' }} title="Fixed cost — very low variance in your history">
                                    🔒 {goal ? `$${goal.toFixed(2)}` : aiEntry ? `$${aiEntry.suggested_amount.toFixed(2)}` : '—'}
                                  </span>
                                ) : isEditing ? (
                                  <input
                                    type="number" defaultValue={goal || ''} autoFocus
                                    style={{ width: 82, padding: '3px 7px', borderRadius: 4, fontSize: 13, textAlign: 'right', border: isOverIncome ? '2px solid #ef4444' : '1px solid #4f46e5', outline: 'none' }}
                                    onBlur={e => saveGoal(group.category, e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') saveGoal(group.category, e.target.value); if (e.key === 'Escape') setEditingGoal(null); }}
                                  />
                                ) : (
                                  <span
                                    onClick={() => setEditingGoal(group.category)}
                                    style={{ cursor: 'pointer', color: isOverIncome ? '#dc2626' : goal ? '#0f172a' : '#94a3b8', fontWeight: goal ? 600 : 400, fontSize: 13, borderBottom: '1px dashed #cbd5e1', paddingBottom: 1 }}
                                    title="Click to edit goal"
                                  >
                                    {goal ? `$${goal.toFixed(2)}` : 'Set goal'}
                                  </span>
                                )}
                              </td>
                              {/* Actual */}
                              <td style={{ padding: '11px 12px', textAlign: 'right', fontWeight: 600, color: over ? '#ef4444' : '#0f172a' }}>
                                {formatCurrency ? formatCurrency(actual) : `$${actual.toFixed(2)}`}
                                {over && <div style={{ fontSize: 10, color: '#ef4444' }}>+${(actual - goal).toFixed(2)}</div>}
                              </td>
                              {/* % of total */}
                              <td style={{ padding: '11px 12px', textAlign: 'right', color: '#64748b', fontSize: 13 }}>{ofTotalPct.toFixed(1)}%</td>
                              {/* Progress bar */}
                              <td style={{ padding: '11px 12px' }}>
                                {goal ? (
                                  <div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                      <span style={{ fontSize: 10, color: barColor, fontWeight: 700 }}>
                                        {over ? `${((actual / goal) * 100).toFixed(0)}%` : `${pct.toFixed(0)}%`}
                                      </span>
                                      {!over && <span style={{ fontSize: 10, color: '#94a3b8' }}>${(goal - actual).toFixed(2)} left</span>}
                                    </div>
                                    <div style={{ height: 7, background: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
                                      <div style={{ height: '100%', width: `${over ? 100 : pct}%`, background: barColor, borderRadius: 99, transition: 'width .3s' }} />
                                    </div>
                                  </div>
                                ) : <span style={{ color: '#cbd5e1', fontSize: 12 }}>—</span>}
                              </td>
                            </tr>
                          );
                        });
                      })()}
                      <tr style={{ background: '#f1f5f9', fontWeight: 700, borderTop: '2px solid #e2e8f0' }}>
                        <td style={{ padding: '11px 12px' }}>TOTAL</td>
                        <td />
                        <td style={{ padding: '11px 12px', textAlign: 'right', color: '#475569' }}>
                          ${Object.values(budgetSuggestions?.suggested_budgets || {}).reduce((s, b) => s + (b.historical_avg || 0), 0).toFixed(2)}
                        </td>
                        <td />
                        <td style={{ padding: '11px 12px', textAlign: 'right', color: '#4f46e5' }}>
                          ${Object.values(goals || {}).reduce((s, v) => s + (v || 0), 0).toFixed(2)}
                        </td>
                        <td style={{ padding: '11px 12px', textAlign: 'right' }}>${totalExpenses.toFixed(2)}</td>
                        <td style={{ padding: '11px 12px', textAlign: 'right' }}>100%</td>
                        <td />
                      </tr>
                    </tbody>
                  </table>
                </div>
                {/* Action buttons */}
                <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
                  <button
                    onClick={saveBudgets}
                    style={{ padding: '9px 18px', background: '#4f46e5', color: 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >💾 Save Goals</button>
                  <button
                    onClick={() => {
                      if (!budgetSuggestions?.suggested_budgets || !setGoals) return;
                      const reset = {};
                      for (const [cat, entry] of Object.entries(budgetSuggestions.suggested_budgets)) {
                        reset[cat] = entry.suggested_amount;
                      }
                      setGoals(reset);
                      localStorage.setItem('budgetGoals', JSON.stringify(reset));
                    }}
                    style={{ padding: '9px 18px', background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >↺ Reset to AI</button>
                  <button
                    onClick={() => {
                      const seen = new Set(groupedData.map(g => g.category));
                      const extras = [];
                      Object.keys(goals || {}).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0 }); } });
                      Object.keys(budgetSuggestions?.suggested_budgets || {}).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); extras.push({ category: cat, amount: 0 }); } });
                      const allCats = [...groupedData.filter(g => !g.one_time), ...extras];
                      const header = ['Category', 'Bucket', '3-mo Avg', 'AI Cap', 'Your Goal', 'Actual'].join(',');
                      const rows = allCats.map(g => {
                        const ai = budgetSuggestions?.suggested_budgets?.[g.category];
                        return [g.category, ai?.bucket || '', ai?.historical_avg?.toFixed(2) || '', ai?.ai_cap?.toFixed(2) || '', (goals[g.category] || '').toString(), g.amount.toFixed(2)].join(',');
                      });
                      const csv = [header, ...rows].join('\n');
                      const blob = new Blob([csv], { type: 'text/csv' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a'); a.href = url; a.download = `budget-${currentMonth}.csv`; a.click();
                      URL.revokeObjectURL(url);
                    }}
                    style={{ padding: '9px 18px', background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >📥 Export CSV</button>
                </div>
                <p style={{ fontSize: 12, color: '#94a3b8', margin: '10px 0 0' }}>
                  💡 Click any goal to edit inline. Fixed-cost 🔒 rows have low month-to-month variance. 📈📉 trend icons show 3-month direction.
                </p>
              </div>

              {/* ── Phase 4 — Report Card ── */}
              {budgetComparison && (
                <div style={{ background: '#fff', borderRadius: 8, padding: '20px', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <h3 style={{ margin: 0, fontSize: 16 }}>📋 {currentMonth} — Budget Report Card</h3>
                    <span style={{ fontSize: 13, color: budgetComparison.on_track ? '#16a34a' : '#dc2626', fontWeight: 700 }}>
                      {budgetComparison.on_track ? '✓ On Track' : '⚠ Over Budget'}
                    </span>
                  </div>

                  {/* Summary stats */}
                  <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                    {[
                      { label: 'Budget',  val: budgetComparison.total_budget,   color: '#475569' },
                      { label: 'Actual',  val: budgetComparison.total_actual,   color: budgetComparison.on_track ? '#16a34a' : '#dc2626' },
                      { label: (budgetComparison.total_variance || 0) >= 0 ? 'Overage' : 'Surplus', val: Math.abs(budgetComparison.total_variance || 0), color: (budgetComparison.total_variance || 0) > 0 ? '#dc2626' : '#16a34a' },
                    ].map(({ label, val, color }) => (
                      <div key={label} style={{ flex: 1, minWidth: 100, background: '#f8fafc', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, marginBottom: 2 }}>{label.toUpperCase()}</div>
                        <div style={{ fontSize: 20, fontWeight: 800, color }}>${val?.toFixed(2)}</div>
                      </div>
                    ))}
                    {budgetComparison.one_time_total > 0 && (
                      <div style={{ flex: 1, minWidth: 100, background: '#fffbeb', borderRadius: 8, padding: '10px 14px', border: '1px solid #fde68a' }}>
                        <div style={{ fontSize: 11, color: '#92400e', fontWeight: 600, marginBottom: 2 }}>ONE-TIME</div>
                        <div style={{ fontSize: 20, fontWeight: 800, color: '#d97706' }}>${budgetComparison.one_time_total.toFixed(2)}</div>
                      </div>
                    )}
                  </div>

                  {/* AI Coaching Debrief */}
                  <div style={{ marginBottom: 16 }}>
                    {budgetDebrief ? (
                      <div style={{ background: 'linear-gradient(135deg, #f0f9ff, #e0f2fe)', border: '1px solid #bae6fd', borderRadius: 8, padding: '14px 16px', fontSize: 14, color: '#0c4a6e', lineHeight: 1.6 }}>
                        <div style={{ fontWeight: 700, marginBottom: 6, fontSize: 11, color: '#0369a1', letterSpacing: '0.05em' }}>🤖 AI COACHING</div>
                        {budgetDebrief}
                      </div>
                    ) : (
                      <button
                        onClick={() => loadDebrief(currentMonth)}
                        disabled={debriefLoading}
                        style={{ padding: '8px 16px', background: debriefLoading ? '#f1f5f9' : '#0ea5e9', color: debriefLoading ? '#94a3b8' : 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: debriefLoading ? 'default' : 'pointer' }}
                      >{debriefLoading ? '⏳ Generating…' : '🤖 Generate AI Coaching Note'}</button>
                    )}
                  </div>

                  {/* Per-category comparison table */}
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                        <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569' }}>Category</th>
                        <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Goal</th>
                        <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Actual</th>
                        <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Variance</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569', minWidth: 110 }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(budgetComparison.categories || {})
                        .sort((a, b) => Math.abs(b[1].variance) - Math.abs(a[1].variance))
                        .map(([cat, data]) => {
                          const isOver = data.status === 'over';
                          const barPct = data.budget > 0 ? Math.min((data.actual / data.budget) * 100, 100) : 0;
                          return (
                            <tr key={cat} style={{ borderBottom: '1px solid #f0f0f0' }}>
                              <td style={{ padding: '8px 12px', fontWeight: 600 }}>{cat}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>${data.budget?.toFixed(2)}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: isOver ? '#ef4444' : '#0f172a' }}>${data.actual?.toFixed(2)}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', color: isOver ? '#ef4444' : '#16a34a' }}>
                                {isOver ? '+' : ''}{data.variance?.toFixed(2)}
                              </td>
                              <td style={{ padding: '8px 12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <div style={{ height: 6, flex: 1, background: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
                                    <div style={{ height: '100%', width: `${barPct}%`, background: isOver ? '#ef4444' : '#22c55e', borderRadius: 99 }} />
                                  </div>
                                  <span style={{ fontSize: 10, fontWeight: 700, color: isOver ? '#ef4444' : '#16a34a', minWidth: 32 }}>
                                    {data.budget > 0 ? `${((data.actual / data.budget) * 100).toFixed(0)}%` : '—'}
                                  </span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>

                  {/* 3-month attainment trend */}
                  {budgetHistory.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: '#475569', marginBottom: 8 }}>📅 Monthly Attainment Trend</div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {budgetHistory.slice(0, 6).map(m => {
                          const pct = m.attainment_pct;
                          const good = pct != null && pct >= 90;
                          return (
                            <div key={m.month} style={{ flex: 1, minWidth: 80, background: good ? '#f0fdf4' : pct != null ? '#fef2f2' : '#f8fafc', border: `1px solid ${good ? '#86efac' : pct != null ? '#fca5a5' : '#e2e8f0'}`, borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                              <div style={{ fontSize: 10, color: '#64748b', marginBottom: 2 }}>{m.month}</div>
                              <div style={{ fontSize: 18, fontWeight: 800, color: good ? '#16a34a' : pct != null ? '#dc2626' : '#94a3b8' }}>{pct != null ? `${pct}%` : '—'}</div>
                              <div style={{ fontSize: 10, color: '#64748b' }}>{pct != null ? 'attainment' : 'no data'}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {planSection === 'budget' && !budgetSuggestions && !loading && (
            <div style={{
              padding: '48px 32px', textAlign: 'center', color: '#64748b',
              background: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0'
            }}>
              <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
              {availableMonths.length === 0 ? (
                <>
                  <p style={{ fontSize: 18, fontWeight: 600, color: '#334155', margin: '0 0 8px' }}>
                    No processed months yet
                  </p>
                  <p style={{ margin: 0, maxWidth: 400, marginInline: 'auto' }}>
                    A budget baseline requires at least one processed month of transactions.
                    Upload and process a bank statement to get started.
                  </p>
                </>
              ) : (
                <>
                  <p style={{ fontSize: 18, fontWeight: 600, color: '#334155', margin: '0 0 8px' }}>
                    Budget suggestions unavailable
                  </p>
                  <p style={{ margin: 0 }}>Could not load budget data. Please try again.</p>
                </>
              )}
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
