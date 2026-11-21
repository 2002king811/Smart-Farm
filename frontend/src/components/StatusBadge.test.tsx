import { render, screen } from '@testing-library/react';

import { StatusBadge, statusDef, STATUS_MAP } from './StatusBadge';

describe('StatusBadge', () => {
  it('shows the prototype label and tone for a status', () => {
    render(<StatusBadge status="under_treatment" />);
    const badge = screen.getByText('Under Treatment');
    expect(badge).toHaveAttribute('data-tone', 'amber');
  });

  it('falls back to a grey, readable label for unknown statuses', () => {
    expect(statusDef('some_new_state')).toEqual({ label: 'some new state', tone: 'grey' });
  });

  it('covers every health and activity status from the spec', () => {
    for (const s of ['healthy', 'under_treatment', 'sick', 'quarantined', 'pregnant', 'monitoring']) {
      expect(STATUS_MAP[s]).toBeDefined();
    }
    for (const s of ['pending', 'in_progress', 'completed', 'overdue', 'cancelled']) {
      expect(STATUS_MAP[s]).toBeDefined();
    }
  });

  it('allows a translated label while keeping the colour', () => {
    render(<StatusBadge status="sick" label="Mgonjwa" />);
    expect(screen.getByText('Mgonjwa')).toHaveAttribute('data-tone', 'red');
  });
});
