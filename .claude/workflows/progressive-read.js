export const meta = {
  name: 'progressive-read',
  description: 'Check that a text makes sense read cold, block by block: each fresh reader sees only the blocks before the one it judges',
  whenToUse: 'Before publishing a blog post or a docs page: finds where a reader without context loses the thread. Pass the Markdown as args.text.',
  phases: [
    { title: 'Intent', detail: 'one agent with the full text states what each block should leave the reader with' },
    { title: 'Read', detail: 'one fresh reader per block, given only the blocks before it' },
    { title: 'Judge', detail: 'compare what each reader understood with the intent' },
  ],
}

// How it works
//
// The text is split into blocks: a paragraph, a list, a table or a code block, with a heading
// joined to the block under it. The title and description from the frontmatter form block 0,
// because a reader meets them first. HTML comments are dropped, and so is everything from the
// `stopAtHeading` heading on (default "Sources").
//
// Reader i is a fresh agent that sees blocks 0..i-1 as "what you have read so far" and block i as
// "the next part", and nothing else: no brief, no title of the project, no other context. It says
// what it understood and where it got lost. A judge then compares that with the intent, which an
// agent with the full text wrote for every block. A block fails when a reader with only the text
// before it cannot get the intended point.
//
// Readers do not depend on each other (each gets a prefix of the original text), so they run in
// parallel. After fixing failed blocks, run the workflow again on the new text: a changed block
// changes what every later reader sees.
//
// args:
//   text           required, the Markdown, frontmatter included
//   audience       who the reader is (default: a developer who uses AI assistants daily and knows
//                  little about MCP internals)
//   stopAtHeading  heading text where checking stops (default "Sources"); "" checks to the end
//   fromBlock      first block to read and judge (default 0); earlier blocks are still context

const text = args && args.text
if (!text) throw new Error('progressive-read needs args.text: the Markdown to check')
const audience = (args && args.audience) ||
  'a developer who uses AI assistants every day and knows little about MCP (the Model Context Protocol) internals'
const stopAt = args && typeof args.stopAtHeading === 'string' ? args.stopAtHeading : 'Sources'
const fromBlock = (args && args.fromBlock) || 0

function frontmatter(source) {
  const m = source.match(/^---\n([\s\S]*?)\n---\n?/)
  if (!m) return { fields: {}, body: source }
  const fields = {}
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^(\w+):\s*(.*)$/)
    if (kv) fields[kv[1]] = kv[2].replace(/^["']|["']$/g, '')
  }
  return { fields, body: source.slice(m[0].length) }
}

function splitBlocks(body) {
  const lines = body.replace(/<!--[\s\S]*?-->/g, '').split('\n')
  const blocks = []
  let current = []
  let fenced = false
  const flush = () => {
    const block = current.join('\n').trim()
    if (block) blocks.push(block)
    current = []
  }
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced
    if (!fenced && line.trim() === '') { flush(); continue }
    current.push(line)
  }
  flush()
  // a heading on its own belongs to the block under it
  const joined = []
  for (let i = 0; i < blocks.length; i++) {
    if (/^#{1,6}\s/.test(blocks[i]) && !blocks[i].includes('\n') && i + 1 < blocks.length) {
      joined.push(`${blocks[i]}\n\n${blocks[i + 1]}`)
      i++
    } else joined.push(blocks[i])
  }
  if (!stopAt) return joined
  const cut = joined.findIndex(b => new RegExp(`^#{1,6}\\s+${stopAt}\\s*$`, 'm').test(b.split('\n')[0]))
  return cut === -1 ? joined : joined.slice(0, cut)
}

const { fields, body } = frontmatter(text)
const blocks = splitBlocks(body)
if (fields.title) {
  blocks.unshift(fields.description ? `# ${fields.title}\n\n_${fields.description}_` : `# ${fields.title}`)
}
const numbered = blocks.map((b, i) => `[[BLOCK ${i}]]\n${b}`).join('\n\n')
log(`${blocks.length} blocks; checking from block ${fromBlock}`)

const INTENT_SCHEMA = {
  type: 'object',
  properties: {
    intents: { type: 'array', items: { type: 'object', properties: {
      index: { type: 'number' },
      takeaway: { type: 'string', description: 'What a reader should understand after this block, in one or two sentences' },
      needs_known: { type: 'array', items: { type: 'string' }, description: 'Terms or ideas the block relies on that must already be clear by then' },
    }, required: ['index', 'takeaway', 'needs_known'] } },
  },
  required: ['intents'],
}

phase('Intent')
// not awaited: readers do not need the intent, only the judges do
const intentsPromise = agent(`You are the author's editor. Below is a text split into numbered blocks. For every block, say what a reader should understand after reading it (the intended takeaway, one or two sentences, concrete), and list the terms or ideas the block relies on that must already be clear to the reader at that point. Do not judge the writing; state the intent.

${numbered}`, { label: 'intent', phase: 'Intent', schema: INTENT_SCHEMA })
  .then(r => {
    const byIndex = {}
    for (const it of (r && r.intents) || []) byIndex[it.index] = it
    return byIndex
  })

const READER_SCHEMA = {
  type: 'object',
  properties: {
    understood: { type: 'string', description: 'What the next part says, in your own plain words' },
    about_so_far: { type: 'string', description: 'What you think the whole text is about, after this part' },
    followed: { type: 'string', enum: ['yes', 'partly', 'no'] },
    lost_at: { type: 'array', items: { type: 'string' }, description: 'Exact phrases you could not follow, each with why' },
    questions: { type: 'array', items: { type: 'string' }, description: 'Questions you have now that the text has not answered' },
  },
  required: ['understood', 'about_so_far', 'followed', 'lost_at', 'questions'],
}

const JUDGE_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['pass', 'partial', 'fail'] },
    gap: { type: 'string', description: 'What the reader missed or got wrong compared with the intent; empty on pass' },
    cause: { type: 'string', description: 'Why: a term not introduced yet, a missing step, an unexplained example, ambiguity, ...' },
    suggested_fix: { type: 'string', description: 'A concrete rewrite of the block, or what an earlier block must add; keep every fact, add none' },
  },
  required: ['verdict', 'gap', 'cause', 'suggested_fix'],
}

const indices = blocks.map((_, i) => i).filter(i => i >= fromBlock)

const results = await pipeline(
  indices,
  i => {
    const before = blocks.slice(0, i).join('\n\n')
    return agent(`You are ${audience}. You are reading a text for the first time, one part at a time. You have no other context: no brief, no idea who wrote it or why. Read only what is below. Use general knowledge as such a reader would, but do not fill gaps by guessing what the author meant; when something is not explained, say so.

${i === 0 ? 'This is the very beginning of the text.' : `WHAT YOU HAVE READ SO FAR:\n\n${before}`}

THE NEXT PART:

${blocks[i]}

Report what the next part says in your own words, what you think the whole text is about now, whether you could follow it, the exact phrases where you got lost, and the questions you now have.`,
      { label: `read:${i}`, phase: 'Read', schema: READER_SCHEMA })
  },
  async (reader, i) => {
    if (!reader) return null
    const intents = await intentsPromise
    const intent = intents[i] || { takeaway: '(no intent recorded)', needs_known: [] }
    const judged = await agent(`A text is being checked block by block. A fresh reader saw only the blocks before block ${i} and then block ${i}, and reported what they understood. Judge whether they got the intended point.

Intended takeaway of block ${i}: ${intent.takeaway}
Must already be clear at this point: ${intent.needs_known.join('; ') || '(nothing listed)'}

Block ${i}:
${blocks[i]}

Blocks before it (all the reader had):
${blocks.slice(0, i).join('\n\n') || '(none, this is the start)'}

Reader's report:
${JSON.stringify(reader, null, 2)}

Verdict: pass if the reader got the intended point without guessing; partial if they got the gist but missed something the text relies on later; fail if they missed or misread the point. Name the cause and suggest a concrete fix that keeps every fact and adds none. When the real fix belongs in an earlier block (a term used before it is introduced), say which.`,
      { label: `judge:${i}`, phase: 'Judge', schema: JUDGE_SCHEMA })
    return judged && {
      index: i,
      excerpt: blocks[i].slice(0, 160),
      takeaway: intent.takeaway,
      verdict: judged.verdict,
      gap: judged.gap,
      cause: judged.cause,
      suggested_fix: judged.suggested_fix,
      reader_followed: reader.followed,
      reader_understood: reader.understood,
      reader_lost_at: reader.lost_at,
      reader_questions: reader.questions,
      reader_about_so_far: reader.about_so_far,
    }
  },
)

const checked = results.filter(Boolean).sort((a, b) => a.index - b.index)
const skipped = indices.length - checked.length
if (skipped) log(`${skipped} block(s) got no verdict (agent skipped or failed); they are listed as unchecked`)
const count = v => checked.filter(r => r.verdict === v).length
const firstProblem = checked.find(r => r.verdict !== 'pass')

return {
  blocks: blocks.length,
  checked: checked.length,
  unchecked: indices.filter(i => !checked.some(r => r.index === i)),
  pass: count('pass'),
  partial: count('partial'),
  fail: count('fail'),
  first_problem: firstProblem ? firstProblem.index : null,
  results: checked,
}
