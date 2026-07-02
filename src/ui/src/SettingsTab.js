import React, { useEffect, useState, useCallback } from 'react';

const API = 'http://localhost:8000';

const ACTION_LABELS = { income: 'Always Income', expense: 'Always Expense', ignore: 'Always Ignore' };
const ACTION_COLORS = { income: '#0891b2', expense: '#6366f1', ignore: '#dc2626' };

const REASON_LABELS = {
  transfer_keyword: 'Transfer Keyword',
  cross_account:    'Cross-Account Transfer',
  bank_transfer:    'Bank Transfer',
  manual_delete:    'Manually Deleted',
};

const REASON_COLORS = {
  transfer_keyword: '#6366f1',
  cross_account:    '#0891b2',
  bank_transfer:    '#059669',
  manual_delete:    '#dc2626',
};

const REASON_ORDER = ['manual_delete', 'transfer_keyword', 'cross_account', 'bank_transfer'];

export default function SettingsTab({ onCategoriesUpdated }) {
  const [activeSubTab, setActiveSubTab] = useState('auto-filters');

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Sub-tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 28, background: '#f1f5f9', borderRadius: 10, padding: 4, width: 'fit-content' }}>
        {[
          { key: 'auto-filters', label: '🚫 Auto-Filter Manager' },
          { key: 'merchant-rules', label: '📋 Merchant Rules' },
          { key: 'keywords', label: '🔑 Keywords' },
          { key: 'categories', label: '🏷️ Categories' },
        ].map(t => (
          <button key={t.key} onClick={() => setActiveSubTab(t.key)} style={{
            padding: '7px 18px', borderRadius: 8, border: 'none', cursor: 'pointer',
            fontWeight: 600, fontSize: 13, transition: 'all 0.15s',
            background: activeSubTab === t.key ? '#fff' : 'transparent',
            color: activeSubTab === t.key ? '#1e293b' : '#64748b',
            boxShadow: activeSubTab === t.key ? '0 1px 4px rgba(0,0,0,.10)' : 'none',
          }}>{t.label}</button>
        ))}
      </div>

      {activeSubTab === 'auto-filters' && <AutoFilterPanel />}
      {activeSubTab === 'merchant-rules' && <MerchantRulesPanel />}
      {activeSubTab === 'keywords' && <KeywordsPanel />}
      {activeSubTab === 'categories' && <CategoriesPanel onSaved={onCategoriesUpdated} />}
    </div>
  );
}

/* ── Auto-Filter Panel ──────────────────────────────────────────────────── */
function AutoFilterPanel() {
  const [records, setRecords]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [filter, setFilter]           = useState('');
  const [monthFilter, setMonthFilter] = useState('all');
  const [restoreMsg, setRestoreMsg]   = useState('');
  const [collapsed, setCollapsed]     = useState({});

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/auto-filters`)
      .then(r => r.json())
      .then(d => {
        setRecords(d.auto_filters || []);
        setLoading(false);
      })
      .catch(err => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleWhitelist = async (id, current) => {
    const next = !current;
    try {
      const res = await fetch(`${API}/api/auto-filters/${id}/whitelist`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ whitelisted: next }),
      });
      if (!res.ok) throw new Error(await res.text());
      setRecords(prev =>
        prev.map(r => r.id === id ? { ...r, whitelisted: next } : r)
      );
    } catch (e) {
      alert(`Error: ${e.message}`);
    }
  };

  const deleteRecord = async (id, reason) => {
    try {
      const res = await fetch(`${API}/api/auto-filters/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setRecords(prev => prev.filter(r => r.id !== id));
      if (data.restored) {
        setRestoreMsg('Transaction restored to All Transactions.');
        setTimeout(() => setRestoreMsg(''), 4000);
      }
    } catch (e) {
      alert(`Error: ${e.message}`);
    }
  };

  const toggleCollapse = (reason) =>
    setCollapsed(prev => ({ ...prev, [reason]: !prev[reason] }));

  const filtered = records.filter(r => {
    const matchesText = !filter || (r.place_display || r.place_normalized || '')
      .toLowerCase().includes(filter.toLowerCase());
    const seenMonths = Array.isArray(r.seen_months)
      ? r.seen_months
      : (r.report_month ? [r.report_month] : []);
    const matchesMonth = monthFilter === 'all' || seenMonths.includes(monthFilter);
    return matchesText && matchesMonth;
  });

  const knownReasonsSet = new Set(REASON_ORDER);
  const groups = [
    ...REASON_ORDER
      .map(reason => ({ reason, rows: filtered.filter(r => r.reason === reason) }))
      .filter(g => g.rows.length > 0),
    ...(() => {
      const unknownRows = filtered.filter(r => !knownReasonsSet.has(r.reason));
      return unknownRows.length > 0 ? [{ reason: 'other', rows: unknownRows }] : [];
    })(),
  ];

  const whitelistedCount = records.filter(r => r.whitelisted).length;
  const months = [...new Set(
    records.flatMap(r =>
      Array.isArray(r.seen_months) && r.seen_months.length > 0
        ? r.seen_months
        : (r.report_month ? [r.report_month] : [])
    )
  )].filter(Boolean).sort().reverse();

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#1e293b' }}>
          Auto-Filter Manager
        </h2>
        <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: 14 }}>
          Transactions auto-removed during processing are tracked here.
          {whitelistedCount > 0 && (
            <span style={{ marginLeft: 8, color: '#059669', fontWeight: 600 }}>
              {whitelistedCount} whitelisted
            </span>
          )}
        </p>
      </div>

      {/* Info banner */}
      <div style={{
        background: '#f8fafc',
        border: '1px solid #cbd5e1',
        borderRadius: 8,
        padding: '10px 16px',
        marginBottom: 20,
        fontSize: 13,
        color: '#475569',
      }}>
        <strong>Whitelist</strong> an entry to keep it on future reprocesses.
        Pressing <strong>✕</strong> removes the tracking record — for manually
        deleted transactions it also restores them to All Transactions.
      </div>

      {/* Restore success banner */}
      {restoreMsg && (
        <div style={{
          background: '#f0fdf4', border: '1px solid #86efac',
          borderRadius: 8, padding: '8px 16px', marginBottom: 16,
          fontSize: 13, color: '#15803d',
        }}>
          ↩ {restoreMsg}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          placeholder="Filter by merchant name…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{
            padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 6,
            fontSize: 13, outline: 'none', minWidth: 220,
          }}
        />
        <select
          value={monthFilter}
          onChange={e => setMonthFilter(e.target.value)}
          style={{
            padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 6,
            fontSize: 13, outline: 'none', background: '#fff',
          }}
        >
          <option value="all">All months</option>
          {months.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <button
          onClick={load}
          style={{
            padding: '7px 16px', border: '1px solid #cbd5e1', borderRadius: 6,
            fontSize: 13, background: '#f8fafc', cursor: 'pointer',
          }}
        >
          ↻ Refresh
        </button>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: '#94a3b8' }}>
          {filtered.length} record{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Content */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>Loading…</div>
      )}
      {error && (
        <div style={{ color: '#dc2626', padding: 16 }}>Error: {error}</div>
      )}
      {!loading && !error && filtered.length === 0 && (
        <div style={{
          textAlign: 'center', padding: 48, color: '#94a3b8',
          border: '2px dashed #e2e8f0', borderRadius: 10,
        }}>
          No auto-filtered transactions recorded yet.
          <br />
          <span style={{ fontSize: 13 }}>
            They will appear here after you process or force-reprocess a month.
          </span>
        </div>
      )}

      {!loading && !error && groups.map(({ reason, rows }) => {
        const color = REASON_COLORS[reason] || '#64748b';
        const label = REASON_LABELS[reason] || reason;
        const isCollapsed = !!collapsed[reason];
        const showKeyword     = reason !== 'manual_delete';
        const showOccurrences = reason !== 'manual_delete';
        const wlCount = rows.filter(r => r.whitelisted).length;

        return (
          <div key={reason} style={{ marginBottom: 20 }}>
            {/* Section header */}
            <div
              onClick={() => toggleCollapse(reason)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px', cursor: 'pointer', userSelect: 'none',
                background: color + '0d',
                borderTop: `1px solid ${color}30`,
                borderRight: `1px solid ${color}30`,
                borderBottom: isCollapsed ? `1px solid ${color}30` : 'none',
                borderLeft: `4px solid ${color}`,
                borderRadius: isCollapsed ? 8 : '8px 8px 0 0',
              }}
            >
              <span style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>{label}</span>
              <span style={{
                background: color + '20', color,
                border: `1px solid ${color}40`,
                borderRadius: 10, padding: '1px 8px', fontSize: 12, fontWeight: 600,
              }}>
                {rows.length}
              </span>
              {wlCount > 0 && (
                <span style={{
                  background: '#dcfce7', color: '#16a34a',
                  borderRadius: 10, padding: '1px 8px', fontSize: 12, fontWeight: 600,
                }}>
                  {wlCount} whitelisted
                </span>
              )}
              <span style={{ marginLeft: 'auto', color: '#94a3b8', fontSize: 13 }}>
                {isCollapsed ? '▶' : '▼'}
              </span>
            </div>

            {/* Table */}
            {!isCollapsed && (
              <div style={{
                overflowX: 'auto',
                border: `1px solid ${color}30`,
                borderTop: 'none',
                borderRadius: '0 0 8px 8px',
              }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                      {['Merchant', 'Amount', 'Month', ...(showKeyword ? ['Keyword'] : []), ...(showOccurrences ? ['Occurrences'] : []), 'Last Seen', '', ''].map((h, i) => (
                        <th key={i} style={{
                          padding: '8px 12px',
                          textAlign: h === 'Occurrences' || h === '' ? 'center' : 'left',
                          fontWeight: 600, color: '#475569', fontSize: 12, whiteSpace: 'nowrap',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr
                        key={r.id}
                        style={{
                          background: r.whitelisted ? '#f0fdf4' : (i % 2 === 0 ? '#fff' : '#f8fafc'),
                          borderBottom: '1px solid #e2e8f0',
                        }}
                      >
                        <td style={{ padding: '9px 12px', maxWidth: 240 }}>
                          <div style={{ fontWeight: 500, color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {r.place_display || r.place_normalized}
                          </div>
                          {r.place_display && r.place_display !== r.place_normalized && (
                            <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2 }}>{r.place_normalized}</div>
                          )}
                        </td>
                        <td style={{ padding: '9px 12px', whiteSpace: 'nowrap', color: '#475569' }}>
                          {r.amount !== null ? `$${Number(r.amount).toFixed(2)}` : '—'}
                        </td>
                        <td
                          style={{ padding: '9px 12px', whiteSpace: 'nowrap', color: '#64748b' }}
                          title={Array.isArray(r.seen_months) && r.seen_months.length > 1 ? r.seen_months.join(', ') : undefined}
                        >
                          {r.report_month || '—'}
                          {Array.isArray(r.seen_months) && r.seen_months.length > 1 && (
                            <span style={{ fontSize: 10, color: '#94a3b8', marginLeft: 4 }}>
                              +{r.seen_months.length - 1}
                            </span>
                          )}
                        </td>
                        {showKeyword && (
                          <td style={{ padding: '9px 12px', color: '#64748b', fontFamily: 'monospace', fontSize: 12 }}>
                            {r.keyword_matched || '—'}
                          </td>
                        )}
                        {showOccurrences && (
                          <td style={{ padding: '9px 12px', textAlign: 'center', color: '#475569' }}>
                            {r.occurrence_count}
                          </td>
                        )}
                        <td style={{ padding: '9px 12px', whiteSpace: 'nowrap', color: '#64748b', fontSize: 12 }}>
                          {r.last_seen ? r.last_seen.replace('T', ' ') : '—'}
                        </td>
                        <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                          <button
                            onClick={() => toggleWhitelist(r.id, r.whitelisted)}
                            title={r.whitelisted ? 'Click to remove from whitelist' : 'Click to whitelist (preserve on reprocess)'}
                            style={{
                              padding: '3px 10px', borderRadius: 5, border: 'none',
                              cursor: 'pointer', fontWeight: 600, fontSize: 12,
                              background: r.whitelisted ? '#dcfce7' : '#f1f5f9',
                              color: r.whitelisted ? '#16a34a' : '#94a3b8',
                              transition: 'all 0.15s',
                            }}
                          >
                            {r.whitelisted ? '✓ Whitelisted' : 'Whitelist'}
                          </button>
                        </td>
                        <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                          <button
                            onClick={() => deleteRecord(r.id, r.reason)}
                            title="Remove this record entirely"
                            style={{
                              padding: '3px 7px', borderRadius: 5,
                              border: '1px solid #fecaca', background: '#fff5f5',
                              color: '#dc2626', cursor: 'pointer', fontSize: 12,
                            }}
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Merchant Rules Panel ────────────────────────────────────────────────── */
function MerchantRulesPanel() {
  const [rules, setRules]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [filter, setFilter]     = useState('');
  const [editing, setEditing]   = useState({}); // id → {action, category}

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/merchant-rules`)
      .then(r => r.json())
      .then(d => { setRules(d.rules || []); setLoading(false); })
      .catch(err => { setError(String(err)); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const deleteRule = async (id) => {
    if (!window.confirm('Remove this merchant rule? Future transactions from this merchant will be auto-categorized normally.')) return;
    try {
      const res = await fetch(`${API}/api/merchant-rules/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await res.text());
      setRules(prev => prev.filter(r => r.id !== id));
    } catch (e) { alert(`Error: ${e.message}`); }
  };

  const saveEdit = async (id) => {
    const ed = editing[id];
    if (!ed) return;
    try {
      const res = await fetch(`${API}/api/merchant-rules/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: ed.action, category: ed.category || '' }),
      });
      if (!res.ok) throw new Error(await res.text());
      setRules(prev => prev.map(r => r.id === id ? { ...r, ...ed } : r));
      setEditing(prev => { const n = { ...prev }; delete n[id]; return n; });
    } catch (e) { alert(`Error: ${e.message}`); }
  };

  const filtered = rules.filter(r =>
    !filter || (r.display_name || r.merchant_key || '').toLowerCase().includes(filter.toLowerCase())
  );

  const groups = ['income', 'expense', 'ignore'].map(action => ({
    action,
    rows: filtered.filter(r => r.action === action),
  })).filter(g => g.rows.length > 0);

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#1e293b' }}>Merchant Rules</h2>
        <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: 14 }}>
          Rules are applied every time a month is processed. They override the parser&apos;s auto-classification.
          Rules are created when you confirm &quot;save as recurring rule&quot; while reclassifying an expense as income in the Transactions tab.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
        <input
          placeholder="Filter by merchant name…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, outline: 'none', minWidth: 220 }}
        />
        <button onClick={load} style={{ padding: '7px 16px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, background: '#f8fafc', cursor: 'pointer' }}>
          ↻ Refresh
        </button>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: '#94a3b8' }}>
          {filtered.length} rule{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>Loading…</div>}
      {error && <div style={{ color: '#dc2626', padding: 16 }}>Error: {error}</div>}
      {!loading && !error && filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: 48, color: '#94a3b8', border: '2px dashed #e2e8f0', borderRadius: 10 }}>
          No merchant rules yet.
          <br />
          <span style={{ fontSize: 13 }}>Rules are created when you reclassify a transaction and choose &quot;save as recurring rule&quot;.</span>
        </div>
      )}

      {!loading && !error && groups.map(({ action, rows }) => {
        const color = ACTION_COLORS[action] || '#64748b';
        const label = ACTION_LABELS[action] || action;
        return (
          <div key={action} style={{ marginBottom: 20 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px',
              background: color + '0d',
              borderTop: `1px solid ${color}30`, borderRight: `1px solid ${color}30`,
              borderBottom: `1px solid ${color}30`, borderLeft: `4px solid ${color}`,
              borderRadius: '8px 8px 0 0',
            }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>{label}</span>
              <span style={{ background: color + '20', color, border: `1px solid ${color}40`, borderRadius: 10, padding: '1px 8px', fontSize: 12, fontWeight: 600 }}>
                {rows.length}
              </span>
            </div>
            <div style={{ overflowX: 'auto', border: `1px solid ${color}30`, borderTop: 'none', borderRadius: '0 0 8px 8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                    {['Merchant', 'Key', 'Action', ...(action === 'expense' ? ['Category'] : []), ''].map((h, i) => (
                      <th key={i} style={{ padding: '8px 12px', textAlign: h === '' ? 'center' : 'left', fontWeight: 600, color: '#475569', fontSize: 12, whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const ed = editing[r.id];
                    return (
                      <tr key={r.id} style={{ background: i % 2 === 0 ? '#fff' : '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                        <td style={{ padding: '9px 12px', fontWeight: 500, color: '#1e293b' }}>
                          {r.display_name || r.merchant_key}
                        </td>
                        <td style={{ padding: '9px 12px', color: '#94a3b8', fontFamily: 'monospace', fontSize: 11 }}>
                          {r.merchant_key}
                        </td>
                        <td style={{ padding: '9px 12px' }}>
                          {ed ? (
                            <select
                              value={ed.action}
                              onChange={e => setEditing(prev => ({ ...prev, [r.id]: { ...ed, action: e.target.value } }))}
                              style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid #cbd5e1', fontSize: 12 }}
                            >
                              <option value="income">Always Income</option>
                              <option value="expense">Always Expense</option>
                              <option value="ignore">Always Ignore</option>
                            </select>
                          ) : (
                            <span style={{ background: color + '20', color, border: `1px solid ${color}40`, borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 600 }}>
                              {label}
                            </span>
                          )}
                        </td>
                        {action === 'expense' && (
                          <td style={{ padding: '9px 12px', color: '#64748b' }}>
                            {ed ? (
                              <input
                                value={ed.category || ''}
                                onChange={e => setEditing(prev => ({ ...prev, [r.id]: { ...ed, category: e.target.value } }))}
                                placeholder="Category (optional)"
                                style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid #cbd5e1', fontSize: 12, width: 160 }}
                              />
                            ) : (r.category || '—')}
                          </td>
                        )}
                        <td style={{ padding: '9px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                          {ed ? (
                            <>
                              <button onClick={() => saveEdit(r.id)} style={{ padding: '3px 10px', borderRadius: 5, border: 'none', background: '#dcfce7', color: '#16a34a', cursor: 'pointer', fontSize: 12, fontWeight: 600, marginRight: 6 }}>Save</button>
                              <button onClick={() => setEditing(prev => { const n = { ...prev }; delete n[r.id]; return n; })} style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid #e2e8f0', background: '#fff', color: '#64748b', cursor: 'pointer', fontSize: 12 }}>Cancel</button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => setEditing(prev => ({ ...prev, [r.id]: { action: r.action, category: r.category || '' } }))}
                                style={{ padding: '3px 10px', borderRadius: 5, border: '1px solid #cbd5e1', background: '#f8fafc', color: '#475569', cursor: 'pointer', fontSize: 12, marginRight: 6 }}
                              >Edit</button>
                              <button
                                onClick={() => deleteRule(r.id)}
                                style={{ padding: '3px 7px', borderRadius: 5, border: '1px solid #fecaca', background: '#fff5f5', color: '#dc2626', cursor: 'pointer', fontSize: 12 }}
                              >✕</button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Keywords Panel ─────────────────────────────────────────────────────── */

const SOURCE_BADGE = {
  default: { label: 'default', bg: '#e2e8f0', color: '#475569' },
  user:    { label: 'user',    bg: '#dbeafe', color: '#1d4ed8' },
  learned: { label: 'learned', bg: '#d1fae5', color: '#065f46' },
};

const KW_GROUPS = [
  {
    key:      'investment',
    label:    '📈 Investment Platform',
    apiPost:  '/api/investment-keywords',
    apiDel:   (kw) => `/api/investment-keywords/${encodeURIComponent(kw)}`,
    hint:     'Merchants matching these keywords are treated as investment platforms (e.g. fidelity, vanguard).',
  },
  {
    key:      'income',
    label:    '💰 Income',
    apiPost:  '/api/income-keywords',
    apiDel:   (kw) => `/api/income-keywords/${encodeURIComponent(kw)}`,
    hint:     'Transaction descriptions matching these keywords are classified as income.',
  },
  {
    key:      'ignore',
    label:    '🚫 Ignore',
    apiPost:  '/api/ignore-keywords',
    apiDel:   (kw) => `/api/ignore-keywords/${encodeURIComponent(kw)}`,
    hint:     'Transactions matching these keywords are silently dropped during import.',
  },
  {
    key:      'payment_app',
    label:    '📱 Payment Apps',
    apiPost:  '/api/payment-app-keywords',
    apiDel:   (kw) => `/api/payment-app-keywords/${encodeURIComponent(kw)}`,
    hint:     'Peer-to-peer app identifiers (Venmo, Zelle, etc.). Static — not auto-learned.',
  },
  {
    key:      'transfer',
    label:    '🔄 Transfer',
    apiPost:  '/api/transfer-keywords',
    apiDel:   (kw) => `/api/transfer-keywords/${encodeURIComponent(kw)}`,
    hint:     'Raw bank text patterns for inter-account transfers. Static — not auto-learned.',
  },
];

function KeywordsPanel() {
  const [allKw, setAllKw]       = useState({});
  const [loading, setLoading]   = useState(true);
  const [addInput, setAddInput] = useState({});
  const [addErr, setAddErr]     = useState({});
  const [delErr, setDelErr]     = useState({});
  const [expanded, setExpanded] = useState({ investment: true, income: true });

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/all-keywords`)
      .then(r => r.json())
      .then(d => { setAllKw(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (key) => setExpanded(e => ({ ...e, [key]: !e[key] }));

  const handleAdd = async (group) => {
    const kw = (addInput[group.key] || '').trim().toLowerCase();
    if (!kw) return;
    setAddErr(e => ({ ...e, [group.key]: '' }));
    const res = await fetch(`${API}${group.apiPost}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: kw }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      setAddErr(e => ({ ...e, [group.key]: d.error || 'Failed to add' }));
      return;
    }
    setAddInput(i => ({ ...i, [group.key]: '' }));
    load();
  };

  const handleDelete = async (group, kw) => {
    setDelErr(e => ({ ...e, [`${group.key}:${kw}`]: '' }));
    const res = await fetch(`${API}${group.apiDel(kw)}`, { method: 'DELETE' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      setDelErr(e => ({ ...e, [`${group.key}:${kw}`]: d.error || 'Cannot delete' }));
      return;
    }
    load();
  };

  if (loading) return <div style={{ padding: 32, color: '#64748b' }}>Loading keywords…</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>
        Keywords drive automatic classification during statement import.{' '}
        <strong>Default</strong> seeds are always present and cannot be deleted.{' '}
        <strong>User</strong> entries are added manually here.{' '}
        <strong>Learned</strong> entries are discovered automatically from your corrections.
      </p>
      {KW_GROUPS.map(group => {
        const rows = allKw[group.key] || [];
        const isOpen = expanded[group.key] !== false;
        const learnedCount = rows.filter(r => r.source === 'learned').length;
        return (
          <div key={group.key} style={{ border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
            <div
              onClick={() => toggle(group.key)}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                       padding: '12px 18px', background: '#f8fafc', cursor: 'pointer',
                       borderBottom: isOpen ? '1px solid #e2e8f0' : 'none' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>{group.label}</span>
                <span style={{ fontSize: 12, color: '#94a3b8' }}>
                  {rows.length} keyword{rows.length !== 1 ? 's' : ''}
                </span>
                {learnedCount > 0 && (
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '1px 7px', borderRadius: 4,
                                 background: SOURCE_BADGE.learned.bg, color: SOURCE_BADGE.learned.color }}>
                    {learnedCount} learned
                  </span>
                )}
              </div>
              <span style={{ color: '#94a3b8', fontSize: 13 }}>{isOpen ? '▲' : '▼'}</span>
            </div>

            {isOpen && (
              <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>{group.hint}</p>

                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    value={addInput[group.key] || ''}
                    onChange={e => setAddInput(i => ({ ...i, [group.key]: e.target.value }))}
                    onKeyDown={e => e.key === 'Enter' && handleAdd(group)}
                    placeholder="Add keyword…"
                    style={{ flex: 1, padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6,
                             fontSize: 13, outline: 'none' }}
                  />
                  <button
                    onClick={() => handleAdd(group)}
                    style={{ padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                             background: '#4f46e5', color: '#fff', fontWeight: 600, fontSize: 13 }}
                  >Add</button>
                </div>
                {addErr[group.key] && (
                  <div style={{ color: '#dc2626', fontSize: 12 }}>⚠ {addErr[group.key]}</div>
                )}

                {rows.length === 0 ? (
                  <div style={{ color: '#94a3b8', fontSize: 13, fontStyle: 'italic' }}>No keywords yet.</div>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {rows.map(({ keyword, source }) => {
                      const badge = SOURCE_BADGE[source] || SOURCE_BADGE.default;
                      const errKey = `${group.key}:${keyword}`;
                      const canDelete = source !== 'default';
                      return (
                        <div key={keyword} style={{ display: 'flex', alignItems: 'center', gap: 4,
                               padding: '4px 8px 4px 10px', borderRadius: 20,
                               background: canDelete ? '#fff' : '#f1f5f9',
                               border: `1px solid ${canDelete ? '#e2e8f0' : '#d1d5db'}`,
                               fontSize: 13, color: '#1e293b' }}>
                          <span>{keyword}</span>
                          <span style={{ padding: '1px 5px', borderRadius: 3, fontSize: 10,
                                         fontWeight: 700, letterSpacing: '0.02em',
                                         background: badge.bg, color: badge.color }}>
                            {badge.label}
                          </span>
                          {canDelete ? (
                            <button
                              title={delErr[errKey] || 'Remove'}
                              onClick={() => handleDelete(group, keyword)}
                              style={{ marginLeft: 2, background: 'none', border: 'none', cursor: 'pointer',
                                       color: delErr[errKey] ? '#dc2626' : '#94a3b8', fontSize: 14,
                                       lineHeight: 1, padding: '0 2px' }}
                            >✕</button>
                          ) : (
                            <span title="Default keywords cannot be deleted"
                                  style={{ marginLeft: 2, color: '#d1d5db', fontSize: 14 }}>🔒</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
/* ── Categories Panel ───────────────────────────────────────────────────── */
function CategoriesPanel({ onSaved }) {
  const [categories, setCategories] = useState([]);
  const [subcategories, setSubcategories] = useState({});   // parent → [children]
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [newCat, setNewCat] = useState('');
  // For subcategory assignment: which parent is being edited
  const [editingSubFor, setEditingSubFor] = useState(null);
  // For drag-and-drop reordering
  const [draggedCat, setDraggedCat] = useState(null);
  const [dragOverCat, setDragOverCat] = useState(null);

  const load = () => {
    setLoading(true);
    fetch(`${API}/api/categories/full`)
      .then(r => r.json())
      .then(d => {
        setCategories(d.categories || []);
        setSubcategories(d.subcategories || {});
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const addCategory = () => {
    const name = newCat.trim();
    if (!name || categories.includes(name)) return;
    setCategories(prev => [...prev, name]);
    setNewCat('');
  };

  const removeCategory = (cat) => {
    setCategories(prev => prev.filter(c => c !== cat));
    // Remove from subcategories as parent or child
    setSubcategories(prev => {
      const next = { ...prev };
      delete next[cat];
      for (const [parent, children] of Object.entries(next)) {
        next[parent] = children.filter(c => c !== cat);
        if (next[parent].length === 0) delete next[parent];
      }
      return next;
    });
  };

  const moveCategory = (cat, direction) => {
    setCategories(prev => {
      const idx = prev.indexOf(cat);
      if (idx === -1) return prev;
      const next = [...prev];
      const target = direction === 'up' ? idx - 1 : idx + 1;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const reorderByHierarchy = (cats, subs) => {
    const childSet = new Set(Object.values(subs).flat());
    const result = [];
    for (const cat of cats) {
      if (childSet.has(cat)) continue;
      result.push(cat);
      if (subs[cat]) {
        for (const child of subs[cat]) {
          if (cats.includes(child)) result.push(child);
        }
      }
    }
    for (const cat of cats) {
      if (!result.includes(cat)) result.push(cat);
    }
    return result;
  };

  const handleDrop = (targetCat) => {
    if (!draggedCat || draggedCat === targetCat) return;
    setCategories(prev => {
      const next = [...prev];
      const fromIdx = next.indexOf(draggedCat);
      if (fromIdx === -1) return prev;
      next.splice(fromIdx, 1);
      const toIdx = next.indexOf(targetCat);
      if (toIdx === -1) return prev;
      next.splice(toIdx, 0, draggedCat);
      return reorderByHierarchy(next, subcategories);
    });
    setDraggedCat(null);
    setDragOverCat(null);
  };

  const toggleSubcategory = (parent, child) => {
    const next = { ...subcategories };
    // First remove child from any existing parent
    for (const [p, children] of Object.entries(next)) {
      if (children.includes(child) && p !== parent) {
        next[p] = children.filter(c => c !== child);
        if (next[p].length === 0) delete next[p];
      }
    }
    // Toggle under target parent
    const existing = next[parent] || [];
    if (existing.includes(child)) {
      const filtered = existing.filter(c => c !== child);
      if (filtered.length === 0) delete next[parent];
      else next[parent] = filtered;
    } else {
      next[parent] = [...existing, child];
    }
    setSubcategories(next);
    setCategories(prev => reorderByHierarchy(prev, next));
  };

  // Build reverse map: child → parent
  const childToParent = {};
  for (const [parent, children] of Object.entries(subcategories)) {
    for (const child of children) childToParent[child] = parent;
  }

  const save = async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      const res = await fetch(`${API}/api/categories`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categories, subcategories }),
      });
      if (!res.ok) {
        const err = await res.json();
        setSaveMsg('❌ ' + (err.error || 'Save failed'));
      } else {
        setSaveMsg('✅ Saved! Changes will apply to new transactions from this point forward.');
        if (onSaved) onSaved();
      }
    } catch (e) {
      setSaveMsg('❌ ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>Loading…</div>;

  return (
    <div>
      {/* Info banner */}
      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '12px 16px', marginBottom: 20, fontSize: 13, color: '#1e40af' }}>
        <strong>💡 How this works:</strong> Changes saved here are stored in the database.
        New transactions will be classified using the updated list. <strong>Historical months are not affected</strong> —
        transactions already in the database keep their existing categories.
        The dashboard dropdowns and budget goal table update immediately after saving.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* ── Left: Category list ── */}
        <div>
          <h4 style={{ margin: '0 0 12px', fontSize: 14, color: '#334155' }}>📋 Categories ({categories.length})</h4>
          <div style={{ marginBottom: 10, display: 'flex', gap: 8 }}>
            <input
              value={newCat}
              onChange={e => setNewCat(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addCategory()}
              placeholder="Add new category…"
              style={{ flex: 1, padding: '7px 10px', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 13 }}
            />
            <button
              onClick={addCategory}
              disabled={!newCat.trim() || categories.includes(newCat.trim())}
              style={{ padding: '7px 14px', background: '#4f46e5', color: 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: !newCat.trim() || categories.includes(newCat.trim()) ? 0.5 : 1 }}
            >+ Add</button>
          </div>
          <div style={{ maxHeight: 460, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 8 }}>
            {categories.map((cat, idx) => {
              const isParent = cat in subcategories;
              const isChild = cat in childToParent;
              return (
                <div
                  key={cat}
                  draggable={!isChild}
                  onDragStart={!isChild ? () => setDraggedCat(cat) : undefined}
                  onDragOver={e => { e.preventDefault(); setDragOverCat(cat); }}
                  onDrop={e => { e.preventDefault(); handleDrop(cat); }}
                  onDragEnd={() => { setDraggedCat(null); setDragOverCat(null); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                    borderBottom: idx < categories.length - 1 ? '1px solid #f0f4f8' : 'none',
                    background: dragOverCat === cat && draggedCat !== cat ? '#e0e7ff' : (isParent ? '#f8faff' : isChild ? '#f8fff8' : 'white'),
                    opacity: draggedCat === cat ? 0.5 : 1,
                    transition: 'background 0.1s',
                  }}
                >
                  {isChild ? (
                    <span style={{ width: 20, display: 'inline-block' }} />
                  ) : (
                    <span
                      title="Drag to reorder"
                      style={{ color: '#cbd5e1', fontSize: 18, lineHeight: 1, padding: '0 2px', cursor: draggedCat === cat ? 'grabbing' : 'grab', userSelect: 'none' }}
                    >⠿</span>
                  )}
                  <span style={{ flex: 1, fontSize: 13, fontWeight: isParent ? 700 : 400, color: isChild ? '#475569' : '#0f172a' }}>
                    {isChild && <span style={{ color: '#94a3b8', marginRight: 6 }}>↳</span>}
                    {cat}
                    {isParent && <span style={{ fontSize: 10, color: '#6366f1', marginLeft: 6 }}>parent ({subcategories[cat].length})</span>}
                    {isChild && <span style={{ fontSize: 10, color: '#22c55e', marginLeft: 6 }}>↑ {childToParent[cat]}</span>}
                  </span>
                  <button
                    onClick={() => setEditingSubFor(editingSubFor === cat ? null : cat)}
                    title="Manage subcategory relationships"
                    style={{ padding: '3px 8px', background: editingSubFor === cat ? '#4f46e5' : '#f1f5f9', color: editingSubFor === cat ? 'white' : '#475569', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 11, cursor: 'pointer' }}
                  >⋮ Sub</button>
                  <button
                    onClick={() => removeCategory(cat)}
                    title={`Remove "${cat}" from categories`}
                    style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: '0 4px' }}
                  >✕</button>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Right: Subcategory hierarchy + editing ── */}
        <div>
          <h4 style={{ margin: '0 0 12px', fontSize: 14, color: '#334155' }}>🌿 Subcategory Hierarchy</h4>
          {editingSubFor ? (
            <div style={{ border: '1px solid #c7d2fe', borderRadius: 8, padding: 14, background: '#f5f3ff' }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: '#4f46e5', marginBottom: 10 }}>
                Set parent for: <strong>{editingSubFor}</strong>
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
                Click a category to assign it as the parent. Click the current parent to remove the relationship.
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {categories.filter(c => c !== editingSubFor && !(c in childToParent)).map(c => {
                  const isCurrentParent = childToParent[editingSubFor] === c;
                  const wouldBeChild = editingSubFor in subcategories && subcategories[editingSubFor].length > 0;
                  if (wouldBeChild) return null; // parents can't become children
                  return (
                    <button
                      key={c}
                      onClick={() => toggleSubcategory(c, editingSubFor)}
                      style={{
                        padding: '4px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                        background: isCurrentParent ? '#4f46e5' : '#f1f5f9',
                        color: isCurrentParent ? 'white' : '#334155',
                        border: `1px solid ${isCurrentParent ? '#4f46e5' : '#e2e8f0'}`,
                        fontWeight: isCurrentParent ? 700 : 400,
                      }}
                    >{isCurrentParent ? '✓ ' : ''}{c}</button>
                  );
                })}
              </div>
              {editingSubFor in subcategories && subcategories[editingSubFor].length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: '#dc2626' }}>⚠️ This category has its own children — remove them first before making it a child.</div>
              )}
              <button onClick={() => setEditingSubFor(null)} style={{ marginTop: 10, padding: '4px 10px', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12, cursor: 'pointer' }}>Done</button>
            </div>
          ) : (
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
              {Object.keys(subcategories).length === 0 ? (
                <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                  No subcategory relationships defined.<br />
                  <span style={{ fontSize: 12 }}>Click "⋮ Sub" next to a category to assign it under a parent.</span>
                </div>
              ) : (
                Object.entries(subcategories).map(([parent, children], i) => (
                  <div key={parent} style={{ padding: '10px 14px', borderBottom: i < Object.keys(subcategories).length - 1 ? '1px solid #f0f4f8' : 'none', background: 'white' }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: '#334155', marginBottom: 4 }}>📁 {parent}</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, paddingLeft: 12 }}>
                      {children.map(child => (
                        <span key={child} style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 12, padding: '2px 10px', fontSize: 12, color: '#1e40af' }}>↳ {child}</span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Save button */}
          <div style={{ marginTop: 20 }}>
            <button
              onClick={save}
              disabled={saving}
              style={{ padding: '9px 20px', background: '#4f46e5', color: 'white', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 700, cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.7 : 1 }}
            >{saving ? '⏳ Saving…' : '💾 Save Categories'}</button>
            {saveMsg && <span style={{ marginLeft: 12, fontSize: 12, color: saveMsg.startsWith('✅') ? '#16a34a' : '#dc2626' }}>{saveMsg}</span>}
          </div>

          {/* Warning */}
          <div style={{ marginTop: 14, background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#92400e' }}>
            ⚠️ Removing a category does not delete historical transactions that used it. Those transactions will retain their existing category label in the database.
          </div>
        </div>
      </div>
    </div>
  );
}
