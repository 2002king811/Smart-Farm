import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { SERIES_COLOURS, type Chart } from './api';
import styles from './Reports.module.css';

/** The report's chart, from the same series the PDF draws. */
export function ReportChart({ chart }: { chart: Chart }) {
  const data = chart.labels.map((label, i) => ({
    label,
    ...Object.fromEntries(chart.series.map((s) => [s.name, s.values[i] ?? 0])),
  }));
  return (
    <figure className={styles.chart} aria-label={chart.title}>
      <figcaption>{chart.title}</figcaption>
      <div className={styles.chartBox}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} interval="preserveStartEnd" />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip />
            {chart.series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {chart.series.map((s, i) => (
              <Bar
                key={s.name}
                dataKey={s.name}
                stackId={chart.stacked ? 'a' : undefined}
                fill={SERIES_COLOURS[i % SERIES_COLOURS.length]}
                radius={chart.stacked ? 0 : [4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
