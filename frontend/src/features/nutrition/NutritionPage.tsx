import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Droplets, Package, Plus, Utensils, Wallet } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { api } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { applyServerErrors, FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { StatCard } from '@/components/StatCard';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { RecordList } from '@/features/health/Records';
import { formatDate } from '@/features/livestock/format';
import styles from '@/features/livestock/Livestock.module.css';
import { useSession } from '@/features/session/SessionContext';
import { useCursorList } from '@/features/users/api';
import { can } from '@/routes/permissions';

import { ASSESSMENTS, FEEDING, HYGIENE, SUPPLEMENTS } from './config';

interface FeedItem {
  id: string;
  name: string;
  category: string;
  unit: string;
  reorder_level: string;
  unit_cost_cents: number | null;
  stock_quantity: string;
  is_low: boolean;
  days_left: number | null;
  average_daily_use: string;
  notes: string;
}
interface Summary {
  feed_items: number;
  low_stock_items: number;
  feedings_today: number;
  feed_cost_this_month_cents: number;
  last_hygiene_score: number | null;
}
interface Movement {
  id: string;
  feed_item_name: string;
  unit: string;
  date: string;
  kind: string;
  quantity: string;
  total_cost_cents: number | null;
  supplier: string;
  notes: string;
  recorded_by: string | null;
}

const CATEGORIES = [
  ['forage', 'Forage / hay'],
  ['concentrate', 'Concentrate'],
  ['mineral', 'Mineral / lick'],
  ['supplement', 'Supplement'],
  ['other', 'Other'],
] as const;
const UNITS = ['kg', 'bale', 'bag', 'litre', 'block'];
const KIND_LABELS: Record<string, string> = {
  purchase: 'Stock in',
  usage: 'Fed',
  adjustment: 'Stock count',
  waste: 'Wasted',
};
const TABS = [
  ['stock', 'Feed stock'],
  ['feeding', 'Feeding'],
  ['assessments', 'Assessments'],
  ['supplements', 'Supplements'],
  ['hygiene', 'Water & hygiene'],
  ['history', 'Stock history'],
] as const;

function money(cents: number | null | undefined, currency: string) {
  if (cents === null || cents === undefined) return '—';
  return `${currency} ${(cents / 100).toLocaleString('en-KE', { maximumFractionDigits: 2 })}`;
}
const qty = (v: string | number) => Number(v).toLocaleString('en-KE', { maximumFractionDigits: 2 });

export default function NutritionPage() {
  const { activeFarm } = useSession();
  const currency = activeFarm?.farm.currency ?? 'KES';
  const summary = useQuery({
    queryKey: ['nutrition', 'summary'],
    queryFn: () => api<Summary>('/nutrition/summary'),
  });
  const s = summary.data;
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Nutrition &amp; feeding</h2>
          <p>Feed stock, daily feeding, body condition, supplements, and water and hygiene checks.</p>
        </div>
      </div>
      <div className={styles.stats}>
        <StatCard label="Feed items" value={s?.feed_items ?? '—'} icon={Package} />
        <StatCard label="Low stock" value={s?.low_stock_items ?? '—'} icon={AlertTriangle} />
        <StatCard label="Feedings today" value={s?.feedings_today ?? '—'} icon={Utensils} />
        <StatCard
          label="Feed bought this month"
          value={s ? money(s.feed_cost_this_month_cents, currency) : '—'}
          icon={Wallet}
        />
        <StatCard
          label="Last hygiene check"
          value={s?.last_hygiene_score === null || !s ? '—' : `${s.last_hygiene_score}/5`}
          icon={Droplets}
        />
      </div>
      <nav className={page.tabs} aria-label="Nutrition sections">
        {TABS.map(([k, l]) => (
          <NavLink key={k} to={`/nutrition/${k}`} className={page.tab}>
            {l}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="stock" replace />} />
        <Route path="stock" element={<FeedStock />} />
        <Route path="feeding" element={<RecordList type={FEEDING} />} />
        <Route path="assessments" element={<RecordList type={ASSESSMENTS} />} />
        <Route path="supplements" element={<RecordList type={SUPPLEMENTS} />} />
        <Route path="hygiene" element={<RecordList type={HYGIENE} />} />
        <Route path="history" element={<StockHistory />} />
        <Route path="*" element={<Navigate to="/nutrition" replace />} />
      </Routes>
    </>
  );
}

function FeedStock() {
  const { role, activeFarm } = useSession();
  const currency = activeFarm?.farm.currency ?? 'KES';
  const items = useQuery({
    queryKey: ['nutrition', 'feed-items'],
    queryFn: () => api<FeedItem[]>('/feed-items'),
  });
  const [editing, setEditing] = useState<FeedItem | 'new' | null>(null);
  const [changing, setChanging] = useState<FeedItem | null>(null);
  const manage = can(role, 'nutrition', 'manage');

  return (
    <section className={page.card}>
      {manage && (
        <div className={page.toolbar}>
          <div style={{ flex: '0 0 auto' }}>
            <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
              <Plus size={18} aria-hidden="true" /> Add feed item
            </button>
          </div>
        </div>
      )}
      {items.isPending ? (
        <div className={page.cardBody}>
          <LoadingState />
        </div>
      ) : items.isError ? (
        <div className={page.cardBody}>
          <ErrorState message={items.error.message} onRetry={() => void items.refetch()} />
        </div>
      ) : items.data.length === 0 ? (
        <div className={page.cardBody}>
          <EmptyState icon={Package} title="No feed items" message="Add the feeds you keep in store." />
        </div>
      ) : (
        <div className={page.tableWrap}>
          <table className={page.table}>
            <thead>
              <tr>
                <th scope="col">Feed</th>
                <th scope="col">In stock</th>
                <th scope="col">Reorder at</th>
                <th scope="col">Use per day</th>
                <th scope="col">Days left</th>
                <th scope="col">Last price</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.data.map((i) => (
                <tr key={i.id}>
                  <td>
                    <strong>{i.name}</strong>
                    <span className={page.sub}>{CATEGORIES.find(([v]) => v === i.category)?.[1]}</span>
                  </td>
                  <td>
                    {qty(i.stock_quantity)} {i.unit}{' '}
                    {i.is_low && <StatusBadge status="low_stock" label="Low stock" />}
                  </td>
                  <td>
                    {qty(i.reorder_level)} {i.unit}
                  </td>
                  <td>{Number(i.average_daily_use) > 0 ? `${qty(i.average_daily_use)} ${i.unit}` : '—'}</td>
                  <td>{i.days_left === null ? '—' : `${i.days_left} days`}</td>
                  <td>
                    {i.unit_cost_cents === null ? '—' : `${money(i.unit_cost_cents, currency)} / ${i.unit}`}
                  </td>
                  <td>
                    {manage && (
                      <div className={page.rowActions}>
                        <button
                          type="button"
                          className={page.small}
                          onClick={() => setChanging(i)}
                          aria-label={`Update stock of ${i.name}`}
                        >
                          Stock
                        </button>
                        <button
                          type="button"
                          className={page.small}
                          onClick={() => setEditing(i)}
                          aria-label={`Edit ${i.name}`}
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <ItemForm item={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />
      )}
      {changing && <StockForm item={changing} onClose={() => setChanging(null)} />}
    </section>
  );
}

function ItemForm({ item, onClose }: { item?: FeedItem; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { activeFarm } = useSession();
  const currency = activeFarm?.farm.currency ?? 'KES';
  const form = useForm({
    defaultValues: {
      name: item?.name ?? '',
      category: item?.category ?? 'forage',
      unit: item?.unit ?? 'kg',
      reorder_level: item ? String(Number(item.reorder_level)) : '0',
      unit_cost: item?.unit_cost_cents ? String(item.unit_cost_cents / 100) : '',
      notes: item?.notes ?? '',
    },
  });
  const { errors, isSubmitting } = form.formState;
  const onSubmit = form.handleSubmit(async ({ unit_cost, ...v }) => {
    try {
      await api(item ? `/feed-items/${item.id}` : '/feed-items', {
        method: item ? 'PATCH' : 'POST',
        body: { ...v, unit_cost_cents: unit_cost ? Math.round(Number(unit_cost) * 100) : null },
      });
      await qc.invalidateQueries({ queryKey: ['nutrition'] });
      toast.success(`${v.name} saved.`);
      onClose();
    } catch (err) {
      applyServerErrors(err, form.setError, ['name', 'category', 'unit', 'reorder_level', 'notes']);
    }
  });
  return (
    <Modal
      title={item ? `Edit ${item.name}` : 'Add feed item'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="item-form" className="btn btn-primary" disabled={isSubmitting}>
            Save
          </button>
        </>
      }
    >
      <form id="item-form" onSubmit={onSubmit} noValidate style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <FormError message={errors.root?.server?.message} />
        <FormInput
          label="Name *"
          error={errors.name?.message}
          {...form.register('name', { required: 'Enter a name.' })}
        />
        <div className={page.grid2}>
          <FormSelect label="Category" {...form.register('category')}>
            {CATEGORIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Unit" {...form.register('unit')}>
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </FormSelect>
        </div>
        <div className={page.grid2}>
          <FormInput
            label="Reorder when stock reaches"
            type="number"
            step="0.01"
            min="0"
            error={errors.reorder_level?.message}
            {...form.register('reorder_level')}
          />
          <FormInput
            label={`Price per unit (${currency})`}
            type="number"
            step="0.01"
            min="0"
            {...form.register('unit_cost')}
          />
        </div>
        <FormInput label="Notes" {...form.register('notes')} />
      </form>
    </Modal>
  );
}

function StockForm({ item, onClose }: { item: FeedItem; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { activeFarm } = useSession();
  const currency = activeFarm?.farm.currency ?? 'KES';
  const form = useForm({
    defaultValues: {
      kind: 'purchase',
      quantity: '',
      counted_quantity: '',
      unit_cost: item.unit_cost_cents ? String(item.unit_cost_cents / 100) : '',
      supplier: '',
      date: new Date().toISOString().slice(0, 10),
      notes: '',
    },
  });
  const kind = form.watch('kind');
  const { errors, isSubmitting } = form.formState;
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      const res = await api<FeedItem>(`/feed-items/${item.id}/stock`, {
        method: 'POST',
        body: {
          kind: v.kind,
          quantity: v.kind === 'adjustment' ? undefined : v.quantity || undefined,
          counted_quantity: v.kind === 'adjustment' ? v.counted_quantity || undefined : undefined,
          unit_cost_cents:
            v.kind === 'purchase' && v.unit_cost ? Math.round(Number(v.unit_cost) * 100) : null,
          supplier: v.supplier,
          date: v.date,
          notes: v.notes,
        },
      });
      await qc.invalidateQueries({ queryKey: ['nutrition'] });
      toast.success(`${item.name}: ${qty(res.stock_quantity)} ${item.unit} in stock.`);
      onClose();
    } catch (err) {
      applyServerErrors(err, form.setError, ['quantity', 'counted_quantity', 'date']);
    }
  });
  return (
    <Modal
      title={`Stock · ${item.name}`}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="stock-form" className="btn btn-primary" disabled={isSubmitting}>
            Save
          </button>
        </>
      }
    >
      <form id="stock-form" onSubmit={onSubmit} noValidate style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <FormError message={errors.root?.server?.message} />
        <p style={{ margin: 0 }}>
          In stock now:{' '}
          <strong>
            {qty(item.stock_quantity)} {item.unit}
          </strong>
        </p>
        <FormSelect label="What happened" {...form.register('kind')}>
          <option value="purchase">Bought / received feed</option>
          <option value="adjustment">Counted the store</option>
          <option value="waste">Feed spoiled or wasted</option>
        </FormSelect>
        {kind === 'adjustment' ? (
          <FormInput
            label={`Counted in store (${item.unit})`}
            type="number"
            step="0.01"
            min="0"
            error={errors.counted_quantity?.message}
            {...form.register('counted_quantity')}
          />
        ) : (
          <FormInput
            label={`Quantity (${item.unit})`}
            type="number"
            step="0.01"
            min="0"
            error={errors.quantity?.message}
            {...form.register('quantity')}
          />
        )}
        {kind === 'purchase' && (
          <div className={page.grid2}>
            <FormInput
              label={`Price per ${item.unit} (${currency})`}
              type="number"
              step="0.01"
              min="0"
              {...form.register('unit_cost')}
            />
            <FormInput label="Supplier" {...form.register('supplier')} />
          </div>
        )}
        <div className={page.grid2}>
          <FormInput label="Date" type="date" error={errors.date?.message} {...form.register('date')} />
          <FormInput label="Notes" {...form.register('notes')} />
        </div>
      </form>
    </Modal>
  );
}

function StockHistory() {
  const { activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const currency = activeFarm?.farm.currency ?? 'KES';
  const list = useCursorList<Movement>(['nutrition', 'movements'], '/feed-stock', {});
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  if (list.isPending) return <LoadingState />;
  if (list.isError) return <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />;
  if (!rows.length) return <EmptyState icon={Package} title="No stock movements yet" />;
  return (
    <section className={page.card}>
      <div className={page.tableWrap}>
        <table className={page.table}>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Feed</th>
              <th scope="col">What</th>
              <th scope="col">Change</th>
              <th scope="col">Cost</th>
              <th scope="col">By</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{formatDate(m.date, fmt)}</td>
                <td>{m.feed_item_name}</td>
                <td>
                  {KIND_LABELS[m.kind] ?? m.kind}
                  {m.supplier && <span className={page.sub}>{m.supplier}</span>}
                </td>
                <td
                  style={{
                    color: Number(m.quantity) < 0 ? 'var(--tone-red-fg)' : 'var(--tone-green-fg)',
                    fontWeight: 600,
                  }}
                >
                  {Number(m.quantity) > 0 ? '+' : ''}
                  {qty(m.quantity)} {m.unit}
                </td>
                <td>{money(m.total_cost_cents, currency)}</td>
                <td>{m.recorded_by ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.hasNextPage && (
        <div className={page.footer}>
          <span />
          <button type="button" className="btn btn-secondary" onClick={() => void list.fetchNextPage()}>
            Load more
          </button>
        </div>
      )}
    </section>
  );
}
