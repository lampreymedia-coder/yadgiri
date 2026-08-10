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
    <div className="chart-shell" role="img" aria-label="نمودار امتیازهای هفتگی">
      {data.map((entry) => (
        <div key={entry.name} className="mini-chart__row">
          <div className="mini-chart__label">
            <strong>{entry.name}</strong>
            <span>{entry.value} / ۵</span>
          </div>
          <div className="mini-chart__track">
            <div
              className="mini-chart__bar"
              style={{
                width: `${(entry.value / 5) * 100}%`,
                background: entry.color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export default ProgressChart
