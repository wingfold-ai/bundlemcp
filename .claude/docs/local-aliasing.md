# Local Aliasing

When to bind a local name to a member expression (`state = self._app.state`), and when to leave the expression in place.
Fowler calls this **Extract Variable**; the inverse is **Inline Variable**.

Not to be confused with PL-theory aliasing (two references to one mutable object) — that is a correctness topic, this is
a readability one.

## The rules

A local needs **one** of two independent justifications — it adds meaning (rule 1), or it collapses a repeated reach
(rule 2). Rules 3–6 then constrain whichever one applies.

1. **Alias to add meaning, not to save typing.** If the new name is a synonym of the expression it replaces, it earns
   nothing and costs a binding the reader must track. `settings = self._settings` is pure cost — and no usage count
   redeems it, because a single attribute access is not a reach.
2. **Rule of three, for reaches only.** Three or more uses of a *non-trivial* expression — a multi-hop reach
   (`self._app.state`), a call, a compound condition — may be extracted even though the name is a synonym. Reducing a
   repeated two-hop reach is a Law-of-Demeter justification, separate from naming. One or two uses: leave it inline.
3. **The alias name must be at least as informative as what it replaces.** `state = self._app.state` passes;
   `st = self._app.state` does not.
4. **Narrowest scope, declared at first use** — never a preamble block of aliases at the top of a function.
5. **Repetition across many methods is a structural signal, not an aliasing problem, and it outranks rule 2.** If
   several methods open with the same alias, hold the reference once — a constructor attribute, a property, a parameter,
   or a different class boundary (Extract Class / Move Method) — and drop the per-method locals. Rule 2 licenses an
   alias *within* one method; it never licenses the same alias in four. Only hold a reference that cannot be rebound
   underneath you, and verify that before relying on it.
6. **Never alias to fit the 100-character line limit.** Wrap the line instead. A formatting problem gets a formatting
   fix.

## Cases that always justify a local

- **Explaining variable** — the name states what a compound expression *means*:
  `eligible = user.age >= 18 and not user.banned`. This is the strongest case and the one Clean Code's G19 is about.
- **Deliberate snapshot** — binding a value that may be rebound underneath you, so iteration or a sequence of reads sees
  one consistent object. Here the alias *is* the semantics; say so in a comment.
- **Hot-loop hoisting** — Python attribute access is a real dict lookup plus descriptor protocol, so lifting `self.x`
  out of a tight loop is legitimate. Only with a measurement; premature everywhere else.

## Python specifics

- `self.` is explicit **by design**. Aliasing it away fights the language, and loses provenance: `state.gateway = x`
  does not say whose state is being mutated, while `self._app.state.gateway = x` does. When publishing onto a shared
  object is the point of the method, keep that visible.
- There is no destructuring culture here as there is in JS/TS. `a, b = obj.a, obj.b` at the top of a method is not
  idiomatic Python; do not import the habit.
- Aliases go stale. If the underlying attribute is rebound, the alias still points at the old object and writes land in
  the discarded one.

## Why these and not "extract everything"

Every name is working memory. An alias is the smallest possible abstraction, and by Ousterhout's test
(*A Philosophy of Software Design*) an abstraction must hide more complexity than it adds — a pure alias hides none.
Clean Code's "extract until you drop" instinct pushes the other way; where the two conflict in this repo, the test above
wins.

## Worked example

`bundlemcp/main/composition_root.py` (`CompositionRoot`) is the reference case, and it contains the one comparison worth
internalising — two aliases that look identical and land on opposite sides of the line:

```python
state = self._app.state        # a two-hop reach  -> rule 2 would allow it
settings = self._settings      # one hop, a synonym -> rule 1 rejects it
```

Both names are synonyms; neither adds meaning. Only the first collapses a reach, and that — not the usage count — is
what separates them under rules 1 and 2. Six uses of `self._settings` still would not qualify.

But `state` appeared in four methods, which is rule 5's signal, and rule 5 outranks rule 2. So the resolution was
neither alias: `CompositionRoot` holds `self._state = app.state` once in `__init__` (verified safe — Starlette assigns
`app.state` exactly once and never rebinds it) and every method uses it directly.

### The one exception, and what makes it one

`_compose()` in the same class opens with the two aliases rule 1 rejects:

```python
settings = self._settings
overrides = self._overrides
```

They are there on purpose, and the conditions are narrow enough to state:

- **One method, not four.** Rule 5 does not fire, so this cannot spread.
- **A build sequence, not logic.** `_compose()` is nothing but construction, with many uses of `settings` and
  `overrides`. In keyword arguments such as `settings=settings, clock=clock` the alias makes the wiring legible as a
  table; `settings=self._settings` next to fifteen local names reads as though it came from somewhere else.
- **Nothing rebinds either attribute** for the life of the object.

This is the whole exception. Anywhere the method also *decides* something, rule 1 applies as written: spell out
`self._settings`. If you find yourself writing this preamble in a second method, that is rule 5 and the answer is a
different seam, not another alias.
