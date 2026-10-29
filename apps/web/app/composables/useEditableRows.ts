/**
 * Editable drafts of a list the gateway serves, one per item, by id.
 *
 * A refetch lands while the admin may be editing another row (after saving
 * one row, say), so a row they changed keeps their edit; the rest take the
 * gateway's values. A row counts as changed when it differs from what it was
 * last filled with from the gateway.
 */
export function useEditableRows<Item, Row extends object>(
  source: Ref<Item[]>,
  idOf: (item: Item) => string,
  rowOf: (item: Item) => Row,
): Ref<Record<string, Row>> {
  const rows = ref({}) as Ref<Record<string, Row>>;
  let seeded: Record<string, Row> = {};

  const sameRow = (a: Row | undefined, b: Row | undefined) =>
    JSON.stringify(a) === JSON.stringify(b);

  watch(
    source,
    (list) => {
      const next: Record<string, Row> = {};
      const nextSeeded: Record<string, Row> = {};
      for (const item of list) {
        const id = idOf(item);
        const fresh = rowOf(item);
        const current = rows.value[id];
        const edited = current !== undefined && !sameRow(current, seeded[id]);
        next[id] = edited && !sameRow(current, fresh) ? current : fresh;
        // a copy: the form edits its row in place, and the snapshot must not move with it
        nextSeeded[id] = { ...fresh };
      }
      rows.value = next;
      seeded = nextSeeded;
    },
    { immediate: true },
  );

  return rows;
}
