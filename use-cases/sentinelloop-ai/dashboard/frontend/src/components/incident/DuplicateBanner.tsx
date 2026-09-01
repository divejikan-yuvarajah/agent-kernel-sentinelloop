type Props = {
  count: number;
  location?: string | null;
};

export function DuplicateBanner({ count, location }: Props) {
  if (count <= 1) return null;
  return (
    <aside className="ii-duplicate" role="status">
      <p className="ii-duplicate__title">Reported by {count} workers</p>
      <p>
        Reported by {count} workers{location ? ` in the same area (${location})` : " in the same area"}
      </p>
    </aside>
  );
}
