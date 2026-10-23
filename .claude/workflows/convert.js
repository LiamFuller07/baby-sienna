export const meta = {
  name: 'convert',
  description: 'Convert every new input of a workspace into records/<ID>.json, then run bs.py check',
  whenToUse: 'bs.py status shows NOT CONVERTED inputs. Args: {ws, captured, notes?}',
  phases: [
    { title: 'Status', detail: 'bs.py status --json, then one id and header per NOT CONVERTED input' },
    { title: 'Convert', detail: 'bs.py convert for a format it reads, the converter agent otherwise; at most 4 at once' },
    { title: 'Check', detail: 'bs.py check, with one repair round for a record that fails' },
  ],
}

// args: {ws: 'work/<engagement>', captured: 'YYYY-MM-DD', notes: 'what each file is, who sent it, when'}
// captured is the date the material was received, used for any input the notes give no date. It is never a file date.
const ws = args && args.ws
if (!ws) throw new Error('convert.js needs args.ws, the workspace folder, e.g. {ws: "work/client-a", captured: "2026-09-01"}')
const captured = (args && args.captured) || ''
const notes = (args && args.notes) || ''
const LIMIT = 4

const PLAN = {
  type: 'object',
  properties: {
    inputs: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string', description: 'inputs/<path>, as status prints it' },
          id: { type: 'string' },
          kind: { enum: ['sheet', 'document', 'transcript', 'web'] },
          title: { type: 'string' },
          captured: { type: 'string', description: 'YYYY-MM-DD, or empty when nobody gave a date' },
          detail: { type: 'string' },
          url: { type: 'string' },
          partial: { type: 'boolean' },
          legacy: { type: 'boolean' },
          reader: { enum: ['bs.py', 'converter', 'none'], description: 'none: a container or anything that is not an input' },
        },
        required: ['file', 'id', 'kind', 'title', 'captured', 'reader'],
      },
    },
    questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['inputs', 'questions'],
}

const RESULT = {
  type: 'object',
  properties: {
    file: { type: 'string' },
    id: { type: 'string' },
    exit: { type: 'integer' },
    records: { type: 'integer' },
    unchecked: { type: 'boolean' },
    note: { type: 'string' },
  },
  required: ['file', 'id', 'exit', 'note'],
}

const CHECK = {
  type: 'object',
  properties: {
    exit: { type: 'integer' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: { level: { type: 'string' }, rule: { type: 'string' }, file: { type: 'string' }, message: { type: 'string' } },
        required: ['level', 'rule', 'file', 'message'],
      },
    },
    status: { type: 'string', description: 'the State and Next step lines of bs.py status' },
  },
  required: ['exit', 'findings', 'status'],
}

const q = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`

function convertCommand(i) {
  return [
    'python3 bs.py convert', q(ws), q(i.file), '--id', q(i.id), '--kind', i.kind, '--title', q(i.title), '--captured', q(i.captured),
    i.detail ? `--detail ${q(i.detail)}` : '', i.url ? `--url ${q(i.url)}` : '', i.partial ? '--partial' : '', i.legacy ? '--legacy' : '',
  ].filter(Boolean).join(' ')
}

function byHand(i, why) {
  return `Convert ${ws}/${i.file} into ${ws}/records/${i.id}.json by hand, with the convert skill (.claude/skills/convert/SKILL.md). ${why}
Header: id ${i.id}, kind ${i.kind}, title ${JSON.stringify(i.title)}, captured ${i.captured}${i.detail ? `, detail ${JSON.stringify(i.detail)}` : ''}${i.url ? `, url ${i.url}` : ''}${i.partial ? ', coverage partial' : ''}${i.legacy ? ', legacy' : ''}.
Every unit verbatim, in reading order, with its locator and context. Then run python3 bs.py check ${q(ws)} and report the record count, and whether rec-5 reports the file UNCHECKED.`
}

async function convertOne(i) {
  if (i.reader === 'bs.py') {
    const r = await agent(
      `From the repo root, run exactly:\n${convertCommand(i)}\nReport its exit code and the record count it prints. Change nothing else.`,
      { label: `convert ${i.id}`, phase: 'Convert', schema: RESULT, effort: 'low' },
    )
    if (!r || r.exit !== 2) return r
  }
  return agent(byHand(i, i.reader === 'bs.py' ? 'bs.py convert has no reader for it (exit 2).' : 'Its format is not in its kind\'s read list.'), {
    label: `converter ${i.id}`, phase: 'Convert', schema: RESULT, agentType: 'converter',
  })
}

phase('Status')
const plan = await agent(
  `From the repo root, run: python3 bs.py status ${q(ws)} --json
For each item whose state is NOT CONVERTED, propose the record header, with the convert skill (.claude/skills/convert/SKILL.md) and formats/citation-types.json:
- id: unique in the workspace and unused in ${ws}/records/; by convention WB<n> for a sheet, D<n> a document, T<n> a transcript, WEB<n> a web page.
- kind, from the extension and a look at the file. title: what it is, in plain words. detail: one line (who provided it, size, version, how speakers were pseudonymised); roles, never names.
- captured: from these notes when they date the file, else ${captured ? `"${captured}"` : 'empty'}.
- url for a web page; partial when the file is an excerpt; legacy when the material was already old when it arrived.
- reader: "bs.py" when the extension is in kinds.<kind>.read, "converter" when it is in kinds.<kind>.unchecked, "none" for a .zip or anything that is not an input.
List in questions what a person must answer: a missing date or url, a container to unpack, a transcript that names people.
Notes from the person: ${notes || '(none)'}
Read only what you need to name each file. Write nothing.`,
  { label: 'status and plan', phase: 'Status', schema: PLAN },
)
if (!plan) throw new Error('the status step returned nothing')

const ready = plan.inputs.filter((i) => i.reader !== 'none' && /^\d{4}-\d{2}-\d{2}$/.test(i.captured))
const held = plan.inputs.filter((i) => !ready.includes(i))
log(`${plan.inputs.length} input(s) not converted: ${ready.length} to convert, ${held.length} held for a person`)

phase('Convert')
const queue = ready.slice()
const converted = []
await parallel(
  Array.from({ length: Math.min(LIMIT, queue.length) }, () => async () => {
    while (queue.length) {
      const i = queue.shift()
      const r = await convertOne(i)
      converted.push(r || { file: i.file, id: i.id, exit: 2, note: 'the agent returned nothing' })
    }
  }),
)

phase('Check')
const checkPrompt = `From the repo root, run python3 bs.py check ${q(ws)} and then python3 bs.py status ${q(ws)}. Report the check's exit code, every finding (level, rule, file, message), and the status's State and Next step lines. Change nothing.`
let check = await agent(checkPrompt, { label: 'check', phase: 'Check', schema: CHECK, effort: 'low' })
const failing = check
  ? ready.filter((i) => check.findings.some((f) => f.level === 'ERROR' && f.file.startsWith(`records/${i.id}.json`)))
  : []
if (failing.length) {
  log(`${failing.length} record file(s) fail a check: converting them again`)
  await parallel(
    failing.map((i) => () =>
      agent(
        `${byHand(i, 'Its record file fails bs.py check:')}\n${check.findings.filter((f) => f.file.startsWith(`records/${i.id}.json`)).map((f) => `${f.rule} ${f.message}`).join('\n')}\nRecord files are never edited by hand: delete ${ws}/records/${i.id}.json and convert again under the same id (python3 bs.py convert when it reads the format).`,
        { label: `repair ${i.id}`, phase: 'Check', schema: RESULT, agentType: 'converter' },
      ),
    ),
  )
  check = await agent(checkPrompt, { label: 'check again', phase: 'Check', schema: CHECK, effort: 'low' })
}

return {
  workspace: ws,
  converted,
  held: held.map((i) => ({ file: i.file, reason: i.reader === 'none' ? 'not an input: a person unpacks it' : 'no captured date' })),
  questions: plan.questions,
  check,
}
