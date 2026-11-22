import { useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '@/api/client';
import { FormInput, FormSelect } from '@/components/forms';

export type Country = Schemas['Country'];

export const OTHER = 'XX';

export function useCountries() {
  return useQuery({
    queryKey: ['countries'],
    queryFn: () => api<Country[]>('/countries', { noRefresh: true }),
    staleTime: Infinity,
  });
}

/** Country select; "Other" covers countries without a district list. */
export function CountrySelect({
  value,
  onChange,
  countries,
  error,
  id,
}: {
  value: string;
  onChange: (code: string) => void;
  countries: Country[];
  error?: string;
  id?: string;
}) {
  return (
    <FormSelect
      id={id}
      label="Country"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      error={error}
    >
      {countries.map((c) => (
        <option key={c.code} value={c.code}>
          {c.name}
        </option>
      ))}
      <option value={OTHER}>Another country</option>
    </FormSelect>
  );
}

/** District / county / region of the chosen country, or free text for other countries. */
export function RegionField({
  country,
  countries,
  value,
  onChange,
  error,
}: {
  country: string;
  countries: Country[];
  value: string;
  onChange: (v: string) => void;
  error?: string;
}) {
  const c = countries.find((x) => x.code === country);
  if (!c)
    return (
      <FormInput
        label="Region / district"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        error={error}
      />
    );
  return (
    <FormSelect label={c.region_label} value={value} onChange={(e) => onChange(e.target.value)} error={error}>
      <option value="">Choose…</option>
      {c.regions.map((r) => (
        <option key={r} value={r}>
          {r}
        </option>
      ))}
    </FormSelect>
  );
}
