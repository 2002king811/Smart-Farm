import { z } from 'zod';

/** Client-side rules that mirror the backend; the server stays the source of truth. */
export const phone = z
  .string()
  .trim()
  .refine(
    (v) => /^(\+?\d[\d\s\-()]{7,18})$/.test(v),
    'Enter a valid mobile number, for example 0712 345 678.',
  );
export const optionalPhone = z.union([z.literal(''), phone]);
export const password = z.string().min(8, 'Use at least 8 characters.');
export const email = z.string().trim().email('Enter a valid email address.');
export const optionalEmail = z.union([z.literal(''), email]);
