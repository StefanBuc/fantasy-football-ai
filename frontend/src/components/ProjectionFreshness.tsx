export function ProjectionFreshness({ generatedAt }: { generatedAt: string }) {
  const date = new Date(generatedAt)
  const label = Number.isNaN(date.getTime())
    ? 'Unknown'
    : date.toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
        second: '2-digit', timeZoneName: 'short',
      })

  return (
    <p className="mt-3 text-xs font-semibold text-slate-500">
      Last generated: <time dateTime={generatedAt}>{label}</time>
    </p>
  )
}
