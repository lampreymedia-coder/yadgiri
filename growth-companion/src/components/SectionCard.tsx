import type { PropsWithChildren, ReactNode } from 'react'

interface SectionCardProps extends PropsWithChildren {
  title: string
  subtitle?: string
  action?: ReactNode
  className?: string
}

function SectionCard({ title, subtitle, action, className, children }: SectionCardProps) {
  return (
    <section className={`section-card ${className ?? ''}`.trim()}>
      <header className="section-card__header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {action ? <div className="section-card__action">{action}</div> : null}
      </header>
      {children}
    </section>
  )
}

export default SectionCard
