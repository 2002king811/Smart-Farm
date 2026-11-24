import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef, type ReactNode } from 'react';

import page from './Page.module.css';

interface Props<T> {
  rows: T[];
  head: ReactNode;
  renderRow: (row: T, index: number) => ReactNode;
  /** Tables longer than this draw only the rows on screen. */
  threshold?: number;
  rowHeight?: number;
}

/** A table that stays fast with thousands of rows: over 200 rows, only the visible ones are
 * rendered (spacer rows keep the scrollbar right). */
export function VirtualTable<T>({ rows, head, renderRow, threshold = 200, rowHeight = 41 }: Props<T>) {
  const box = useRef<HTMLDivElement>(null);
  const virtual = rows.length > threshold;
  const v = useVirtualizer({
    count: virtual ? rows.length : 0,
    getScrollElement: () => box.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  });
  if (!virtual) {
    return (
      <div className={page.tableWrap}>
        <table className={page.table}>
          <thead>{head}</thead>
          <tbody>{rows.map(renderRow)}</tbody>
        </table>
      </div>
    );
  }
  const items = v.getVirtualItems();
  const top = items[0]?.start ?? 0;
  const bottom = v.getTotalSize() - (items.at(-1)?.end ?? 0);
  return (
    // A scrolling region must be reachable by keyboard so it can be scrolled without a mouse.
    <div
      ref={box}
      className={page.tableWrap}
      style={{ maxHeight: 640, overflowY: 'auto' }}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      role="region"
      aria-label={`Table with ${rows.length} rows`}
    >
      <table className={page.table} aria-rowcount={rows.length + 1}>
        <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>{head}</thead>
        <tbody>
          {top > 0 && (
            <tr aria-hidden="true">
              <td style={{ height: top, padding: 0, border: 0 }} />
            </tr>
          )}
          {items.map((item) => renderRow(rows[item.index]!, item.index))}
          {bottom > 0 && (
            <tr aria-hidden="true">
              <td style={{ height: bottom, padding: 0, border: 0 }} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
