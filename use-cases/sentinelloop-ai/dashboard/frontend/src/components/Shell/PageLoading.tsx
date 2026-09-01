type Props = {
  label?: string;
  rows?: number;
};

export function PageLoading({ label = "Loading command center", rows = 3 }: Props) {
  return (
    <div className="sl-page-loading" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="sl-page-loading__block" />
      ))}
      <p>{label}</p>
    </div>
  );
}
