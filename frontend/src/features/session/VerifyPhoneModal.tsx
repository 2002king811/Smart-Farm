import { useState } from 'react';

import { api, ApiError, type Schemas } from '@/api/client';
import { FormError, FormInput } from '@/components/forms';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';

import { useSession } from './SessionContext';

export function VerifyPhoneModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, setUser } = useSession();
  const toast = useToast();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setError(undefined);
    try {
      const res = await api<{ detail: string }>('/auth/verify-phone/send', { method: 'POST' });
      toast.success(res.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the code.');
    }
  };

  const verify = async () => {
    setBusy(true);
    setError(undefined);
    try {
      const me = await api<Schemas['Me']>('/auth/verify-phone', { method: 'POST', body: { code } });
      setUser(me);
      toast.success('Your mobile number is confirmed.');
      setCode('');
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? (err.field('code')[0] ?? err.message) : 'Could not check the code.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Confirm your mobile number"
      open={open}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={() => void send()}>
            Send a new code
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void verify()}
            disabled={busy || code.trim().length !== 6}
          >
            Confirm
          </button>
        </>
      }
    >
      <p style={{ margin: 0 }}>Enter the 6-digit code we sent by SMS to {user?.phone}.</p>
      <FormError message={error} />
      <FormInput
        label="6-digit code"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
      />
    </Modal>
  );
}
