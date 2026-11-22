import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { UserPlus, Users } from 'lucide-react';
import { useDeferredValue, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import {
  applyServerErrors,
  Checkbox,
  CheckboxGroup,
  FormError,
  FormInput,
  FormSelect,
} from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { optionalEmail, optionalPhone } from '@/features/auth/schemas';
import { useSession } from '@/features/session/SessionContext';

import { CHANNEL_OPTIONS, ROLE_OPTIONS, useCursorList, type Invitation, type Member } from './api';

type Tab = 'members' | 'invitations';

export default function UsersPage() {
  const [tab, setTab] = useState<Tab>('members');
  const [adding, setAdding] = useState(false);
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>User Management</h2>
          <p>Add staff to the farm, set their role, and turn access on or off.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          <UserPlus size={18} aria-hidden="true" /> Add user
        </button>
      </div>
      <div className={page.tabs} role="tablist" aria-label="User Management">
        {(['members', 'invitations'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            className={page.tab}
            onClick={() => setTab(t)}
          >
            {t === 'members' ? 'Users' : 'Invitations'}
          </button>
        ))}
      </div>
      {tab === 'members' ? <MembersTab /> : <InvitationsTab />}
      <AddUserModal open={adding} onClose={() => setAdding(false)} onInvited={() => setTab('invitations')} />
    </>
  );
}

function initials(first: string, last: string) {
  return `${first[0] ?? ''}${last[0] ?? ''}`.toUpperCase() || '?';
}

function formatDate(value?: string | null) {
  if (!value) return 'Never';
  return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// --- Users tab -------------------------------------------------------------------------------------

function MembersTab() {
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const q = useDeferredValue(search);
  const list = useCursorList<Member>(['members'], '/members', { search: q, role, status });
  const [editing, setEditing] = useState<Member | null>(null);
  const [resetting, setResetting] = useState<Member | null>(null);
  const [toggling, setToggling] = useState<Member | null>(null);
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const count = list.data?.pages[0]?.count ?? 0;

  return (
    <div className={page.card}>
      <div className={page.toolbar}>
        <div className={page.search}>
          <FormInput
            label="Search"
            type="search"
            placeholder="Name, email or phone"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <FormSelect label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">All roles</option>
          {ROLE_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </FormSelect>
        <FormSelect label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
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
          <EmptyState icon={Users} title="No users found" message="Try another search or filter." />
        </div>
      ) : (
        <>
          <div className={page.tableWrap}>
            <table className={page.table}>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Role</th>
                  <th scope="col">Contact</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last login</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div className={page.person}>
                        <span className={page.initials} aria-hidden="true">
                          {initials(m.first_name, m.last_name)}
                        </span>
                        <span>
                          <strong>{m.full_name}</strong>
                          <span className={page.sub}>{m.job_title || `@${m.username}`}</span>
                        </span>
                      </div>
                    </td>
                    <td>{m.role_label}</td>
                    <td>
                      {m.email && <span className={page.sub}>{m.email}</span>}
                      {m.phone && <span className={page.sub}>{m.phone}</span>}
                    </td>
                    <td>
                      <StatusBadge status={m.status} />
                    </td>
                    <td>{formatDate(m.last_login)}</td>
                    <td>
                      <div className={page.rowActions}>
                        <button
                          type="button"
                          className={page.small}
                          onClick={() => setEditing(m)}
                          aria-label={`Edit ${m.full_name}`}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className={page.small}
                          onClick={() => setResetting(m)}
                          aria-label={`Reset password for ${m.full_name}`}
                        >
                          Reset password
                        </button>
                        <button
                          type="button"
                          className={`${page.small} ${m.status === 'active' ? page.danger : ''}`}
                          onClick={() => setToggling(m)}
                          aria-label={`${m.status === 'active' ? 'Deactivate' : 'Activate'} ${m.full_name}`}
                        >
                          {m.status === 'active' ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
                    </td>
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
      <EditMemberModal member={editing} onClose={() => setEditing(null)} />
      <ResetPasswordModal member={resetting} onClose={() => setResetting(null)} />
      <ToggleMemberModal member={toggling} onClose={() => setToggling(null)} />
    </div>
  );
}

const editSchema = z.object({ role: z.string(), job_title: z.string() });

function EditMemberModal({ member, onClose }: { member: Member | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const form = useForm<z.infer<typeof editSchema>>({
    resolver: zodResolver(editSchema),
    values: { role: member?.role ?? 'livestock_attendant', job_title: member?.job_title ?? '' },
  });
  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await api(`/members/${member!.id}`, { method: 'PATCH', body: values });
      await qc.invalidateQueries({ queryKey: ['members'] });
      toast.success(`${member!.full_name} is updated.`);
      onClose();
    } catch (err) {
      applyServerErrors(err, form.setError, ['role', 'job_title']);
    }
  });
  return (
    <Modal
      title={`Edit ${member?.full_name ?? ''}`}
      open={!!member}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="edit-member"
            className="btn btn-primary"
            disabled={form.formState.isSubmitting}
          >
            Save
          </button>
        </>
      }
    >
      <form
        id="edit-member"
        onSubmit={onSubmit}
        noValidate
        style={{ display: 'grid', gap: 'var(--space-4)' }}
      >
        <FormError message={form.formState.errors.root?.server?.message} />
        <FormSelect label="Role" error={form.formState.errors.role?.message} {...form.register('role')}>
          {ROLE_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </FormSelect>
        <FormInput
          label="Job title (optional)"
          placeholder="e.g. Herd manager"
          {...form.register('job_title')}
        />
      </form>
    </Modal>
  );
}

function ChannelPicker({
  value,
  onChange,
  error,
  hasEmail,
  hasPhone,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  error?: string;
  hasEmail: boolean;
  hasPhone: boolean;
}) {
  const { user } = useSession();
  return (
    <CheckboxGroup legend="Send by" error={error}>
      {CHANNEL_OPTIONS.map(([v, l]) => {
        const needsPhone = v !== 'email';
        const disabled = v === 'email' ? !hasEmail : !hasPhone || !user?.phone_verified;
        return (
          <Checkbox
            key={v}
            label={needsPhone && !user?.phone_verified ? `${l} (confirm your phone first)` : l}
            checked={value.includes(v) && !disabled}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked ? [...value, v] : value.filter((x) => x !== v))}
          />
        );
      })}
    </CheckboxGroup>
  );
}

function ResetPasswordModal({ member, onClose }: { member: Member | null; onClose: () => void }) {
  const toast = useToast();
  const [channels, setChannels] = useState<string[]>(['email']);
  const [error, setError] = useState<string>();
  const reset = useMutation({
    mutationFn: () =>
      api<{ detail: string }>(`/members/${member!.id}/reset-password`, {
        method: 'POST',
        body: { channels },
      }),
    onSuccess: (res) => {
      toast.success(res.detail);
      onClose();
    },
    onError: (err) =>
      setError(
        err instanceof ApiError
          ? [...err.field('channels'), ...err.field('detail')].join(' ') || err.message
          : 'Could not reset.',
      ),
  });
  return (
    <Modal
      title="Reset password"
      open={!!member}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => reset.mutate()}
            disabled={reset.isPending}
          >
            Send temporary password
          </button>
        </>
      }
    >
      <p style={{ margin: 0 }}>
        {member?.full_name} gets a temporary password and must choose a new one at their next login. They are
        logged out everywhere.
      </p>
      <FormError message={error} />
      <ChannelPicker
        value={channels}
        onChange={setChannels}
        hasEmail={!!member?.email}
        hasPhone={!!member?.phone}
      />
    </Modal>
  );
}

function ToggleMemberModal({ member, onClose }: { member: Member | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string>();
  const deactivate = member?.status === 'active';
  const toggle = useMutation({
    mutationFn: () =>
      api<Member>(`/members/${member!.id}/${deactivate ? 'deactivate' : 'activate'}`, { method: 'POST' }),
    onSuccess: async (m) => {
      await qc.invalidateQueries({ queryKey: ['members'] });
      toast.success(`${m.full_name} is now ${m.status === 'active' ? 'active' : 'inactive'}.`);
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not change access.'),
  });
  return (
    <Modal
      title={deactivate ? 'Deactivate user' : 'Activate user'}
      open={!!member}
      onClose={() => {
        setError(undefined);
        onClose();
      }}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
          >
            {deactivate ? 'Deactivate' : 'Activate'}
          </button>
        </>
      }
    >
      <FormError message={error} />
      <p style={{ margin: 0 }}>
        {deactivate
          ? `${member?.full_name} loses access to this farm straight away. Their records and history stay.`
          : `${member?.full_name} can use this farm again with their existing login.`}
      </p>
    </Modal>
  );
}

// --- Add user --------------------------------------------------------------------------------------

const addSchema = z
  .object({
    mode: z.enum(['invite', 'create']),
    first_name: z.string().trim().min(1, 'Enter a first name.'),
    last_name: z.string().trim(),
    email: optionalEmail,
    phone: optionalPhone,
    role: z.string(),
    job_title: z.string(),
    channels: z.array(z.string()).min(1, 'Choose at least one way to send it.'),
  })
  .refine((v) => v.email || v.phone, { path: ['email'], message: 'Add an email address or a mobile number.' })
  .refine((v) => v.mode === 'invite' || v.last_name, { path: ['last_name'], message: 'Enter a last name.' });
type AddValues = z.infer<typeof addSchema>;

const ADD_DEFAULTS: AddValues = {
  mode: 'invite',
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  role: 'livestock_attendant',
  job_title: '',
  channels: ['email'],
};

function AddUserModal({
  open,
  onClose,
  onInvited,
}: {
  open: boolean;
  onClose: () => void;
  onInvited: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [created, setCreated] = useState<{ name: string; username: string; password: string } | null>(null);
  const form = useForm<AddValues>({ resolver: zodResolver(addSchema), defaultValues: ADD_DEFAULTS });
  const { errors, isSubmitting } = form.formState;
  const mode = form.watch('mode');

  const close = () => {
    form.reset(ADD_DEFAULTS);
    setCreated(null);
    onClose();
  };

  const onSubmit = form.handleSubmit(async ({ mode: m, ...values }) => {
    try {
      if (m === 'invite') {
        await api('/invitations', { method: 'POST', body: values });
        await qc.invalidateQueries({ queryKey: ['invitations'] });
        toast.success(`Invitation sent to ${values.first_name}.`);
        onInvited();
        close();
      } else {
        const res = await api<{ member: Member; temporary_password: string }>('/members', {
          method: 'POST',
          body: values,
        });
        await qc.invalidateQueries({ queryKey: ['members'] });
        toast.success(`${res.member.full_name} has been added.`);
        setCreated({
          name: res.member.full_name,
          username: res.member.username,
          password: res.temporary_password,
        });
      }
    } catch (err) {
      applyServerErrors(err, form.setError, [
        'first_name',
        'last_name',
        'email',
        'phone',
        'role',
        'channels',
        'username',
      ]);
    }
  });

  if (created) {
    return (
      <Modal
        title="User added"
        open={open}
        onClose={close}
        footer={
          <button type="button" className="btn btn-primary" onClick={close}>
            Done
          </button>
        }
      >
        <p style={{ margin: 0 }}>
          We sent the login details to {created.name}. If they need them in person, share these now. You will
          not see this password again.
        </p>
        <div className={page.note}>
          Username: <span className={page.secret}>{created.username}</span>
          <br />
          Temporary password: <span className={page.secret}>{created.password}</span>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Add user"
      open={open}
      onClose={close}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={close}>
            Cancel
          </button>
          <button type="submit" form="add-user" className="btn btn-primary" disabled={isSubmitting}>
            {mode === 'invite' ? 'Send invitation' : 'Create user'}
          </button>
        </>
      }
    >
      <form id="add-user" onSubmit={onSubmit} noValidate style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <FormError message={errors.root?.server?.message} />
        <CheckboxGroup legend="How to add them">
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', minHeight: 44 }}>
            <input type="radio" value="invite" {...form.register('mode')} /> Send an invitation link (they
            choose their own password)
          </label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', minHeight: 44 }}>
            <input type="radio" value="create" {...form.register('mode')} /> Create the account now with a
            temporary password
          </label>
        </CheckboxGroup>
        <div className={page.grid2}>
          <FormInput label="First name" error={errors.first_name?.message} {...form.register('first_name')} />
          <FormInput
            label={mode === 'invite' ? 'Last name (optional)' : 'Last name'}
            error={errors.last_name?.message}
            {...form.register('last_name')}
          />
        </div>
        <div className={page.grid2}>
          <FormInput label="Email" type="email" error={errors.email?.message} {...form.register('email')} />
          <FormInput
            label="Mobile number"
            type="tel"
            placeholder="0712 345 678"
            error={errors.phone?.message}
            {...form.register('phone')}
          />
        </div>
        <div className={page.grid2}>
          <FormSelect label="Role" {...form.register('role')}>
            {ROLE_OPTIONS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
          {mode === 'create' && <FormInput label="Job title (optional)" {...form.register('job_title')} />}
        </div>
        <ChannelPicker
          value={form.watch('channels')}
          onChange={(v) => form.setValue('channels', v, { shouldValidate: form.formState.isSubmitted })}
          error={errors.channels?.message}
          hasEmail={!!form.watch('email')}
          hasPhone={!!form.watch('phone')}
        />
      </form>
    </Modal>
  );
}

// --- Invitations tab --------------------------------------------------------------------------------

function InvitationsTab() {
  const [status, setStatus] = useState('pending');
  const list = useCursorList<Invitation>(['invitations'], '/invitations', { status });
  const qc = useQueryClient();
  const toast = useToast();
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];

  const act = async (inv: Invitation, action: 'resend' | 'revoke') => {
    try {
      await api(`/invitations/${inv.id}/${action}`, { method: 'POST' });
      await qc.invalidateQueries({ queryKey: ['invitations'] });
      toast.success(
        action === 'resend' ? `Invitation sent again to ${inv.first_name}.` : 'Invitation cancelled.',
      );
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Something went wrong.');
    }
  };

  return (
    <div className={page.card}>
      <div className={page.toolbar}>
        <FormSelect label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">Pending</option>
          <option value="accepted">Accepted</option>
          <option value="revoked">Revoked</option>
          <option value="">All</option>
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
            icon={UserPlus}
            title="No invitations"
            message="Use “Add user” to invite someone to the farm."
          />
        </div>
      ) : (
        <div className={page.tableWrap}>
          <table className={page.table}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Role</th>
                <th scope="col">Sent to</th>
                <th scope="col">Status</th>
                <th scope="col">Expires</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((inv) => {
                const expired = inv.status === 'pending' && new Date(inv.expires_at) < new Date();
                return (
                  <tr key={inv.id}>
                    <td>
                      <strong>
                        {inv.first_name} {inv.last_name}
                      </strong>
                      <span className={page.sub}>Invited by {inv.invited_by_name}</span>
                    </td>
                    <td>{inv.role_label}</td>
                    <td>
                      {inv.email && <span className={page.sub}>{inv.email}</span>}
                      {inv.phone && <span className={page.sub}>{inv.phone}</span>}
                    </td>
                    <td>
                      <StatusBadge status={expired ? 'expired' : inv.status} />
                    </td>
                    <td>{formatDate(inv.expires_at)}</td>
                    <td>
                      {inv.status === 'pending' && (
                        <div className={page.rowActions}>
                          <button
                            type="button"
                            className={page.small}
                            onClick={() => void act(inv, 'resend')}
                          >
                            Resend
                          </button>
                          <button
                            type="button"
                            className={`${page.small} ${page.danger}`}
                            onClick={() => void act(inv, 'revoke')}
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
