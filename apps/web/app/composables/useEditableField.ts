/**
 * Whether two drafts hold the same value. Drafts are plain data bound to form
 * fields, so they compare by content: a list of header rows or auth modes
 * equals another with the same items in the same order.
 */
export function sameDraft(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * An editable copy of one value the gateway serves, for a form field.
 *
 * The data behind a form is read again while the admin may be typing (another
 * card's action, a save elsewhere on the page), so the field takes the
 * gateway's new value only while it still holds the value it was last filled
 * with; an edit in progress is kept. Once a save comes back the gateway
 * reports the edit, and the field follows the gateway again.
 */
export function useEditableField<T>(source: () => T): Ref<T> {
  const field = ref(copyOf(source())) as Ref<T>;
  // a snapshot, not the value: the form may edit a list in place
  let seeded = JSON.stringify(field.value);

  watch(source, (fresh) => {
    if (JSON.stringify(field.value) === seeded) field.value = copyOf(fresh);
    seeded = JSON.stringify(fresh);
  });

  return field;
}

/** A copy the form may edit in place without reaching into the cached read. */
function copyOf<T>(value: T): T {
  return value !== null && typeof value === "object" ? JSON.parse(JSON.stringify(value)) : value;
}
