import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface ChartItem {
  name: string
  value: number
  color: string
}

interface ProgressChartProps {
  data: ChartItem[]
}

function ProgressChart({ data }: ProgressChartProps) {
  return (
    <div className="chart-shell">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 6 }}>
          <CartesianGrid stroke="rgba(148, 163, 184, 0.16)" strokeDasharray="4 4" vertical={false} />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fill: '#475569', fontSize: 12 }}
          />
          <YAxis
            domain={[0, 5]}
            ticks={[1, 2, 3, 4, 5]}
            tickLine={false}
            axisLine={false}
            tick={{ fill: '#64748b', fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.5)' }}
            contentStyle={{
              borderRadius: '16px',
              border: '1px solid rgba(148, 163, 184, 0.18)',
              background: '#ffffff',
              boxShadow: '0 18px 46px rgba(15, 23, 42, 0.14)',
            }}
            formatter={(value: number) => [`${value} از ۵`, 'امتیاز']}
          />
          <Bar dataKey="value" radius={[14, 14, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default ProgressChart
