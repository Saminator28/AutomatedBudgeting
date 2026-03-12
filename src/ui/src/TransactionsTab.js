import React, { useEffect, useState, useRef, useCallback } from 'react';

const API = 'http://localhost:8000';

const cellInput = {
  padding: '3px 7px', border: '1px solid #4f46e5', borderRadius: 4,
  fontSize: 13, outline: 'none', width: '100%', boxSizing: 'border-box',
};

// ─── Inline-editable text cell ──────────────────────────────────────────────
function EditableCell({ value, onSave, style = {} }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef();
  useEffect(() => { if (editing) ref.current?.select(); }, [editing]);

  const commit = () => {
    setEditing(false);
    if (draft.trim() && draft.trim() !== value) onSave(draft.trim());
    else setDraft(value);
  };

  return editing ? (
    <input
      ref={ref}
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setEditing(false); setDraft(value); } }}
      style={{ ...cellInput, ...style }}
    />
  ) : (
    <span
      onClick={() => { setDraft(value); setEditing(true); }}
      title="Click to edit"
      style={{ cursor: 'text', borderBottom: '1px dashed #cbd5e1', paddingBottom: 1, ...style }}
    >
      {value || <span style={{ color: '#94a3b8' }}>—</span>}
    </span>
  );
}

// ─── Inline-editable amount cell ───────────────────────────────────────────
function EditableAmountCell({ value, formatCurrency, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const ref = useRef();
  useEffect(() => { if (editing) ref.current?.select(); }, [editing]);

  const commit = () => {
    setEditing(false);
    const parsed = parseFloat(draft);
    if (!isNaN(parsed) && Math.abs(parsed - value) > 0.001) onSave(parsed);
    else setDraft(String(value));
  };

  return editing ? (
    <input
      ref={ref}
      type="number"
      min="0"
      step="0.01"
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setEditing(false); setDraft(String(value)); } }}
      style={{ ...cellInput, textAlign: 'right', width: 90 }}
    />
  ) : (
    <span
      onClick={() => { setDraft(String(value)); setEditing(true); }}
      title="Click to edit amount"
      style={{ cursor: 'text', borderBottom: '1px dashed #cbd5e1', paddingBottom: 1 }}
    >
      {formatCurrency(value)}
    </span>
  );
}

// ─── Inline-editable category select cell ───────────────────────────────────
function EditableCategoryCell({ value, categories, onSave }) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <select
        autoFocus
        value={value}
        onChange={e => { onSave(e.target.value); setEditing(false); }}
        onBlur={() => setEditing(false)}
        style={{ ...cellInput, background: '#fff' }}
      >
        {categories.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    );
  }
  return (
    <span
      onClick={() => setEditing(true)}
      title="Click to change category"
      style={{ cursor: 'pointer', borderBottom: '1px dashed #cbd5e1', paddingBottom: 1 }}
    >
      {value || <span style={{ color: '#e85d04' }}>Uncategorized</span>}
    </span>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function TransactionsTab({ formatCurrency, categories, selectedMonth, onRefreshData }) {
  const [subTab, setSubTab] = useState('expenses');

  // ── Add form state ─────────────────────────────────────────────────────────
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    place: '', amount: '', type: 'expense', category: '', label: 'recurring',
  });
  const [addedTxs, setAddedTxs] = useState([]);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState('');
  const [addSuccess, setAddSuccess] = useState('');

  // ── All Transactions state ─────────────────────────────────────────────────
  const [expenses, setExpenses] = useState([]);
  const [income, setIncome] = useState([]);
  const [reviewData, setReviewData] = useState([]);          // unclassified payment-app txs
  const [inlineReviewEdits, setInlineReviewEdits] = useState({}); // {key: {classification,category}}
  const [inlineReviewSaving, setInlineReviewSaving] = useState({});
  const [expLoading, setExpLoading] = useState(false);
  const [expError, setExpError] = useState('');
  const [search, setSearch] = useState('');
  const [filterMonth, setFilterMonth] = useState(selectedMonth || '');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [sortCol, setSortCol] = useState('date');
  const [sortDir, setSortDir] = useState('asc');
  const [savingRow, setSavingRow] = useState(null);
  const [availableExpMonths, setAvailableExpMonths] = useState([]);


  // ── Fetch manual txs (Add sub-tab) ────────────────────────────────────────
  useEffect(() => {
    if (subTab !== 'add') return;
    fetch(`${API}/api/manual-transactions`)
      .then(r => r.json())
      .then(d => setAddedTxs(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [subTab]);

  // Sync filterMonth when the global selected month changes
  useEffect(() => {
    if (selectedMonth) setFilterMonth(selectedMonth);
  }, [selectedMonth]);

  // ── Fetch available month list (for the dropdown) ────────────────────────────
  useEffect(() => {
    if (subTab !== 'expenses') return;
    fetch(`${API}/api/available-months`)
      .then(r => r.json())
      .then(d => {
        const months = Array.isArray(d) ? d : [];
        setAvailableExpMonths(months);
        // Auto-select the latest available month if current selection isn't in the list
        if (months.length > 0 && !months.includes(filterMonth)) {
          setFilterMonth(months[0]);
        }
      })
      .catch(() => {});
  }, [subTab]);

  // ── Fetch income (All Transactions sub-tab) ───────────────────────────────
  useEffect(() => {
    if (subTab !== 'expenses') return;
    const monthParam = filterMonth ? `?month=${filterMonth}` : '';
    fetch(`${API}/api/income-entries${monthParam}`)
      .then(r => r.json())
      .then(d => setIncome(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [subTab, filterMonth]);

  // ── Fetch all expenses ────────────────────────────────────────────────────────
  useEffect(() => {
    if (subTab !== 'expenses') return;
    setExpLoading(true);
    setExpError('');
    // Only fetch the selected month to keep the response fast
    const monthParam = filterMonth ? `?month=${filterMonth}` : '';
    fetch(`${API}/api/all-expenses${monthParam}`)
      .then(r => r.json())
      .then(d => { setExpenses(Array.isArray(d) ? d : []); setExpLoading(false); })
      .catch(e => { setExpError(e.message); setExpLoading(false); });
  }, [subTab, filterMonth]);

  // ── Fetch review items (unclassified, shown inline in All Transactions) ───
  useEffect(() => {
    if (subTab !== 'expenses') return;
    fetch(`${API}/api/manual-review`)
      .then(r => r.json())
      .then(d => setReviewData(Array.isArray(d) ? d.map((r, i) => ({ ...r, _id: i })) : []))
      .catch(() => {});
  }, [subTab]);



  // ── Derived: filtered + sorted transactions (expenses + income + unclassified) ────
  const allRows = [
    ...expenses.map(e => ({ ...e, _type: 'expense' })),
    ...income.map(i => ({ ...i, _type: 'income' })),
    ...reviewData
      .filter(r => !filterMonth || r.month === filterMonth)
      .map(r => ({ ...r, _type: 'review' })),
  ];

  const filtered = allRows.filter(e => {
    if (filterType === 'unclassified') { if (e._type !== 'review') return false; }
    else if (filterType === 'reimbursement') { if (!(e._type === 'expense' && e.amount < 0)) return false; }
    else if (filterType === 'expense') { if (!(e._type === 'expense' && e.amount >= 0)) return false; }
    else if (filterType === 'income') { if (e._type !== 'income') return false; }
    if (filterCategory && e.category !== filterCategory) return false;
    if (search && !e.place.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const filteredWithSearch = filtered; // alias for row count display

  const sorted = [...filteredWithSearch].sort((a, b) => {
    let av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
    if (sortCol === 'amount') { av = a.amount; bv = b.amount; }
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const toggleSort = col => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const sortIcon = col => sortCol === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

  // ── Inline classify a review row from All Transactions ──────────────────────
  const inlineClassify = useCallback(async (row, classification, category) => {
    const key = `review_${row._id}`;
    // Don't save yet if expense/reimbursement and no category
    if ((classification === 'Expense' || classification === 'Reimbursement') && !category) {
      setInlineReviewEdits(prev => ({ ...prev, [key]: { classification, category: '' } }));
      return;
    }
    setInlineReviewSaving(s => ({ ...s, [key]: true }));
    try {
      const res = await fetch(`${API}/api/manual-review/classify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          month: row.month,
          date: row.date,
          original_place: row.place_original || row.place,
          amount: row.amount,
          classification,
          category: category || '',
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed');
      // Remove from review data and refresh expenses/income
      setReviewData(prev => prev.filter(r => r._id !== row._id));
      setInlineReviewEdits(prev => { const n = { ...prev }; delete n[key]; return n; });
      // Refresh expenses and income for the affected month
      const mParam = `?month=${row.month}`;
      fetch(`${API}/api/all-expenses${mParam}`).then(r => r.json()).then(d => setExpenses(prev => {
        const otherMonths = prev.filter(e => e.month !== row.month);
        return [...otherMonths, ...(Array.isArray(d) ? d : [])];
      }));
      fetch(`${API}/api/income-entries${mParam}`).then(r => r.json()).then(d => setIncome(prev => {
        const otherMonths = prev.filter(e => e.month !== row.month);
        return [...otherMonths, ...(Array.isArray(d) ? d : [])];
      }));
    } catch (err) {
      alert('Classify failed: ' + err.message);
    } finally {
      setInlineReviewSaving(s => ({ ...s, [key]: false }));
    }
  }, []);

  // ── Change label on an income row ────────────────────────────────────────
  const editIncomeLabelFn = useCallback(async (row, newLabel) => {
    if (newLabel === 'reimbursement') {
      try {
        const res = await fetch(`${API}/api/income/reclassify-as-reimbursement`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ date: row.date, place: row.place, amount: row.amount, month: row.month }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed');
        setIncome(prev => prev.filter(r => !(r.date === row.date && r.place === row.place && r.amount === row.amount && r.month === row.month)));
        setExpenses(prev => [...prev, { ...row, _type: 'expense', amount: -Math.abs(row.amount), label: 'reimbursement', category: '' }]);
      } catch (err) {
        alert('Reclassify failed: ' + err.message);
      }
      return;
    }
    try {
      await fetch(`${API}/api/income/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: row.date, place: row.place, amount: row.amount, month: row.month, label: newLabel }),
      });
      setIncome(prev => prev.map(r =>
        r.date === row.date && r.place === row.place && r.amount === row.amount && r.month === row.month
          ? { ...r, label: newLabel } : r
      ));
    } catch (err) {
      alert('Label save failed: ' + err.message);
    }
  }, []);

  // ── Edit an expense row ───────────────────────────────────────────────────
  const editExpense = useCallback(async (row, patch) => {
    const key = `${row.date}|${row.place}|${row.amount}|${row.month}`;
    setSavingRow(key);
    try {
      const res = await fetch(`${API}/api/expense/edit`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: row.date, original_place: row.place, amount: row.amount, month: row.month, row_idx: row.row_idx, ...patch }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed');
      // Update local state; match by stable row_idx when available
      setExpenses(prev => prev.map(e => {
        const match = row.row_idx != null
          ? (e.row_idx === row.row_idx && e.month === row.month)
          : (e.date === row.date && e.place === row.place && e.amount === row.amount && e.month === row.month);
        if (!match) return e;
        return {
          ...e,
          ...(patch.new_place    ? { place:    patch.new_place    } : {}),
          ...(patch.new_category ? { category: patch.new_category } : {}),
          ...(patch.new_label    ? { label:    patch.new_label    } : {}),
          ...(patch.new_amount != null ? { amount: patch.new_amount } : {}),
        };
      }));
    } catch (err) {
      alert('Save failed: ' + err.message);
    } finally {
      setSavingRow(null);
    }
  }, []);

  // ── Cycle transaction type by clicking the badge ──────────────────────────
  const changeTypeFn = useCallback(async (row) => {
    const rowIsIncome = row._type === 'income' && row.label !== 'reimbursement';
    const rowIsReimb  = (row._type === 'expense' && row.amount < 0) ||
                        (row._type === 'income'  && row.label === 'reimbursement');

    if (rowIsIncome) {
      // income → reimbursement (moves row to expenses CSV, label=reimbursement)
      await editIncomeLabelFn(row, 'reimbursement');
    } else if (rowIsReimb) {
      if (row._type === 'income') {
        // reimb (income row with label=reimbursement) → back to regular income
        await editIncomeLabelFn(row, 'recurring');
      } else {
        // reimb (negative expense) → expense (flip amount positive, clear reimbursement label)
        await editExpense(row, { new_label: 'recurring', new_amount: Math.abs(row.amount) });
      }
    } else {
      // expense → income (moves row to income CSV)
      try {
        const res = await fetch(`${API}/api/expense/reclassify-as-income`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ date: row.date, place: row.place, amount: row.amount, month: row.month }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed');
        setExpenses(prev => prev.filter(e =>
          !(e.date === row.date && e.place === row.place && e.amount === row.amount && e.month === row.month)
        ));
        setIncome(prev => [...prev, { ...row, _type: 'income', amount: Math.abs(row.amount), label: 'recurring', category: '' }]);
      } catch (err) {
        alert('Reclassify failed: ' + err.message);
      }
    }
  }, [editIncomeLabelFn, editExpense]);



  // ── Shared styles ─────────────────────────────────────────────────────────
  const card = { background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)', border: '1px solid #e2e8f0', padding: '22px 26px', marginBottom: 22 };
  const th = { padding: '9px 11px', textAlign: 'left', fontWeight: 700, color: '#475569', fontSize: 12, borderBottom: '2px solid #e2e8f0', cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none' };
  const td = { padding: '8px 11px', borderBottom: '1px solid #f1f5f9', fontSize: 13 };

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto', padding: '28px 32px' }}>

      {/* Sub-tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: '#f1f5f9', borderRadius: 10, padding: 4, width: 'fit-content' }}>
        {[
          { key: 'expenses', label: '📋 All Transactions' },
          { key: 'add',      label: '➕ Add Transaction' },
        ].map(t => (
          <button key={t.key} onClick={() => setSubTab(t.key)} style={{
            padding: '8px 18px', border: 'none', borderRadius: 8, fontWeight: 600, fontSize: 13,
            cursor: 'pointer', transition: 'all .15s',
            background: subTab === t.key ? '#4f46e5' : 'transparent',
            color: subTab === t.key ? '#fff' : '#64748b',
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ─── ADD TRANSACTION ─────────────────────────────────────────────── */}
      {subTab === 'add' && (
        <>
          <div style={card}>
            <h3 style={{ margin: '0 0 16px', color: '#0f172a', fontWeight: 700, fontSize: 16 }}>➕ Add Transaction</h3>
            {addError   && <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 7, padding: '9px 13px', marginBottom: 12, color: '#dc2626', fontSize: 13 }}>{addError}</div>}
            {addSuccess && <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 7, padding: '9px 13px', marginBottom: 12, color: '#16a34a', fontSize: 13 }}>{addSuccess}</div>}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 14 }}>
              {/* Date */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '.04em' }}>Date</div>
                <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              {/* Type */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '.04em' }}>Type</div>
                <select value={form.type}
                  onChange={e => setForm(f => ({ ...f, type: e.target.value, label: 'recurring' }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 14, boxSizing: 'border-box', background: '#fff' }}>
                  <option value="expense">💸 Expense</option>
                  <option value="income">💵 Income</option>
                  <option value="reimbursement">↩️ Reimbursement</option>
                </select>
              </div>
              {/* Category (expense or reimbursement) */}
              {(form.type === 'expense' || form.type === 'reimbursement') && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '.04em' }}>Category</div>
                  <select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 14, boxSizing: 'border-box', background: '#fff' }}>
                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              )}
              {/* Merchant */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '.04em' }}>Merchant / Description</div>
                <input type="text" placeholder="e.g. Merchant Name, Paycheck" value={form.place}
                  onChange={e => setForm(f => ({ ...f, place: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              {/* Amount */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '.04em' }}>Amount ($)</div>
                <input type="number" min="0" step="0.01" placeholder="0.00" value={form.amount}
                  onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              {/* Label */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '.04em' }}>Label</div>
                <select value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 14, boxSizing: 'border-box', background: '#fff' }}>
                  {form.type === 'income'
                    ? <><option value="recurring">✅ Regular</option><option value="bonus">⭐ Bonus</option></>
                    : <><option value="recurring">📌 Normal</option><option value="one-time">⚡ One-Time</option></>}
                </select>
              </div>
            </div>
            <div style={{ marginTop: 18 }}>
              <button disabled={addLoading || !form.date || !form.place.trim() || !form.amount}
                onClick={async () => {
                  setAddLoading(true); setAddError(''); setAddSuccess('');
                  try {
                    const res = await fetch(`${API}/api/manual-transactions`, {
                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ ...form, amount: parseFloat(form.amount) }),
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || 'Failed');
                    setAddedTxs(prev => [data.transaction, ...prev]);
                    setForm(f => ({ ...f, place: '', amount: '' }));
                    const typeLabel = form.type === 'reimbursement' ? 'reimbursement' : form.type;
                    setAddSuccess(`✅ Added ${typeLabel}: ${data.transaction.place} ${formatCurrency(data.transaction.amount)} — included in ${data.transaction.month}.`);
                    if (onRefreshData) onRefreshData();
                  } catch (err) { setAddError(err.message); }
                  finally { setAddLoading(false); }
                }}
                style={{ background: addLoading ? '#94a3b8' : '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 26px', fontSize: 14, fontWeight: 700, cursor: addLoading ? 'not-allowed' : 'pointer' }}>
                {addLoading ? 'Saving…' : '➕ Add Transaction'}
              </button>
            </div>
          </div>

          {/* Manual transactions history */}
          <div style={card}>
            <h3 style={{ margin: '0 0 14px', color: '#0f172a', fontWeight: 700, fontSize: 15 }}>📋 Manually Added ({addedTxs.length})</h3>
            {addedTxs.length === 0
              ? <div style={{ textAlign: 'center', padding: 28, color: '#94a3b8' }}>No manual transactions yet.</div>
              : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        {['Date', 'Type', 'Merchant', 'Category', 'Amount', 'Label', ''].map(h => (
                          <th key={h} style={{ ...th, cursor: 'default' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[...addedTxs].sort((a, b) => b.date.localeCompare(a.date)).map(tx => (
                        <tr key={tx.id}>
                          <td style={td}>{tx.date}</td>
                          <td style={td}>
                            <span style={{
                              background: tx.type === 'income' ? '#dcfce7' : tx.type === 'reimbursement' ? '#ede9fe' : '#fee2e2',
                              color: tx.type === 'income' ? '#166534' : tx.type === 'reimbursement' ? '#5b21b6' : '#991b1b',
                              borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 700
                            }}>
                              {tx.type === 'income' ? '💵 Income' : tx.type === 'reimbursement' ? '↩️ Reimb.' : '💸 Expense'}
                            </span>
                          </td>
                          <td style={td}>{tx.place}</td>
                          <td style={{ ...td, color: tx.category ? '#374151' : '#94a3b8' }}>{tx.category || '—'}</td>
                          <td style={{ ...td, textAlign: 'right', fontWeight: 600 }}>{formatCurrency(tx.amount)}</td>
                          <td style={td}>
                            <span style={{ background: tx.label === 'bonus' ? '#fffbeb' : tx.label === 'one-time' ? '#fff7ed' : '#f0fdf4', color: tx.label === 'bonus' ? '#b45309' : tx.label === 'one-time' ? '#c2410c' : '#166534', borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 700 }}>
                              {tx.label === 'bonus' ? '⭐ Bonus' : tx.label === 'one-time' ? '⚡ One-Time' : tx.type === 'income' ? '✅ Regular' : '📌 Normal'}
                            </span>
                          </td>
                          <td style={td}>
                            <button onClick={async () => {
                              if (!window.confirm(`Delete "${tx.place}" ${formatCurrency(tx.amount)}?`)) return;
                              const res = await fetch(`${API}/api/manual-transactions/${tx.id}`, { method: 'DELETE' });
                              if (res.ok) { setAddedTxs(prev => prev.filter(t => t.id !== tx.id)); if (onRefreshData) onRefreshData(); }
                            }}
                              style={{ background: '#fef2f2', color: '#dc2626', border: '1px solid #fca5a5', borderRadius: 5, padding: '3px 9px', fontSize: 12, cursor: 'pointer', fontWeight: 700 }}>
                              🗑️
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
          </div>
        </>
      )}

      {/* ─── ALL TRANSACTIONS ────────────────────────────────────────────────────────── */}
      {subTab === 'expenses' && (
        <div style={card}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 18 }}>
            <div>
              <h3 style={{ margin: 0, color: '#0f172a', fontWeight: 700, fontSize: 16 }}>📋 All Transactions</h3>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: '#64748b' }}>
                Expenses and income in one view. Click any expense <strong>Merchant</strong>, <strong>Amount</strong>, or <strong>Category</strong> cell to edit inline.
              </p>
            </div>
            <span style={{ background: '#e0e7ff', color: '#4f46e5', borderRadius: 20, padding: '4px 14px', fontSize: 13, fontWeight: 700 }}>
              {filteredWithSearch.length} rows{filterType !== 'all' || filterMonth || filterCategory || search ? ` (filtered from ${allRows.length})` : ''}
            </span>
          </div>

          {expError && <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 7, padding: '9px 13px', marginBottom: 14, color: '#dc2626', fontSize: 13 }}>{expError}</div>}

          {/* Filter bar */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
            <input
              type="text" placeholder="🔍 Search merchant…" value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 13, minWidth: 200, flex: 1 }}
            />
            <select value={filterMonth} onChange={e => setFilterMonth(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 13, background: '#fff' }}>
              <option value="">All months</option>
              {(availableExpMonths.length ? availableExpMonths : [...new Set(allRows.map(e => e.month))].sort().reverse()).map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <select value={filterType} onChange={e => setFilterType(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 13, background: '#fff' }}>
              <option value="all">All types</option>
              <option value="expense">💸 Expenses only</option>
              <option value="income">💵 Income only</option>
              <option value="reimbursement">↩️ Reimbursements only</option>
              <option value="unclassified">❓ Unclassified only</option>
            </select>
            <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #cbd5e1', borderRadius: 7, fontSize: 13, background: '#fff' }}>
              <option value="">All categories</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            {(search || filterMonth || filterCategory || filterType !== 'all') && (
              <button onClick={() => { setSearch(''); setFilterMonth(''); setFilterCategory(''); setFilterType('all'); }}
                style={{ padding: '7px 14px', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 7, fontSize: 13, cursor: 'pointer', color: '#64748b' }}>
                ✕ Clear
              </button>
            )}
          </div>

          {expLoading
            ? <div style={{ textAlign: 'center', padding: 48, color: '#94a3b8' }}>Loading…</div>
            : (
              <div style={{ overflowX: 'auto', maxHeight: 620, overflowY: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
                  <thead style={{ position: 'sticky', top: 0, background: '#f8fafc', zIndex: 2 }}>
                    <tr>
                      <th onClick={() => toggleSort('date')} style={th}>Date{sortIcon('date')}</th>
                      <th style={{ ...th, cursor: 'default' }}>Type</th>
                      <th onClick={() => toggleSort('place')} style={th}>Merchant{sortIcon('place')}</th>
                      <th onClick={() => toggleSort('amount')} style={{ ...th, textAlign: 'right' }}>Amount{sortIcon('amount')}</th>
                      <th onClick={() => toggleSort('category')} style={th}>Category{sortIcon('category')}</th>
                      <th style={{ ...th, cursor: 'default' }}>Label</th>
                      <th style={{ ...th, cursor: 'default', color: '#94a3b8' }}>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((row, i) => {
                      const isIncome = row._type === 'income' && row.label !== 'reimbursement';
                      const isReimb  = (row._type === 'expense' && row.amount < 0) || (row._type === 'income' && row.label === 'reimbursement');
                      const isReview = row._type === 'review';
                      const reviewKey = `review_${row._id}`;
                      const rvEdit = inlineReviewEdits[reviewKey] || {};
                      const rvSaving = inlineReviewSaving[reviewKey];
                      const key = `${row._type}|${row.date}|${row.place}|${row.amount}|${row.month}`;
                      const saving = savingRow === `${row.date}|${row.place}|${row.amount}|${row.month}`;

                      if (isReview) {
                        return (
                          <tr key={i} style={{ opacity: rvSaving ? 0.5 : 1, background: '#fef2f2' }}>
                            <td style={{ ...td, whiteSpace: 'nowrap', color: '#64748b' }}>{row.date}</td>
                            <td style={td}>
                              <select
                                value={rvEdit.classification || ''}
                                onChange={e => {
                                  const cls = e.target.value;
                                  const newEdit = { ...rvEdit, classification: cls };
                                  setInlineReviewEdits(prev => ({ ...prev, [reviewKey]: newEdit }));
                                  if (cls === 'Income') inlineClassify(row, cls, '');
                                  else if ((cls === 'Expense' || cls === 'Reimbursement') && rvEdit.category)
                                    inlineClassify(row, cls, rvEdit.category);
                                }}
                                style={{ fontSize: 12, padding: '3px 7px', borderRadius: 5, border: '1px solid #fca5a5', background: '#fff', cursor: 'pointer', color: '#dc2626', fontWeight: 600 }}
                              >
                                <option value="">❓ Unclassified</option>
                                <option value="Expense">💸 Expense</option>
                                <option value="Income">💵 Income</option>
                                <option value="Reimbursement">↩️ Reimbursement</option>
                              </select>
                            </td>
                            <td style={{ ...td, minWidth: 160, color: '#374151' }}>{row.place}</td>
                            <td style={{ ...td, textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap', color: '#dc2626' }}>
                              {formatCurrency(row.amount)}
                            </td>
                            <td style={{ ...td, minWidth: 140 }}>
                              {(rvEdit.classification === 'Expense' || rvEdit.classification === 'Reimbursement') ? (
                                <select
                                  value={rvEdit.category || ''}
                                  onChange={e => {
                                    const cat = e.target.value;
                                    const newEdit = { ...rvEdit, category: cat };
                                    setInlineReviewEdits(prev => ({ ...prev, [reviewKey]: newEdit }));
                                    if (cat) inlineClassify(row, rvEdit.classification, cat);
                                  }}
                                  style={{ ...cellInput, background: '#fff', border: '1px solid #fca5a5' }}
                                >
                                  <option value="">— pick category —</option>
                                  {categories.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                              ) : (
                                <span style={{ color: '#94a3b8', fontSize: 12 }}>—</span>
                              )}
                            </td>
                            <td style={{ ...td, color: '#94a3b8', fontSize: 12 }}>—</td>
                            <td style={{ ...td, color: '#94a3b8', fontSize: 11 }}>{row.statement}</td>
                          </tr>
                        );
                      }

                      return (
                        <tr key={i} style={{ opacity: saving ? 0.5 : 1, background: isIncome ? '#f0fdf4' : isReimb ? '#f5f3ff' : undefined }}>
                          <td style={{ ...td, whiteSpace: 'nowrap', color: '#64748b' }}>{row.date}</td>
                          <td style={td}>
                            <span
                              onClick={() => changeTypeFn(row)}
                              title="Click to change type"
                              style={{
                                background: isIncome ? '#dcfce7' : isReimb ? '#ede9fe' : '#fee2e2',
                                color: isIncome ? '#166534' : isReimb ? '#5b21b6' : '#991b1b',
                                borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 700,
                                cursor: 'pointer', userSelect: 'none',
                              }}
                            >
                              {isIncome ? '💵 Income' : isReimb ? '↩️ Reimb.' : '💸 Expense'}
                            </span>
                          </td>
                          <td style={{ ...td, minWidth: 160 }}>
                            {isIncome
                              ? <span>{row.place}</span>
                              : <EditableCell value={row.place} onSave={v => editExpense(row, { new_place: v })} />}
                          </td>
                          <td style={{ ...td, textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap', color: (isIncome || isReimb) ? '#16a34a' : undefined }}>
                            {isIncome
                              ? formatCurrency(row.amount)
                              : isReimb
                                ? <EditableAmountCell value={Math.abs(row.amount)} formatCurrency={v => `+${formatCurrency(v)}`} onSave={v => editExpense(row, { new_amount: -Math.abs(v) })} />
                                : <EditableAmountCell value={row.amount} formatCurrency={formatCurrency} onSave={v => editExpense(row, { new_amount: v })} />}
                          </td>
                          <td style={{ ...td, minWidth: 140 }}>
                            {isIncome
                              ? <span style={{ color: '#94a3b8', fontSize: 12 }}>—</span>
                              : <EditableCategoryCell value={row.category} categories={categories} onSave={v => editExpense(row, { new_category: v })} />}
                          </td>
                          <td style={td}>
                            {isIncome ? (
                              <select
                                value={row.label || 'recurring'}
                                onChange={e => editIncomeLabelFn(row, e.target.value)}
                                style={{ fontSize: 12, padding: '3px 7px', borderRadius: 5, border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer' }}
                              >
                                <option value="recurring">✅ Regular</option>
                                <option value="bonus">⭐ Bonus</option>
                              </select>
                            ) : (
                              <select
                                value={row.label || 'recurring'}
                                onChange={e => editExpense(row, { new_label: e.target.value })}
                                style={{ fontSize: 12, padding: '3px 7px', borderRadius: 5, border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer' }}
                              >
                                <option value="recurring">📌 Normal</option>
                                <option value="one-time">⚡ One-Time</option>
                              </select>
                            )}
                          </td>
                          <td style={{ ...td, color: '#94a3b8', fontSize: 11 }}>{row.statement}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {sorted.length === 0 && (
                  <div style={{ textAlign: 'center', padding: 36, color: '#94a3b8' }}>No transactions match the current filters.</div>
                )}
              </div>
            )}

        </div>
      )}

    </div>
  );
}
