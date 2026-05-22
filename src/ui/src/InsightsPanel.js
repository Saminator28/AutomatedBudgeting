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

const getNextMonthOf = (monthStr) => {
  const [y, m] = monthStr.split('-').map(Number);
  const d = new Date(y, m, 1); // m is already 1-based; Date(y, m) = first day of next month
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

function InsightsPanel({ selectedMonth, onMonthChange, subcategories = {}, availableCategories = [], processedMonths = [], goals = {}, setGoals, groupedData = [], totalExpenses = 0, avgMonthlyIncome = 0, COLORS = [], formatCurrency, forcedTab }) {
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
  const [categoryHistory, setCategoryHistory] = useState({ months_ordered: [], by_month: {} });
  const [committedCosts, setCommittedCosts] = useState(null);
  const [rollovers, setRollovers] = useState({});          // {category: surplus_amount}
  const [viewGoalsMonth, setViewGoalsMonth] = useState(null);   // month whose goals are being viewed
  const [viewGoalsData, setViewGoalsData] = useState({});        // goals for viewGoalsMonth
  const [copySuccessMonth, setCopySuccessMonth] = useState(null); // for "Use" button feedback
  // Budget target month: the month we are setting goals FOR (defaults to month after data month)
  const [budgetTargetMonth, setBudgetTargetMonth] = useState(
    () => getNextMonthOf(selectedMonth || getPrevMonth())
  );
  const [showBudgetHistory, setShowBudgetHistory] = useState(false);
  const [healthPeriod, setHealthPeriod] = useState(3); // period for historical health bars on insights tab
  const [expandedBudgetGroups, setExpandedBudgetGroups] = useState(() => new Set(Object.keys(subcategories)));
  // Per-category locks: Set of category names whose goals the user has pinned.
  // Locks are cross-month — persisted in the DB and carried forward every new month.
  // localStorage.lockedCats (no month suffix) is used as a fast initial-render cache.
  const [lockedCats, setLockedCats] = useState(
    () => new Set(JSON.parse(localStorage.getItem('lockedCats') || '[]'))
  );
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatAvailable, setChatAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
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

  // Persist lockedCats to localStorage (single global key — locks are cross-month)
  useEffect(() => {
    localStorage.setItem('lockedCats', JSON.stringify([...lockedCats]));
  }, [lockedCats]);

  // Keep budgetTargetMonth = data month + 1 whenever the data month changes,
  // but only if the user hasn't manually overridden it to something else.
  useEffect(() => {
    setBudgetTargetMonth(getNextMonthOf(currentMonth));
  }, [currentMonth]);

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

  // Auto-populate Your Goal from AI suggestions when they first load —
  // ONLY when on the budget/plan tab (not the overview spending summary).
  // Also auto-seed AI-detected fixed-cost categories into lockedCats the first time
  // this month's locks are seen (so they start locked, but users can Unlock All freely).
  useEffect(() => {
    if (!budgetSuggestions?.suggested_budgets || !setGoals) return;
    if (activeTab !== 'plan') return; // don't auto-fill goals while viewing overview
    const updated = { ...goals };
    let changed = false;
    const fixedToSeed = [];
    for (const [cat, entry] of Object.entries(budgetSuggestions.suggested_budgets)) {
      if (updated[cat] === undefined || updated[cat] === null || isNaN(updated[cat])) {
        updated[cat] = entry.suggested_amount;
        changed = true;
      }
      if (entry.is_fixed_cost || entry.goal_mode === 'predictive') fixedToSeed.push(cat);
    }
    if (changed) {
      setGoals(updated);
      localStorage.setItem('budgetGoals', JSON.stringify(updated));
    }
    // Only seed fixed cats if the user has no locks set yet (first-time setup)
    if (fixedToSeed.length > 0 && lockedCats.size === 0) {
      setLockedCats(prev => {
        const next = new Set(prev);
        fixedToSeed.forEach(c => next.add(c));
        return next;
      });
    }
  }, [budgetSuggestions, activeTab]); // intentionally omit goals/setGoals/currentMonth to avoid loops

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

        if (goalsData.has_month_goals) {
          // Saved month: use the exact per-month amounts — replace state entirely
          if (setGoals) setGoals(goalsData.goals);
          localStorage.setItem('budgetGoals', JSON.stringify(goalsData.goals));
        } else if (goalsData.has_goals) {
          // New (unsaved) month: backend already filtered to locked-only amounts.
          // Replace state with just those — unlocked slots are left null so AI fills them.
          if (setGoals) setGoals(goalsData.goals);
          localStorage.setItem('budgetGoals', JSON.stringify(goalsData.goals));
        } else {
          // No goals at all — clear state so AI fills everything fresh
          if (setGoals) setGoals({});
          localStorage.setItem('budgetGoals', JSON.stringify({}));
        }

        // Sync locked categories from DB (source of truth for cross-month locks)
        const dbLocked = new Set(
          Object.entries(goalsData.goal_details || {})
            .filter(([, d]) => d.locked)
            .map(([cat]) => cat)
        );
        if (dbLocked.size > 0) {
          setLockedCats(dbLocked);
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

      // Load per-category spending history for sparklines
      const catHistRes = await fetch('http://localhost:8000/api/budget/category-history?months=6');
      if (catHistRes.ok) {
        const catHistData = await catHistRes.json();
        if (catHistData && catHistData.months_ordered) setCategoryHistory(catHistData);
      }

      // Load committed / recurring costs panel
      const committedRes = await fetch('http://localhost:8000/api/budget/committed?lookback_months=3');
      if (committedRes.ok) {
        const committedData = await committedRes.json();
        if (!committedData.error) setCommittedCosts(committedData);
      }

      // Load rollover surplus from previous month
      const rolloverRes = await fetch(`http://localhost:8000/api/budget/rollover/${encodeURIComponent(month)}`);
      if (rolloverRes.ok) {
        const rolloverData = await rolloverRes.json();
        if (rolloverData.rollovers) setRollovers(rolloverData.rollovers);
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
      // We save for budgetTargetMonth (the upcoming month) not the data month being analysed.
      const flat = {};
      for (const [cat, val] of Object.entries(goals)) {
        if (val !== undefined && val !== null && !isNaN(val)) flat[cat] = val;
      }
      const savingsAmt = parseFloat(savingsTargetInput) || null;
      const response = await fetch('http://localhost:8000/api/budget/goals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          month: budgetTargetMonth,
          budgets: flat,
          // Persist lock state so it carries into future months (cross-month locks)
          locks: Object.fromEntries(
            [...lockedCats].map(c => [c, true]).concat(
              // Explicitly mark unlocked cats as false so DB reflects current state
              Object.keys(flat).filter(c => !lockedCats.has(c)).map(c => [c, false])
            )
          ),
          settings: { ...(savingsAmt ? { savings_target_amount: savingsAmt } : {}), strategy }
        })
      });

      if (response.ok) {
        alert(`Budget goals saved for ${budgetTargetMonth}!`);
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
        setCopySuccessMonth(sourceMonth);
        setTimeout(() => setCopySuccessMonth(null), 3000);
      }
    } catch (e) {
      console.error('Failed to copy from month:', e);
    }
  };

  // Fetch and display goals for a previous month without applying them
  const viewGoalsForMonth = async (month) => {
    if (viewGoalsMonth === month) { setViewGoalsMonth(null); return; }
    try {
      const res = await fetch(`http://localhost:8000/api/budget/goals?month=${month}`);
      if (!res.ok) return;
      const data = await res.json();
      setViewGoalsData(data.goals || {});
      setViewGoalsMonth(month);
    } catch (e) {
      console.error('Failed to view goals for month:', e);
    }
  };

  // Reload suggestions when savings target or strategy changes
  const reloadSuggestionsWithTarget = async (targetAmt, strat) => {
    setSuggestionsLoading(true);
    try {
      const params = new URLSearchParams({ analysis_months: '3' });
      if (targetAmt) params.set('savings_target', targetAmt);
      params.set('strategy', strat || strategy || '50/30/20');
      const res = await fetch(`http://localhost:8000/api/budget-suggestions?${params}`);
      if (res.ok) {
        const data = await res.json();
        if (!data.error) {
          setBudgetSuggestions(data);
          // Auto-apply new AI-suggested amounts to all unlocked categories
          if (setGoals && data.suggested_budgets) {
            setGoals(prevGoals => {
              const updated = { ...prevGoals };
              for (const [cat, entry] of Object.entries(data.suggested_budgets)) {
                // Skip Saving-bucket categories — PYF is the savings mechanism, not goal-based;
                // the user should control their own investment/savings goal amounts.
                if (!lockedCats.has(cat) && entry.bucket !== 'Saving') {
                  updated[cat] = entry.suggested_amount;
                }
              }
              localStorage.setItem('budgetGoals', JSON.stringify(updated));
              return updated;
            });
          }
        }
      }
    } catch (e) { /* ignore */ } finally {
      setSuggestionsLoading(false);
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

          {/* Budget Report Card — spending summary + AI coaching for the latest compiled month */}
          {(budgetComparison || groupedData.length > 0 || Object.keys(goals).length > 0) && (() => {
            // Reverse map: child → parent (built from subcategories prop)
            const _parentMap = {};
            for (const [par, subs] of Object.entries(subcategories)) {
              for (const sub of subs) _parentMap[sub] = par;
            }

            // Spending rows (actual transactions rolled into parent groups by App.js)
            const _dataRows = groupedData.filter(g => !g.one_time).sort((a, b) => b.amount - a.amount);

            // Phantom rows: has a goal for this month but zero transactions.
            // Only add top-level rows (parents or standalones) — children will be sub-rows.
            const _spendingCats = new Set(_dataRows.map(g => g.category));
            const _goalOnlyRows = Object.entries(goals)
              .filter(([cat, amt]) =>
                amt > 0 &&
                !_spendingCats.has(cat) &&   // no spending data already shown
                !_parentMap[cat]              // not a child (children shown as sub-rows)
              )
              .map(([cat]) => ({ category: cat, amount: 0, subcategories: [], one_time: false }));

            // All rows: spending rows first (sorted by amount), then goal-only rows (alphabetical)
            const _allRows = [
              ..._dataRows,
              ..._goalOnlyRows.sort((a, b) => a.category.localeCompare(b.category)),
            ];

            // Local total budget: for parents prefer sub-sum (avoids double-counting parent+child goals)
            const _localTotalBudget = _allRows.reduce((s, g) => {
              const _subs = subcategories[g.category] || [];
              const _ss = _subs.reduce((ss, sub) => ss + (goals[sub] || 0), 0);
              const _d = goals[g.category] ?? null;
              return s + (_ss > 0 ? _ss : _d ?? 0);
            }, 0);
            const showGoalCols = !!(budgetComparison || _localTotalBudget > 0) && (hasMonthGoals || activeTab === 'plan');
            const _localVariance = totalExpenses - _localTotalBudget;
            const _localOnTrack = _localVariance <= 0;
            return (
            <div className="insights-section" style={{ background: '#fff', borderRadius: 8, padding: '20px', border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>
                  📋 {currentMonth} — Spending Summary
                  {showGoalCols && (
                    <span style={{ marginLeft: 12, fontSize: 13, fontWeight: 700, color: _localOnTrack ? '#16a34a' : '#dc2626' }}>
                      {_localOnTrack ? '✓ On Track' : '⚠ Over Budget'}
                    </span>
                  )}
                </h3>
              </div>

              {/* ── First-month milestone banner ── */}
              {processedMonths.length === 1 && groupedData.length > 0 && (() => {
                const recurring = groupedData.filter(g => !g.one_time);
                const topCat = recurring[0];
                const numCats = recurring.length;
                const oneTimeTotal = groupedData.filter(g => g.one_time).reduce((s, g) => s + g.amount, 0);
                return (
                  <div style={{ background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)', border: '1px solid #86efac', borderRadius: 10, padding: '16px 18px', marginBottom: 16 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: '#15803d', marginBottom: 10 }}>🎉 First month complete — here are your baseline metrics</div>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      {[
                        { label: 'Total Spent', val: `$${totalExpenses.toFixed(2)}`, sub: 'recurring expenses' },
                        { label: 'Top Category', val: topCat?.category || '—', sub: topCat ? `$${topCat.amount.toFixed(2)}` : '' },
                        { label: 'Categories', val: numCats, sub: 'with spending' },
                        ...(oneTimeTotal > 0 ? [{ label: 'One-Time', val: `$${oneTimeTotal.toFixed(2)}`, sub: 'excluded from baseline' }] : []),
                      ].map(({ label, val, sub }) => (
                        <div key={label} style={{ flex: 1, minWidth: 110, background: 'rgba(255,255,255,0.7)', borderRadius: 8, padding: '10px 14px' }}>
                          <div style={{ fontSize: 11, color: '#166534', fontWeight: 600, marginBottom: 2 }}>{label.toUpperCase()}</div>
                          <div style={{ fontSize: 18, fontWeight: 800, color: '#14532d' }}>{val}</div>
                          {sub && <div style={{ fontSize: 11, color: '#4ade80', marginTop: 1 }}>{sub}</div>}
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: 10, fontSize: 12, color: '#166534' }}>
                      💡 Use these numbers as a baseline when setting your first budget goals in the <strong>Budget &amp; Goals</strong> tab.
                    </div>
                  </div>
                );
              })()}

              {/* Summary stats */}
              {showGoalCols && (
                <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                  {[
                    { label: 'Budget',  val: _localTotalBudget, color: '#475569' },
                    { label: 'Actual',  val: totalExpenses,     color: _localOnTrack ? '#16a34a' : '#dc2626' },
                    { label: _localVariance >= 0 ? 'Overage' : 'Surplus', val: Math.abs(_localVariance), color: _localVariance > 0 ? '#dc2626' : '#16a34a' },
                  ].map(({ label, val, color }) => (
                    <div key={label} style={{ flex: 1, minWidth: 100, background: '#f8fafc', borderRadius: 8, padding: '10px 14px' }}>
                      <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, marginBottom: 2 }}>{label.toUpperCase()}</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color }}>${val?.toFixed(2)}</div>
                    </div>
                  ))}
                  {budgetComparison?.one_time_total > 0 && (
                    <div style={{ flex: 1, minWidth: 100, background: '#fffbeb', borderRadius: 8, padding: '10px 14px', border: '1px solid #fde68a' }}>
                      <div style={{ fontSize: 11, color: '#92400e', fontWeight: 600, marginBottom: 2 }}>ONE-TIME</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: '#d97706' }}>${budgetComparison.one_time_total.toFixed(2)}</div>
                    </div>
                  )}
                </div>
              )}

              {/* AI Coaching Note — replaces static recommendations list */}
              <div style={{ marginBottom: 16 }}>
                {budgetDebrief ? (
                  <div style={{ background: 'linear-gradient(135deg, #f0f9ff, #e0f2fe)', border: '1px solid #bae6fd', borderRadius: 8, padding: '14px 16px', fontSize: 14, color: '#0c4a6e', lineHeight: 1.6 }}>
                    <div style={{ fontWeight: 700, marginBottom: 6, fontSize: 11, color: '#0369a1', letterSpacing: '0.05em' }}>🤖 AI COACHING</div>
                    {budgetDebrief}
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {insights?.recommendations?.length > 0 && (
                      <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '14px 16px' }}>
                        <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 11, color: '#475569', letterSpacing: '0.04em' }}>💡 RECOMMENDATIONS</div>
                        <ul style={{ margin: 0, paddingLeft: 20 }}>
                          {insights.recommendations.map((rec, idx) => (
                            <li key={idx} style={{ marginBottom: 4, fontSize: 14, color: '#334155' }}>{rec}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div>
                      <button
                        onClick={() => loadDebrief(currentMonth)}
                        disabled={debriefLoading}
                        style={{ padding: '8px 16px', background: debriefLoading ? '#f1f5f9' : '#0ea5e9', color: debriefLoading ? '#94a3b8' : 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: debriefLoading ? 'default' : 'pointer' }}
                      >{debriefLoading ? '⏳ Generating…' : '🤖 Generate AI Coaching Note'}</button>
                    </div>
                  </div>
                )}
              </div>

              {/* Merged expense details + budget comparison table */}
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569' }}>Category</th>
                      {showGoalCols && <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Goal</th>}
                      <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Actual</th>
                      <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>% of Total</th>
                      {showGoalCols && <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Variance</th>}
                      {showGoalCols && <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569', minWidth: 110 }}>Status</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {_allRows.map((group, idx) => {
                      const _rowSubs = subcategories[group.category] || [];
                      const _rowSubSum = _rowSubs.reduce((s, sub) => s + (goals[sub] || 0), 0);
                      const _rowDirect = goals[group.category] ?? null;
                      const goalAmt = _rowSubSum > 0 ? _rowSubSum : _rowDirect;
                      const localVariance = goalAmt != null ? group.amount - goalAmt : null;
                      const isOver = localVariance != null && localVariance > 0;
                      const ofTotal = totalExpenses > 0 ? (group.amount / totalExpenses * 100) : 0;
                      const barPct = goalAmt > 0 ? Math.min((group.amount / goalAmt) * 100, 100) : 0;
                      // Show sub-rows for children that have a user-set goal or actual spend
                      const visibleSubs = _rowSubs.filter(sub => {
                        const subActual = group.subcategories?.find(s => s.category === sub)?.amount || 0;
                        return (goals[sub] != null) || subActual > 0;
                      });
                      return (
                        <React.Fragment key={group.category}>
                          <tr style={{ borderBottom: visibleSubs.length ? 'none' : '1px solid #f0f0f0', background: idx % 2 ? '#f8fafc' : '#fff' }}>
                            <td style={{ padding: '8px 12px', fontWeight: 600 }}>
                              {visibleSubs.length > 0 && <span style={{ color: '#94a3b8', marginRight: 4, fontSize: 11 }}>▾</span>}
                              {group.category}
                            </td>
                            {showGoalCols && <td style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>{goalAmt != null ? `$${goalAmt.toFixed(2)}` : '—'}</td>}
                            <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: isOver ? '#ef4444' : '#0f172a' }}>${group.amount.toFixed(2)}</td>
                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#64748b' }}>{ofTotal.toFixed(1)}%</td>
                            {showGoalCols && <td style={{ padding: '8px 12px', textAlign: 'right', color: isOver ? '#ef4444' : localVariance != null ? '#16a34a' : '#94a3b8' }}>
                              {localVariance != null ? `${isOver ? '+' : ''}${localVariance.toFixed(2)}` : '—'}
                            </td>}
                            {showGoalCols && <td style={{ padding: '8px 12px' }}>
                              {goalAmt ? (
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <div style={{ height: 6, flex: 1, background: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
                                    <div style={{ height: '100%', width: `${barPct}%`, background: isOver ? '#ef4444' : '#22c55e', borderRadius: 99 }} />
                                  </div>
                                  <span style={{ fontSize: 10, fontWeight: 700, color: isOver ? '#ef4444' : '#16a34a', minWidth: 32 }}>
                                    {`${(group.amount / goalAmt * 100).toFixed(0)}%`}
                                  </span>
                                </div>
                              ) : <span style={{ color: '#cbd5e1', fontSize: 11 }}>No goal</span>}
                            </td>}
                          </tr>
                          {visibleSubs.map((sub, si) => {
                            const subGoal = goals[sub] ?? null;
                            const subActual = group.subcategories?.find(s => s.category === sub)?.amount || 0;
                            const subVariance = subGoal != null ? subActual - subGoal : null;
                            const subIsOver = subVariance != null && subVariance > 0;
                            const subBarPct = subGoal > 0 ? Math.min((subActual / subGoal) * 100, 100) : 0;
                            const isLastSub = si === visibleSubs.length - 1;
                            return (
                              <tr key={sub} style={{ borderBottom: isLastSub ? '1px solid #e2e8f0' : '1px solid #f4f4f5', background: idx % 2 ? '#eef2f7' : '#f5f7fa' }}>
                                <td style={{ padding: '5px 12px 5px 26px', color: '#64748b', fontSize: 12 }}>↳ {sub}</td>
                                {showGoalCols && <td style={{ padding: '5px 12px', textAlign: 'right', color: '#64748b', fontSize: 12 }}>
                                  {subGoal != null ? `$${subGoal.toFixed(2)}` : '—'}
                                </td>}
                                <td style={{ padding: '5px 12px', textAlign: 'right', fontSize: 12, color: subIsOver ? '#ef4444' : '#374151' }}>${subActual.toFixed(2)}</td>
                                <td style={{ padding: '5px 12px', textAlign: 'right', color: '#cbd5e1', fontSize: 12 }}>—</td>
                                {showGoalCols && <td style={{ padding: '5px 12px', textAlign: 'right', color: subIsOver ? '#ef4444' : subVariance != null ? '#16a34a' : '#94a3b8', fontSize: 12 }}>
                                  {subVariance != null ? `${subIsOver ? '+' : ''}${subVariance.toFixed(2)}` : '—'}
                                </td>}
                                {showGoalCols && <td style={{ padding: '5px 12px' }}>
                                  {subGoal != null ? (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                      <div style={{ height: 4, flex: 1, background: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
                                        <div style={{ height: '100%', width: `${subBarPct}%`, background: subIsOver ? '#ef4444' : '#22c55e', borderRadius: 99 }} />
                                      </div>
                                      <span style={{ fontSize: 10, color: subIsOver ? '#ef4444' : '#16a34a', minWidth: 32 }}>
                                        {`${subGoal > 0 ? (subActual / subGoal * 100).toFixed(0) : 0}%`}
                                      </span>
                                    </div>
                                  ) : <span style={{ color: '#cbd5e1', fontSize: 11 }}>No goal</span>}
                                </td>}
                              </tr>
                            );
                          })}
                        </React.Fragment>
                      );
                    })}
                    <tr style={{ background: '#f1f5f9', fontWeight: 700, borderTop: '2px solid #e2e8f0' }}>
                      <td style={{ padding: '8px 12px' }}>TOTAL</td>
                      {showGoalCols && <td style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>${_localTotalBudget.toFixed(2)}</td>}
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>${totalExpenses.toFixed(2)}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>100%</td>
                      {showGoalCols && <td colSpan={2} />}
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Historical Budget Health bars */}
              {budgetSuggestions && avgMonthlyIncome > 0 && (() => {
                // Slice budgetHistory to the selected period
                const periodHistory = budgetHistory.slice(0, healthPeriod);
                if (periodHistory.length === 0) return null;
                // Compute avg actual spending per bucket across period months
                const bucketTotals = { Need: 0, Want: 0, Saving: 0 };
                const bucketCounts = { Need: 0, Want: 0, Saving: 0 };
                periodHistory.forEach(m => {
                  if (!m.categories) return;
                  Object.entries(m.categories).forEach(([cat, d]) => {
                    const buck = bucketOverrides[cat] || budgetSuggestions?.suggested_budgets?.[cat]?.bucket;
                    if (buck && bucketTotals[buck] !== undefined) {
                      bucketTotals[buck] += (d.actual || 0);
                      bucketCounts[buck] += 1;
                    }
                  });
                });
                const nMonths = periodHistory.length || 1;
                const avgIncome = avgMonthlyIncome;
                const _splits = { '50/30/20': [50, 30, 20], '60/20/20': [60, 20, 20], '70/20/10': [70, 20, 10] };
                const [needTarget, wantTarget, saveTarget] = _splits[strategy] || [50, 30, 20];
                const bars = [
                  { label: 'Needs',   total: bucketTotals.Need,   target: needTarget,  color: '#3b82f6' },
                  { label: 'Wants',   total: bucketTotals.Want,   target: wantTarget,  color: '#f59e0b' },
                  { label: 'Savings', total: bucketTotals.Saving, target: saveTarget,  color: '#22c55e' },
                ];
                return (
                  <div style={{ background: '#fff', borderRadius: 8, padding: '16px 20px', marginBottom: 12, marginTop: 16, border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
                      <h4 style={{ margin: 0, fontSize: 14 }}>📊 Historical Spending Health</h4>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>Period:</span>
                        {[3, 6, 12].map(n => (
                          <button key={n} onClick={() => setHealthPeriod(n)}
                            style={{ padding: '3px 10px', borderRadius: 20, border: '1px solid', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                              background: healthPeriod === n ? '#4f46e5' : '#f1f5f9',
                              color: healthPeriod === n ? 'white' : '#475569',
                              borderColor: healthPeriod === n ? '#4f46e5' : '#e2e8f0' }}
                          >{n} mo</button>
                        ))}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 10 }}>
                      Average actual spending over last {nMonths} month{nMonths !== 1 ? 's' : ''} vs {strategy} targets
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                      {bars.map(({ label, total, target, color }) => {
                        const pct = avgIncome > 0 ? (total / nMonths / avgIncome) * 100 : 0;
                        const isNW = label !== 'Savings';
                        const isOver = isNW ? pct > target : false;
                        const barColor = isOver ? '#ef4444' : color;
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
                );
              })()}

              {/* Monthly attainment trend */}
              {budgetComparison && budgetHistory.length > 0 && (
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
          );})()}
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
          {planSection === 'budget' && (
            processedMonths.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 320, gap: 16, textAlign: 'center', padding: '48px 40px' }}>
                <span style={{ fontSize: 52 }}>🔒</span>
                <h3 style={{ margin: 0, color: '#1e293b', fontSize: 20, fontWeight: 700 }}>Budget Goals Locked</h3>
                <p style={{ margin: 0, maxWidth: 440, fontSize: 14, color: '#64748b', lineHeight: 1.7 }}>
                  Process your first month&apos;s statements to unlock budget goal setting.<br />
                  Once you have at least one month of expense data, you&apos;ll be able to set and track category budgets here.
                </p>
                <div style={{ marginTop: 8, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '14px 24px', fontSize: 13, color: '#475569' }}>
                  <strong>To get started:</strong> go to the <strong>Statements</strong> tab, upload your bank statement PDF, and click <strong>Process</strong>.
                </div>
              </div>
            ) : (
              <>
              {/* ── Month context bar ── */}
              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 16px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 13 }}>
                <span style={{ fontWeight: 700, color: '#334155' }}>� Analyzing: {currentMonth}</span>
                <span style={{ color: '#94a3b8' }}>→</span>
                <span style={{ fontWeight: 700, color: '#4f46e5' }}>
                  📅 Setting goals for:&nbsp;
                  <input
                    type="month"
                    value={budgetTargetMonth}
                    onChange={e => setBudgetTargetMonth(e.target.value)}
                    style={{ fontWeight: 700, fontSize: 13, color: '#4f46e5', border: '1px solid #c7d2fe', borderRadius: 6, padding: '2px 6px', background: '#eef2ff', cursor: 'pointer' }}
                  />
                </span>
                {hasMonthGoals
                  ? <span style={{ color: '#16a34a', fontWeight: 600 }}>✓ Goals saved for {currentMonth}</span>
                  : <span style={{ color: '#f59e0b', fontWeight: 600 }}>No goals for {currentMonth}</span>
                }
                {goalMonths.length > 0 && (
                  <button
                    onClick={() => setShowBudgetHistory(h => !h)}
                    style={{ marginLeft: 'auto', padding: '3px 10px', background: showBudgetHistory ? '#4f46e5' : '#f1f5f9', color: showBudgetHistory ? 'white' : '#475569', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
                  >📚 History ({goalMonths.length})</button>
                )}
              </div>

              {/* ── Past Budgets History Panel ── */}
              {showBudgetHistory && goalMonths.length > 0 && (
                <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '16px', marginBottom: 12 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: '#334155', marginBottom: 10 }}>📚 Past Budget Goals</div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                          <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569' }}>Month</th>
                          <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Total Goal</th>
                          <th style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>Total Actual</th>
                          <th style={{ padding: '8px 12px', textAlign: 'center', color: '#475569' }}>Attainment</th>
                          <th style={{ padding: '8px 12px', textAlign: 'center', color: '#475569' }}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {goalMonths.map(m => {
                          const hist = budgetHistory.find(h => h.month === m);
                          const attPct = hist?.attainment_pct;
                          const good = attPct != null && attPct >= 90;
                          const isViewing = viewGoalsMonth === m;
                          const isJustCopied = copySuccessMonth === m;
                          return (
                            <React.Fragment key={m}>
                            <tr style={{ borderBottom: isViewing ? 'none' : '1px solid #f0f0f0', background: isViewing ? '#f0f9ff' : 'transparent' }}>
                              <td style={{ padding: '8px 12px', fontWeight: 600 }}>{m}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', color: '#475569' }}>
                                {hist?.total_goal != null ? `$${hist.total_goal.toFixed(2)}` : '—'}
                              </td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: good ? '#16a34a' : attPct != null ? '#dc2626' : '#0f172a' }}>
                                {hist?.total_actual != null ? `$${hist.total_actual.toFixed(2)}` : '—'}
                              </td>
                              <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                                {attPct != null
                                  ? <span style={{ fontWeight: 700, color: good ? '#16a34a' : '#dc2626' }}>{attPct}%</span>
                                  : <span style={{ color: '#cbd5e1' }}>—</span>
                                }
                              </td>
                              <td style={{ padding: '8px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                                <button
                                  onClick={() => viewGoalsForMonth(m)}
                                  style={{ padding: '3px 9px', background: isViewing ? '#0ea5e9' : '#f1f5f9', color: isViewing ? 'white' : '#0369a1', border: `1px solid ${isViewing ? '#0ea5e9' : '#bae6fd'}`, borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer', marginRight: 4 }}
                                  title={isViewing ? 'Hide goals' : `View ${m} goals`}
                                >{isViewing ? '▲ Hide' : '👁 View'}</button>
                                <button
                                  onClick={() => { copyFromMonth(m); setBudgetTargetMonth(getNextMonthOf(m)); }}
                                  style={{ padding: '3px 9px', background: isJustCopied ? '#16a34a' : '#f1f5f9', color: isJustCopied ? 'white' : '#4f46e5', border: `1px solid ${isJustCopied ? '#16a34a' : '#c7d2fe'}`, borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
                                  title={`Copy ${m} goals into budget editor`}
                                >{isJustCopied ? '✓ Loaded!' : '📋 Use'}</button>
                                <button
                                  onClick={() => {
                                    if (!window.confirm(`Delete all saved goals for ${m}? This cannot be undone.`)) return;
                                    fetch(`/api/budget/goals/${m}`, { method: 'DELETE' })
                                      .then(r => { if (r.ok) setGoalMonths(prev => prev.filter(x => x !== m)); })
                                      .catch(() => {});
                                  }}
                                  style={{ padding: '3px 9px', background: '#fef2f2', color: '#dc2626', border: '1px solid #fca5a5', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer', marginLeft: 4 }}
                                  title={`Delete saved goals for ${m}`}
                                >🗑</button>
                              </td>
                            </tr>
                            {isViewing && (
                              <tr style={{ borderBottom: '1px solid #bae6fd' }}>
                                <td colSpan={5} style={{ padding: '0 12px 14px 12px', background: '#f0f9ff' }}>
                                  {(() => {
                                    if (Object.keys(viewGoalsData).length === 0) {
                                      return <span style={{ color: '#94a3b8', fontSize: 12 }}>No goals found for this month.</span>;
                                    }
                                    // Build hierarchical display
                                    const _vParentMap = {};
                                    for (const [par, subs] of Object.entries(subcategories)) {
                                      for (const sub of subs) _vParentMap[sub] = par;
                                    }
                                    // Compute effective total (exclude parent goals when children present)
                                    let _vTotal = 0;
                                    for (const [cat, amt] of Object.entries(viewGoalsData)) {
                                      const children = subcategories[cat] || [];
                                      const hasChildGoals = children.some(c => viewGoalsData[c] != null);
                                      if (!hasChildGoals) _vTotal += Number(amt);
                                    }
                                    // Group: top-level parents and standalones
                                    const _vTopLevel = Object.keys(viewGoalsData)
                                      .filter(cat => !_vParentMap[cat])
                                      .sort((a, b) => a.localeCompare(b));
                                    return (
                                      <div>
                                        <div style={{ fontSize: 12, color: '#0369a1', fontWeight: 700, marginBottom: 10, paddingTop: 10 }}>
                                          Goals set for {m}
                                          <span style={{ marginLeft: 10, fontWeight: 400, color: '#64748b' }}>
                                            — Total: <strong style={{ color: '#0f172a' }}>${_vTotal.toFixed(2)}</strong>
                                          </span>
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '6px 20px' }}>
                                          {_vTopLevel.map(cat => {
                                            const children = (subcategories[cat] || []).filter(c => viewGoalsData[c] != null);
                                            const hasChildren = children.length > 0;
                                            const parentAmt = viewGoalsData[cat];
                                            const childSum = children.reduce((s, c) => s + Number(viewGoalsData[c]), 0);
                                            return (
                                              <div key={cat}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                                  <span style={{ fontSize: 12, fontWeight: hasChildren ? 700 : 400, color: hasChildren ? '#1e40af' : '#334155' }}>
                                                    {cat}
                                                  </span>
                                                  <span style={{ fontSize: 12, color: '#0f172a', fontWeight: 600, marginLeft: 8 }}>
                                                    ${hasChildren ? childSum.toFixed(2) : Number(parentAmt).toFixed(2)}
                                                    {hasChildren && parentAmt != null && parentAmt !== childSum &&
                                                      <span style={{ fontSize: 10, color: '#94a3b8', marginLeft: 4 }}>(set: ${Number(parentAmt).toFixed(2)})</span>
                                                    }
                                                  </span>
                                                </div>
                                                {hasChildren && children.sort((a,b) => a.localeCompare(b)).map(sub => (
                                                  <div key={sub} style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: 14, marginTop: 2 }}>
                                                    <span style={{ fontSize: 11, color: '#64748b' }}>↳ {sub}</span>
                                                    <span style={{ fontSize: 11, color: '#475569', marginLeft: 8 }}>${Number(viewGoalsData[sub]).toFixed(2)}</span>
                                                  </div>
                                                ))}
                                              </div>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    );
                                  })()}
                                </td>
                              </tr>
                            )}
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── No goals callout — offer to copy or use AI suggestions ── */}
              {!hasMonthGoals && goalMonths.length > 0 && (() => {
                // If this month predates all saved goal months, it's a historical baseline.
                // goalMonths is sorted most-recent-first, so last entry is the oldest goal month.
                const oldestGoalMonth = goalMonths[goalMonths.length - 1];
                const isHistoricalBaseline = currentMonth < oldestGoalMonth;
                if (isHistoricalBaseline) {
                  return (
                    <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '12px 16px', marginBottom: 12, fontSize: 13, color: '#166534' }}>
                      📖 <strong>{currentMonth}</strong> is a historical baseline month — no advance goals were set for it. You can set retroactive goals below if you'd like to compare.
                    </div>
                  );
                }
                return (
                  <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '12px 16px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
                    <span style={{ color: '#92400e' }}>No goals planned for <strong>{currentMonth}</strong> yet.</span>
                    <button
                      onClick={() => copyFromMonth(goalMonths[0])}
                      style={{ padding: '5px 12px', background: '#f59e0b', color: 'white', border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer', fontSize: 12 }}
                    >📋 Copy from {goalMonths[0]}</button>
                    <span style={{ color: '#b45309' }}>or adjust the AI suggestions below and click Save.</span>
                  </div>
                );
              })()}

              {/* ── Strategy Picker ── */}
              {budgetSuggestions && (<>
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

              {/* ── Pay Yourself First + What-If Slider ── */}
              <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span
                    style={{ fontWeight: 700, fontSize: 13, color: '#15803d', cursor: 'help', borderBottom: '1px dashed #86efac' }}
                    title="Pay Yourself First: decide how much to save each month before anything else. This carves out your savings from the top and gives the AI a smaller 'spendable pool' to divide across categories below. Drag the slider to explore different savings amounts, then click Apply to recalculate all category caps."
                  >💰 Pay Yourself First</span>
                  <span style={{ fontSize: 12, color: '#16a34a' }}>ℹ️</span>
                  <input
                    type="number" placeholder="e.g. 800" value={savingsTargetInput}
                    onChange={e => setSavingsTargetInput(e.target.value)}
                    style={{ width: 110, padding: '6px 10px', borderRadius: 6, border: '1px solid #86efac', fontSize: 13 }}
                  />
                  <button
                    onClick={() => reloadSuggestionsWithTarget(parseFloat(savingsTargetInput) || null, strategy)}
                    disabled={suggestionsLoading}
                    style={{ padding: '6px 14px', background: suggestionsLoading ? '#86efac' : '#16a34a', color: 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: suggestionsLoading ? 'not-allowed' : 'pointer', transition: 'background .2s', minWidth: 70 }}
                  >{suggestionsLoading ? '⏳ …' : 'Apply'}</button>
                  {budgetSuggestions.spendable_income > 0 && !suggestionsLoading && (
                    <span style={{ fontSize: 13, color: '#166534' }}>
                      Spendable pool: <strong>${budgetSuggestions.spendable_income.toLocaleString('en-US', { minimumFractionDigits: 2 })}/mo</strong>
                      {budgetSuggestions.savings_target > 0 && ` · Savings target: $${budgetSuggestions.savings_target.toFixed(2)}/mo`}
                    </span>
                  )}
                </div>
                {/* ── AI thinking animation ── */}
                {suggestionsLoading && (
                  <div className="ai-thinking-overlay">
                    <span className="ai-thinking-icon">✨</span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#4f46e5' }}>AI is recalculating your budget goals…</span>
                      <span style={{ fontSize: 11, color: '#6366f1' }}>Applying new spendable pool across unlocked categories</span>
                    </div>
                    <div className="ai-thinking-dots" style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 2 }}>
                      <span /><span /><span />
                    </div>
                  </div>
                )}
                {/* ── Saving-bucket goals breakdown ── */}
                {(() => {
                  const savingBucketTotal = Object.entries(goals || {}).reduce((sum, [cat, amt]) => {
                    const b = bucketOverrides[cat] || budgetSuggestions?.suggested_budgets?.[cat]?.bucket;
                    return b === 'Saving' ? sum + (amt || 0) : sum;
                  }, 0);
                  const pyfAmt = parseFloat(savingsTargetInput) || 0;
                  if (savingBucketTotal > 0) {
                    const totalSavings = pyfAmt + savingBucketTotal;
                    return (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #bbf7d0', fontSize: 12, color: '#166534' }}>
                        💰 <strong>Total savings picture:</strong>&nbsp;
                        {pyfAmt > 0 && <span>${pyfAmt.toFixed(0)} PYF +&nbsp;</span>}
                        <span>${savingBucketTotal.toFixed(0)} from Saving-bucket goals</span>
                        {pyfAmt > 0 && <span> = <strong>${totalSavings.toFixed(0)}/mo total</strong></span>}
                        <span style={{ color: '#64748b', marginLeft: 8 }}>· Saving-bucket goals draw from spendable, not from PYF</span>
                      </div>
                    );
                  }
                  return null;
                })()}
                {/* ── What-If Slider ── live preview, no API call ── */}
                {budgetSuggestions.avg_monthly_income > 0 && (() => {
                  const income = budgetSuggestions.avg_monthly_income;
                  const sliderVal = parseFloat(savingsTargetInput) || 0;
                  const sliderPct = Math.round(sliderVal / income * 100);
                  const _splits = { '50/30/20': [0.50, 0.30, 0.20], '60/20/20': [0.60, 0.20, 0.20], '70/20/10': [0.70, 0.20, 0.10] };
                  const [nf, wf, sf] = _splits[strategy] || [0.50, 0.30, 0.20];
                  const spendable = Math.max(0, income - sliderVal);
                  const previewNeeds = (spendable * nf).toFixed(0);
                  const previewWants = (spendable * wf).toFixed(0);
                  return (
                    <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #bbf7d0' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                        <span style={{ fontSize: 12, color: '#166534', fontWeight: 600, minWidth: 130 }}>🎚 What-If: ${Math.round(sliderVal).toLocaleString()}/mo ({sliderPct}%)</span>
                        <input
                          type="range"
                          min={0} max={Math.round(income * 0.5)} step={25}
                          value={Math.round(sliderVal)}
                          onChange={e => setSavingsTargetInput(String(e.target.value))}
                          style={{ flex: 1, accentColor: '#16a34a', cursor: 'pointer' }}
                        />
                        <span style={{ fontSize: 12, color: '#166534', minWidth: 80, textAlign: 'right' }}>
                          ${Math.round(spendable).toLocaleString()} left
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#475569' }}>
                        <span>Needs cap: <strong style={{ color: '#3b82f6' }}>${Number(previewNeeds).toLocaleString()}</strong></span>
                        <span>Wants cap: <strong style={{ color: '#f59e0b' }}>${Number(previewWants).toLocaleString()}</strong></span>
                        <span>Savings (PYF): <strong style={{ color: '#22c55e' }}>${Math.round(sliderVal).toLocaleString()} ({sliderPct}%)</strong><span style={{ color: '#9ca3af', fontWeight: 400 }}> · {Math.round(sf * 100)}% goal = ${Math.round(income * sf).toLocaleString()}</span></span>
                        <span style={{ marginLeft: 'auto', color: '#9ca3af', fontStyle: 'italic' }}>Drag to explore · Apply to recalculate</span>
                      </div>
                    </div>
                  );
                })()}
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

              {/* ── Budget Health Bars (live from current goal amounts) ── */}
              {(() => {
                const income = budgetSuggestions.avg_monthly_income || avgMonthlyIncome || 0;
                const pyfAmt = parseFloat(savingsTargetInput) || 0;
                const _parentCatsH = new Set(Object.keys(subcategories));
                // Helper: sum goals for a bucket, skipping parent cats when their subs have goals
                const goalBucketTotal = (bucket) => Object.entries(goals || {}).reduce((s, [cat, v]) => {
                  const b = bucketOverrides[cat] || budgetSuggestions?.suggested_budgets?.[cat]?.bucket;
                  if (b !== bucket) return s;
                  if (_parentCatsH.has(cat)) {
                    const subSum = (subcategories[cat] || []).reduce((ss, sub) => ss + (goals[sub] || 0), 0);
                    return subSum > 0 ? s : s + (v || 0);
                  }
                  return s + (v || 0);
                }, 0);
                const needGoals  = goalBucketTotal('Need');
                const wantGoals  = goalBucketTotal('Want');
                const saveGoals  = goalBucketTotal('Saving') + pyfAmt;
                const base = income > 0 ? income : 1;
                const _splits = { '50/30/20': [50, 30, 20], '60/20/20': [60, 20, 20], '70/20/10': [70, 20, 10] };
                const [needTarget, wantTarget, saveTarget] = _splits[strategy] || [50, 30, 20];
                return (
              <div style={{ background: '#fff', borderRadius: 8, padding: '16px 20px', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <h4 style={{ margin: 0, fontSize: 14 }}>Budget Health</h4>
                  <span style={{ fontSize: 12, color: '#94a3b8' }}>{strategy} rule · Live from current goals</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {[
                    { label: 'Needs',   goalTotal: needGoals,  target: needTarget,  color: '#3b82f6' },
                    { label: 'Wants',   goalTotal: wantGoals,  target: wantTarget,  color: '#f59e0b' },
                    { label: 'Savings', goalTotal: saveGoals,  target: saveTarget,  color: '#22c55e' },
                  ].map(({ label, goalTotal, target, color }) => {
                    const pct = income > 0 ? (goalTotal / base) * 100 : 0;
                    const isNeedsOrWants = label !== 'Savings';
                    const isOver = isNeedsOrWants ? pct > target : false;
                    const barColor = isOver ? '#ef4444' : color;
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
                );
              })()}

              {/* ── Over-income warning ── */}
              {(() => {
                // Use effective goals: for parents with sub goals, count the sub-goal sum (not the parent goal)
                const _parentCats = new Set(Object.keys(subcategories));
                const totalGoals = Object.entries(goals || {}).reduce((s, [cat, v]) => {
                  if (_parentCats.has(cat)) {
                    const subSum = (subcategories[cat] || []).reduce((ss, sub) => ss + (goals[sub] || 0), 0);
                    return subSum > 0 ? s : s + (v || 0); // skip parent if subs have goals
                  }
                  return s + (v || 0);
                }, 0);
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

              {/* ── How it connects: PYF → caps → lock ── */}
              <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 8, padding: '10px 16px', marginBottom: 12, fontSize: 12, color: '#0369a1' }}>
                <strong>How this works:</strong> Pay Yourself First carves out your savings → AI calculates the remaining category caps below → once you're happy with the numbers, lock your goals to prevent accidental edits.
              </div>
              </>)} {/* end budgetSuggestions AI block */}

              {/* ── Committed Costs Panel ── */}
              {committedCosts && committedCosts.items && committedCosts.items.length > 0 && (
                <details style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
                  <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 14, color: '#1e293b', listStyle: 'none', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>🔒 Committed Costs</span>
                    <span style={{ background: '#1e293b', color: '#fff', borderRadius: 6, padding: '2px 9px', fontSize: 13 }}>
                      ${committedCosts.committed_total.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/mo
                    </span>
                    {committedCosts.income_pct != null && (
                      <span style={{ fontSize: 12, color: '#64748b', fontWeight: 400 }}>
                        · {committedCosts.income_pct}% of income · {committedCosts.items.length} recurring merchants
                      </span>
                    )}
                    <span style={{ marginLeft: 'auto', fontSize: 11, color: '#94a3b8' }}>click to expand ▾</span>
                  </summary>
                  <div style={{ marginTop: 12, overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #e2e8f0' }}>
                          <th style={{ padding: '7px 10px', textAlign: 'left', color: '#475569' }}>Merchant</th>
                          <th style={{ padding: '7px 10px', textAlign: 'left', color: '#475569' }}>Category</th>
                          <th style={{ padding: '7px 10px', textAlign: 'right', color: '#475569' }}>Monthly</th>
                          <th style={{ padding: '7px 10px', textAlign: 'center', color: '#475569' }}>Months seen</th>
                          <th style={{ padding: '7px 10px', textAlign: 'right', color: '#475569' }}>Variability</th>
                        </tr>
                      </thead>
                      <tbody>
                        {committedCosts.items.map((item, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
                            <td style={{ padding: '7px 10px', fontWeight: 600 }}>
                              {item.is_fixed && <span title="Very low variability" style={{ marginRight: 5 }}>📌</span>}
                              {item.merchant}
                            </td>
                            <td style={{ padding: '7px 10px', color: '#64748b' }}>{item.category}</td>
                            <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 600, color: '#0f172a' }}>
                              ${item.monthly_amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </td>
                            <td style={{ padding: '7px 10px', textAlign: 'center', color: '#64748b' }}>{item.months_seen}</td>
                            <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                              <span style={{
                                fontSize: 11, padding: '2px 7px', borderRadius: 10, fontWeight: 600,
                                background: item.cv_pct < 5 ? '#f0fdf4' : item.cv_pct < 10 ? '#fffbeb' : '#fef2f2',
                                color: item.cv_pct < 5 ? '#16a34a' : item.cv_pct < 10 ? '#d97706' : '#dc2626',
                              }}>
                                {item.cv_pct}%
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}

              {/* ── Budget Table ── */}
              <div style={{ background: '#fff', borderRadius: 8, padding: '20px', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <h4 style={{ margin: 0 }}>Category Budget Goals</h4>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {/* On Track / Over / No Goal badges */}
                    {(() => {
                      const allSubCats = new Set(Object.values(subcategories).flat());
                      const activeCatSet = new Set([...availableCategories, ...allSubCats]);
                      const settingsCats = availableCategories.map(cat => {
                        const existing = groupedData.find(g => g.category === cat);
                        return existing || { category: cat, amount: 0 };
                      });
                      const retiredWithSpending = groupedData.filter(g => !g.one_time && !activeCatSet.has(g.category) && g.amount > 0);
                      const all = [...settingsCats, ...retiredWithSpending];
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
                    {/* Lock All / Unlock All convenience shortcuts */}
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <button
                        onClick={() => {
                      const seen = new Set();
                      availableCategories.forEach(c => seen.add(c));
                      Object.values(subcategories).flat().forEach(c => seen.add(c));
                      const allWithGoals = [...seen].filter(c => goals[c]);
                          setLockedCats(new Set(allWithGoals));
                        }}
                        title="Lock all categories that have a goal set"
                        style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer', border: '1px solid #e2e8f0', background: '#f8fafc', color: '#475569' }}
                      >🔒 Lock All</button>
                      <button
                        onClick={() => setLockedCats(new Set())}
                        title="Unlock all categories"
                        style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer', border: '1px solid #e2e8f0', background: '#f8fafc', color: '#475569' }}
                      >🔓 Unlock All</button>
                    </div>
                  </div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                    <thead>
                      <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                        <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#475569' }}>Category</th>
                        <th style={{ padding: '10px 12px', textAlign: 'center', fontSize: 13, color: '#475569' }}>Bucket</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>3-mo Avg</th>
                        <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 13, color: '#475569' }}>Goal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const allSubCats = new Set(Object.values(subcategories).flat());
                        const activeCatSet = new Set([...availableCategories, ...allSubCats]);
                        // Settings categories are authoritative — map them to spending data if available
                        // Exclude categories that already appear as a subcategory under a parent row
                        // (they would show twice otherwise — once standalone, once inside the parent's expanded block)
                        const settingsCats = availableCategories
                          .filter(cat => !allSubCats.has(cat))
                          .map(cat => {
                            const existing = groupedData.find(g => g.category === cat);
                            // Always build subcategory rows from the settings prop so children
                            // (e.g. Rent/Mortgage) appear even when the parent has no spending
                            const propSubs = (subcategories[cat] || []).map(subName => {
                              const existingSub = existing?.subcategories?.find(s => s.category === subName);
                              return existingSub || { category: subName, amount: 0, subcategories: [] };
                            });
                            return { ...(existing || { category: cat, amount: 0 }), subcategories: propSubs };
                          });
                        // Retired categories (had spending this month but no longer in settings)
                        // are completely excluded — they have no place in a forward-looking budget.
                        const allCategories = settingsCats;
                        // Use effective goals so parents with sub-goals don't double-count
                        const totalGoals = allCategories.reduce((s, g) => {
                          const _hasSubs = g.subcategories?.length > 0;
                          const _subSum = _hasSubs ? g.subcategories.reduce((ss, sub) => ss + (goals[sub.category] || 0), 0) : 0;
                          const _eff = _hasSubs && _subSum > 0 ? _subSum : (goals[g.category] || 0);
                          return s + _eff;
                        }, 0);
                        const isOverIncome = avgMonthlyIncome > 0 && totalGoals > avgMonthlyIncome;
                        return allCategories.map((group, idx) => {
                          const aiEntry = budgetSuggestions?.suggested_budgets?.[group.category];
                          const goal = goals[group.category];
                          const rollover = rollovers[group.category] || 0;
                          const hasSubs = group.subcategories?.length > 0;
                          const isExpanded = expandedBudgetGroups.has(group.category);
                          // If subcategories have their own goals, sum them for the parent goal
                          const subGoalTotal = hasSubs
                            ? group.subcategories.reduce((s, sub) => s + (goals[sub.category] || 0), 0)
                            : 0;
                          const effectiveGoal = hasSubs && subGoalTotal > 0 ? subGoalTotal : goal;
                          const effectiveCap = effectiveGoal ? effectiveGoal + rollover : null;
                          const actual = group.amount;
                          const over = effectiveCap && actual > effectiveCap;
                          const nearLimit = effectiveCap && !over && (actual / effectiveCap) >= 0.85;
                          const barColor = !effectiveCap ? '#cbd5e1' : over ? '#ef4444' : nearLimit ? '#f59e0b' : '#22c55e';
                          const pct = effectiveCap ? Math.min((actual / effectiveCap) * 100, 100) : null;
                          const ofTotalPct = totalExpenses > 0 ? (actual / totalExpenses * 100) : 0;
                          const bucket = bucketOverrides[group.category] || aiEntry?.bucket || '';
                          const isFixed = aiEntry?.is_fixed_cost;
                          const fixednessTier = aiEntry?.fixedness_tier;
                          const isCommitted = aiEntry?.is_committed;
                          const goalMode = aiEntry?.goal_mode;
                          // Lock state is purely from lockedCats (user-controlled); goalMode is a hint only
                          const isCatLocked = lockedCats.has(group.category);
                          const trendDir = aiEntry?.trend_direction;
                          const trendIcon = trendDir === 'increasing' ? '📈' : trendDir === 'decreasing' ? '📉' : null;
                          const bucketColor = bucket === 'Need' ? '#3b82f6' : bucket === 'Want' ? '#f59e0b' : bucket === 'Saving' ? '#22c55e' : '#94a3b8';
                          const predictiveIcon = goalMode === 'predictive'
                            ? (isCommitted && !isFixed ? '🔁' : '📌')
                            : null;
                          const predictiveTitle = goalMode === 'predictive'
                            ? (isCommitted && !isFixed
                                ? 'Committed recurring expense — goal is a forecast of expected spend, not a reduction target'
                                : fixednessTier === 'semi-fixed'
                                  ? 'Semi-fixed cost (seasonal variation) — forecast, not a reduction target'
                                  : 'Fixed cost — goal is a forecast of expected spend, not a reduction target')
                            : null;

                          // Reusable goal cell renderer (used for both parent and sub-rows)
                          const renderGoalCell = (cat, catGoal, catAiEntry, catIsLocked, catRollover, isSubRow) => {
                            const catEditing = editingGoal === cat;
                            const catRolloverAmt = catRollover || 0;
                            return (
                              <td style={{ padding: isSubRow ? '7px 12px 7px 28px' : '11px 12px', textAlign: 'right', backgroundColor: isOverIncome && !isSubRow ? '#fff5f5' : 'transparent' }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                                  <button
                                    onClick={() => {
                                      setLockedCats(prev => {
                                        const next = new Set(prev);
                                        if (next.has(cat)) next.delete(cat);
                                        else if (catGoal) next.add(cat);
                                        return next;
                                      });
                                    }}
                                    title={goalMode === 'predictive' && !isSubRow ? `Predictive goal (forecast) — ${catIsLocked ? 'click to unlock' : 'click to lock'}` : catIsLocked ? 'Click to unlock this goal' : 'Click to lock this goal'}
                                    style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontSize: 13, opacity: catGoal ? 1 : 0.3, lineHeight: 1 }}
                                  >
                                    {catIsLocked ? '🔒' : '🔓'}
                                  </button>
                                  {catIsLocked ? (
                                    <span style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>
                                      {catGoal ? `$${catGoal.toFixed(2)}` : catAiEntry ? `$${catAiEntry.suggested_amount.toFixed(2)}` : '—'}
                                    </span>
                                  ) : catEditing ? (
                                    <input
                                      type="number" defaultValue={catGoal ?? (catAiEntry?.suggested_amount ?? '')} autoFocus
                                      style={{ width: 82, padding: '3px 7px', borderRadius: 4, fontSize: 13, textAlign: 'right', border: '1px solid #4f46e5', outline: 'none' }}
                                      onBlur={e => saveGoal(cat, e.target.value)}
                                      onKeyDown={e => { if (e.key === 'Enter') saveGoal(cat, e.target.value); if (e.key === 'Escape') setEditingGoal(null); }}
                                    />
                                  ) : (
                                    <span
                                      onClick={() => setEditingGoal(cat)}
                                      title={catGoal ? 'Click to edit' : 'Click to set — AI suggests $' + (catAiEntry?.suggested_amount?.toFixed(0) ?? '?')}
                                      style={{ cursor: 'pointer', color: catGoal ? '#0f172a' : '#6366f1', fontWeight: catGoal ? 600 : 400, fontSize: 13, borderBottom: '1px dashed #cbd5e1', paddingBottom: 1, fontStyle: catGoal ? 'normal' : 'italic' }}
                                    >
                                      {catGoal ? `$${catGoal.toFixed(2)}` : catAiEntry ? `$${catAiEntry.suggested_amount.toFixed(0)}` : 'Set goal'}
                                    </span>
                                  )}
                                </div>
                                {catRolloverAmt > 0 && (
                                  <div title={`$${catRolloverAmt.toFixed(2)} surplus rolled over`} style={{ fontSize: 10, color: '#d97706', fontWeight: 600, marginTop: 2, textAlign: 'right' }}>
                                    ↩ +${catRolloverAmt.toFixed(0)} rollover
                                  </div>
                                )}
                              </td>
                            );
                          };

                          return (
                            <React.Fragment key={group.category}>
                              {/* ── Parent row ── */}
                              <tr style={{ borderBottom: hasSubs && isExpanded ? 'none' : '1px solid #f0f0f0', background: hasSubs ? '#eef2ff' : 'white', borderLeft: hasSubs ? '3px solid #6366f1' : '3px solid transparent' }}>
                                {/* Category */}
                                <td style={{ padding: '11px 12px', fontWeight: 600 }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                    <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, backgroundColor: COLORS[idx % COLORS.length], flexShrink: 0 }} />
                                    {hasSubs ? (
                                      <button
                                        onClick={() => setExpandedBudgetGroups(prev => { const n = new Set(prev); n.has(group.category) ? n.delete(group.category) : n.add(group.category); return n; })}
                                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontSize: 13, color: '#4f46e5', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}
                                        title={isExpanded ? 'Collapse subcategories' : 'Expand subcategories'}
                                      >
                                        <span style={{ fontSize: 10 }}>{isExpanded ? '▼' : '▶'}</span>
                                        <span>{group.category}</span>
                                        <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>({group.subcategories.length})</span>
                                      </button>
                                    ) : (
                                      <span>{group.category}</span>
                                    )}
                                    {trendIcon && <span title={`Trending ${trendDir}`} style={{ fontSize: 11 }}>{trendIcon}</span>}
                                    {predictiveIcon && <span title={predictiveTitle} style={{ fontSize: 10, color: '#94a3b8' }}>{predictiveIcon}</span>}
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
                                {/* 3-mo Avg + sparkline */}
                                <td style={{ padding: '11px 12px', textAlign: 'right', color: '#64748b', fontSize: 13 }}>
                                  {(() => {
                                    const bars = categoryHistory.months_ordered.map(
                                      m => categoryHistory.by_month[m]?.[group.category] ?? 0
                                    );
                                    const avg = aiEntry ? aiEntry.historical_avg : null;
                                    const maxVal = Math.max(...bars, 0.01);
                                    if (bars.length < 2) {
                                      return avg != null ? `$${avg.toFixed(0)}` : <span style={{ color: '#cbd5e1' }}>—</span>;
                                    }
                                    return (
                                      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end', gap: 2 }}>
                                        {bars.map((v, i) => (
                                          <div key={i} title={`${categoryHistory.months_ordered[i]}: $${v.toFixed(0)}`}
                                            style={{ width: 5, height: `${Math.max(Math.round(v / maxVal * 20), 2)}px`, background: i === bars.length - 1 ? '#4f46e5' : '#cbd5e1', borderRadius: '1px 1px 0 0', transition: 'height .3s' }}
                                          />
                                        ))}
                                        {avg != null && <span style={{ fontSize: 11, marginLeft: 4, color: '#475569' }}>${avg.toFixed(0)}</span>}
                                      </div>
                                    );
                                  })()}
                                </td>
                                {/* Goal cell — if parent has sub-goals: show sum; otherwise editable */}
                                {hasSubs && subGoalTotal > 0 ? (
                                  <td style={{ padding: '11px 12px', textAlign: 'right' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 5 }}>
                                      <span style={{ fontSize: 10, color: '#94a3b8' }}>Σ</span>
                                      <span
                                        style={{ fontWeight: 700, fontSize: 13, color: '#4f46e5', cursor: 'pointer', borderBottom: '1px dashed #c7d2fe' }}
                                        onClick={() => setExpandedBudgetGroups(prev => { const n = new Set(prev); n.has(group.category) ? n.delete(group.category) : n.add(group.category); return n; })}
                                        title="Sum of subcategory goals — click to expand"
                                      >
                                        ${subGoalTotal.toFixed(2)}
                                      </span>
                                    </div>
                                    {rollover > 0 && (
                                      <div style={{ fontSize: 10, color: '#d97706', fontWeight: 600, marginTop: 2, textAlign: 'right' }}>
                                        ↩ +${rollover.toFixed(0)} rollover
                                      </div>
                                    )}
                                  </td>
                                ) : renderGoalCell(group.category, goal, aiEntry, isCatLocked, rollover, false)}
                              </tr>

                              {/* ── Subcategory rows (only when expanded) ── */}
                              {hasSubs && isExpanded && (
                              <tr key={group.category + '-dropdown'}>
                                <td colSpan={4} style={{ padding: 0, background: '#f5f7ff', borderBottom: '2px solid #e0e7ff', borderLeft: '3px solid #6366f1' }}>
                                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <tbody>
                              {group.subcategories.map(sub => {
                                const subGoal = goals[sub.category];
                                const subAiEntry = budgetSuggestions?.suggested_budgets?.[sub.category];
                                const subIsLocked = lockedCats.has(sub.category);
                                const subActual = sub.amount;
                                const subCap = subGoal || null;
                                const subOver = subCap && subActual > subCap;
                                const subPct = subCap ? Math.min((subActual / subCap) * 100, 100) : null;
                                const subBarColor = !subCap ? '#cbd5e1' : subOver ? '#ef4444' : (subActual / subCap) >= 0.85 ? '#f59e0b' : '#22c55e';
                                const subOfTotal = totalExpenses > 0 ? (subActual / totalExpenses * 100) : 0;
                                const subBars = categoryHistory.months_ordered.map(m => categoryHistory.by_month[m]?.[sub.category] ?? 0);
                                const subMaxVal = Math.max(...subBars, 0.01);
                                return (
                                  <tr key={sub.category} style={{ borderBottom: '1px solid #e8edff', background: '#f8f9ff' }}>
                                    {/* Sub-category name — indented */}
                                    <td style={{ padding: '7px 12px 7px 40px', fontSize: 12, color: '#475569' }}>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span style={{ color: '#94a3b8' }}>↳</span>
                                        <span style={{ fontWeight: 500 }}>{sub.category}</span>
                                      </div>
                                    </td>
                                    {/* Bucket — inherit from parent, show dimmed */}
                                    <td style={{ padding: '7px 12px', textAlign: 'center', color: '#94a3b8', fontSize: 11 }}>{bucket || '—'}</td>
                                    {/* 3-mo sparkline */}
                                    <td style={{ padding: '7px 12px', textAlign: 'right', color: '#64748b', fontSize: 12 }}>
                                      {subBars.length >= 2 ? (
                                        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end', gap: 2 }}>
                                          {subBars.map((v, i) => (
                                            <div key={i} title={`${categoryHistory.months_ordered[i]}: $${v.toFixed(0)}`}
                                              style={{ width: 4, height: `${Math.max(Math.round(v / subMaxVal * 16), 2)}px`, background: i === subBars.length - 1 ? '#818cf8' : '#e0e7ff', borderRadius: '1px 1px 0 0' }}
                                            />
                                          ))}
                                          {subAiEntry?.historical_avg != null && <span style={{ fontSize: 10, marginLeft: 3, color: '#64748b' }}>${subAiEntry.historical_avg.toFixed(0)}</span>}
                                        </div>
                                      ) : subAiEntry?.historical_avg != null ? `$${subAiEntry.historical_avg.toFixed(0)}` : <span style={{ color: '#cbd5e1' }}>—</span>}
                                    </td>
                                    {/* Sub goal cell */}
                                    {renderGoalCell(sub.category, subGoal, subAiEntry, subIsLocked, 0, true)}
                                  </tr>
                                );
                              })}
                                    </tbody>
                                  </table>
                                </td>
                              </tr>
                              )}
                            </React.Fragment>
                          );
                        });
                      })()}
                      <tr style={{ background: '#f1f5f9', fontWeight: 700, borderTop: '2px solid #e2e8f0' }}>
                        <td style={{ padding: '11px 12px' }}>TOTAL</td>
                        <td />
                        <td style={{ padding: '11px 12px', textAlign: 'right', color: '#475569' }}>
                          ${(() => {
                            // Sum 3-mo avg only for visible top-level rows; use sub-avgs for
                            // parent categories to avoid double-counting
                            const _sc = new Set(Object.values(subcategories).flat());
                            return availableCategories.filter(c => !_sc.has(c)).reduce((s, cat) => {
                              const propSubs = subcategories[cat] || [];
                              if (propSubs.length > 0) {
                                const subAvg = propSubs.reduce((ss, sub) => ss + (budgetSuggestions?.suggested_budgets?.[sub]?.historical_avg || 0), 0);
                                if (subAvg > 0) return s + subAvg;
                              }
                              return s + (budgetSuggestions?.suggested_budgets?.[cat]?.historical_avg || 0);
                            }, 0).toFixed(2);
                          })()}
                        </td>
                        <td style={{ padding: '11px 12px', textAlign: 'right', color: '#4f46e5' }}>
                          ${(() => {
                            // Sum goals only for visible top-level rows; for parents with
                            // sub-goals use the sub-sum to avoid double-counting
                            const _sc = new Set(Object.values(subcategories).flat());
                            return availableCategories.filter(c => !_sc.has(c)).reduce((s, cat) => {
                              const propSubs = subcategories[cat] || [];
                              if (propSubs.length > 0) {
                                const subSum = propSubs.reduce((ss, sub) => ss + (goals[sub] || 0), 0);
                                if (subSum > 0) return s + subSum;
                              }
                              return s + (goals[cat] || 0);
                            }, 0).toFixed(2);
                          })()}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                {/* Action buttons */}
                <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
                  <button
                    onClick={saveBudgets}
                    style={{ padding: '9px 18px', background: '#4f46e5', color: 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                    title={`Save these goals for ${budgetTargetMonth}`}
                  >💾 Save Goals for {budgetTargetMonth}</button>
                  <button
                    onClick={() => {
                      if (!budgetSuggestions?.suggested_budgets || !setGoals) return;
                      const updated = { ...goals };
                      for (const [cat, entry] of Object.entries(budgetSuggestions.suggested_budgets)) {
                        // Only reset categories that are NOT user-locked
                        if (!lockedCats.has(cat)) {
                          updated[cat] = entry.suggested_amount;
                        }
                      }
                      setGoals(updated);
                      localStorage.setItem('budgetGoals', JSON.stringify(updated));
                    }}
                    style={{ padding: '9px 18px', background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >↺ Reset to AI</button>
                  <button
                    onClick={() => {
                      const allSubCatsExp = new Set(Object.values(subcategories).flat());
                      const activeCatSetExp = new Set([...availableCategories, ...allSubCatsExp]);
                      const settingsCatsExp = availableCategories.map(cat => {
                        const existing = groupedData.find(g => g.category === cat);
                        return existing || { category: cat, amount: 0 };
                      });
                      const retiredExp = groupedData.filter(g => !g.one_time && !activeCatSetExp.has(g.category) && g.amount > 0);
                      const allCats = [...settingsCatsExp, ...retiredExp];
                      const header = ['Category', 'Bucket', '3-mo Avg', 'Goal', 'Locked', 'Actual'].join(',');
                      const rows = allCats.map(g => {
                        const ai = budgetSuggestions?.suggested_budgets?.[g.category];
                        const locked = lockedCats.has(g.category) || ai?.is_fixed_cost ? 'yes' : 'no';
                        return [g.category, ai?.bucket || '', ai?.historical_avg?.toFixed(2) || '', (goals[g.category] || '').toString(), locked, g.amount.toFixed(2)].join(',');
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
                  💡 AI suggestion shown in <em>italic indigo</em> — click to override. Click 🔓/🔒 to pin a goal so Reset to AI won’t touch it. 📈📉 show 3-month trend.
                </p>
              </div>
              </>
            )
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
