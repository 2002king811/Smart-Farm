import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Baby, Download, Mars, PawPrint, Plus, Settings2, Venus } from 'lucide-react';
import { useDeferredValue, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { StatCard } from '@/components/StatCard';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';
import { useCursorList } from '@/features/users/api';
import { can } from '@/routes/permissions';

import { downloadExport, useLocations, type AnimalRow } from './api';
import { formatAge, formatWeight, HEALTH_STATUSES } from './format';
import styles from './Livestock.module.css';

interface Summary {
  total: number;
  males: number;
  females: number;
  kids: number;
  needing_attention: number;
  pregnant: number;
  inactive: number;
}

export function AnimalThumb({
  animal,
  size = 40,
}: {
  animal: Pick<AnimalRow, 'thumbnail' | 'name' | 'animal_id'>;
  size?: number;
}) {
  return animal.thumbnail ? (
    <img className={styles.thumb} src={animal.thumbnail} alt="" width={size} height={size} />
  ) : (
    <span className={styles.thumb} style={{ width: size, height: size }} aria-hidden="true">
      <PawPrint size={size / 2} />
    </span>
  );
}

export default function RegisterPage() {
  const { role, activeFarm } = useSession();
  const toast = useToast();
  const navigate = useNavigate();
  const unit = activeFarm?.farm.weight_unit ?? 'kg';
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({ sex: '', age: '', status: '', location: '', active: 'true' });
  const q = useDeferredValue(search);
  const query = { search: q, ...filters };
  const list = useCursorList<AnimalRow>(['animals', 'list'], '/animals', query);
  const summary = useQuery({
    queryKey: ['animals', 'summary'],
    queryFn: () => api<Summary>('/animals/summary'),
  });
  const locations = useLocations();
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const count = list.data?.pages[0]?.count ?? 0;
  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }));

  const exportAs = async (format: 'csv' | 'xlsx') => {
    try {
      await downloadExport(query, format);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed.');
    }
  };

  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Livestock register</h2>
          <p>
            Every animal on {activeFarm?.farm.name ?? 'the farm'}, with its status, location and latest
            weight.
          </p>
        </div>
        <div className={styles.headerActions}>
          {can(role, 'livestock', 'manage') && (
            <Link to="/livestock/setup" className="btn btn-secondary">
              <Settings2 size={18} aria-hidden="true" /> Locations &amp; groups
            </Link>
          )}
          {can(role, 'livestock', 'export') && (
            <>
              <button type="button" className="btn btn-secondary" onClick={() => void exportAs('xlsx')}>
                <Download size={18} aria-hidden="true" /> Excel
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => void exportAs('csv')}>
                <Download size={18} aria-hidden="true" /> CSV
              </button>
            </>
          )}
          {can(role, 'livestock', 'create') && (
            <Link to="/livestock/new" className="btn btn-primary">
              <Plus size={18} aria-hidden="true" /> Register animal
            </Link>
          )}
        </div>
      </div>

      <div className={styles.stats}>
        <StatCard label="Total animals" value={summary.data?.total ?? '—'} icon={PawPrint} />
        <StatCard label="Females" value={summary.data?.females ?? '—'} icon={Venus} />
        <StatCard label="Males" value={summary.data?.males ?? '—'} icon={Mars} />
        <StatCard label="Kids (under 6 months)" value={summary.data?.kids ?? '—'} icon={Baby} />
        <StatCard
          label="Needing attention"
          value={summary.data?.needing_attention ?? '—'}
          icon={AlertTriangle}
        />
      </div>

      <div className={page.card}>
        <div className={page.toolbar}>
          <div className={page.search}>
            <FormInput
              label="Search"
              type="search"
              placeholder="ID, ear tag, name or breed"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <FormSelect label="Sex" value={filters.sex} onChange={set('sex')}>
            <option value="">All</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
          </FormSelect>
          <FormSelect label="Age" value={filters.age} onChange={set('age')}>
            <option value="">All ages</option>
            <option value="kid">Kids (under 6 months)</option>
            <option value="young">6–12 months</option>
            <option value="adult">Over 12 months</option>
          </FormSelect>
          <FormSelect label="Health status" value={filters.status} onChange={set('status')}>
            <option value="">All</option>
            {HEALTH_STATUSES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Location" value={filters.location} onChange={set('location')}>
            <option value="">All locations</option>
            {locations.data?.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Show" value={filters.active} onChange={set('active')}>
            <option value="true">In the herd</option>
            <option value="false">Sold, died or culled</option>
            <option value="all">All</option>
          </FormSelect>
        </div>

        {list.isPending ? (
          <div className={page.cardBody}>
            <LoadingState />
          </div>
        ) : list.isError ? (
          <div className={page.cardBody}>
            <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />
          </div>
        ) : rows.length === 0 ? (
          <div className={page.cardBody}>
            <EmptyState
              icon={PawPrint}
              title={summary.data?.total === 0 && !q ? 'No animals yet' : 'No animals match'}
              message={
                summary.data?.total === 0 && !q
                  ? 'Register your first animal to start the herd record.'
                  : 'Try another search or filter.'
              }
              action={
                can(role, 'livestock', 'create') && summary.data?.total === 0 ? (
                  <Link to="/livestock/new" className="btn btn-primary">
                    Register animal
                  </Link>
                ) : undefined
              }
            />
          </div>
        ) : (
          <>
            <div className={page.tableWrap}>
              <table className={`${page.table} ${styles.register}`}>
                <thead>
                  <tr>
                    <th scope="col">Animal</th>
                    <th scope="col">Breed</th>
                    <th scope="col">Sex</th>
                    <th scope="col">Age</th>
                    <th scope="col">Status</th>
                    <th scope="col">Location</th>
                    <th scope="col">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => (
                    <tr
                      key={a.id}
                      className={styles.clickable}
                      onClick={() => navigate(`/livestock/${a.id}`)}
                    >
                      <td>
                        <div className={page.person}>
                          <AnimalThumb animal={a} />
                          <span>
                            <Link
                              to={`/livestock/${a.id}`}
                              className={styles.animalLink}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {a.animal_id}
                              {a.name ? ` ${a.name}` : ''}
                            </Link>
                            <span className={page.sub}>{a.ear_tag ? `Tag ${a.ear_tag}` : 'No ear tag'}</span>
                          </span>
                        </div>
                      </td>
                      <td>{a.breed || '—'}</td>
                      <td>{a.sex === 'female' ? 'Female' : 'Male'}</td>
                      <td>
                        {formatAge(a.date_of_birth, a.dob_estimated)}
                        {a.is_kid && <span className={page.sub}>Kid</span>}
                      </td>
                      <td>
                        {a.is_active ? (
                          <StatusBadge status={a.health_status} />
                        ) : (
                          <StatusBadge status={a.exit_reason || 'inactive'} />
                        )}
                      </td>
                      <td>{a.location?.name ?? '—'}</td>
                      <td>{formatWeight(a.latest_weight_kg, unit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={page.footer}>
              <span>
                Showing {rows.length} of {count}
              </span>
              {list.hasNextPage && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void list.fetchNextPage()}
                  disabled={list.isFetchingNextPage}
                >
                  Load more
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
