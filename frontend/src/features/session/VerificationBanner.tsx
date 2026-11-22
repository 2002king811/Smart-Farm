import { MailCheck } from 'lucide-react';
import { useState } from 'react';

import { api, ApiError } from '@/api/client';
import { useToast } from '@/components/Toast';

import { useSession } from './SessionContext';
import styles from './VerificationBanner.module.css';
import { VerifyPhoneModal } from './VerifyPhoneModal';

/** Reminds the user to confirm email and phone. WhatsApp and SMS stay off until the phone is confirmed. */
export function VerificationBanner() {
  const { user } = useSession();
  const toast = useToast();
  const [phoneOpen, setPhoneOpen] = useState(false);
  if (!user) return null;
  const needEmail = !!user.email && !user.email_verified;
  const needPhone = !!user.phone && !user.phone_verified;
  if (!needEmail && !needPhone) return null;

  const resendEmail = async () => {
    try {
      const res = await api<{ detail: string }>('/auth/verify-email/resend', { method: 'POST' });
      toast.success(res.detail);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not send the link.');
    }
  };

  return (
    <div className={styles.banner} role="region" aria-label="Account checks">
      <MailCheck size={20} aria-hidden="true" />
      <div className={styles.text}>
        {needEmail && (
          <span>
            Confirm your email ({user.email}).{' '}
            <button type="button" className={styles.link} onClick={() => void resendEmail()}>
              Resend link
            </button>
          </span>
        )}
        {needPhone && (
          <span>
            Confirm your mobile number to turn on SMS and WhatsApp.{' '}
            <button type="button" className={styles.link} onClick={() => setPhoneOpen(true)}>
              Enter code
            </button>
          </span>
        )}
      </div>
      <VerifyPhoneModal open={phoneOpen} onClose={() => setPhoneOpen(false)} />
    </div>
  );
}
