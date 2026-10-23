export const meta = {
  name: 'make',
  description: 'Write one section file from a brief, loop on bs.py check, have the checker read it, then build the workspace',
  whenToUse: 'a converted workspace needs a process map, an AI layer, a document or an inventory. Args: {ws, section, name, brief}',
  phases: [
    { title: 'Author', detail: 'the author agent writes <section>/<name> with its skill; bs.py check loop, at most 3 rounds' },
    { title: 'Review', detail: 'the checker agent reads what no rule can decide; the author answers each finding' },
    { title: 'Build', detail: 'bs.py build, then bs.py status: every required element fulfilled' },
  ],
}

// args: {ws: 'work/<engagement>', section, name: 'end-to-end', brief: 'what the file should cover, and for whom'}
const SECTIONS = {
  'process-map': { ext: '.json', skill: 'process-map', page: (n) => `out/process-map/${n}.html` },
  'process-map-ai-opportunity': { ext: '.json', skill: 'process-map-ai-opportunity', page: (n) => `out/process-map-ai-opportunity/${n}.html` },
  document: { ext: '.md', skill: 'document', page: (n) => `out/document/${n}.html` },
  inventory: { ext: '.json', skill: 'data-received', page: () => 'out/data-received.html and out/systems-inventory.html' },
}
const { ws, section, name, brief } = args || {}
if (!ws || !SECTIONS[section] || !/^[a-z0-9][a-z0-9-]{1,47}$/.test(name || '') || !brief) {
  throw new Error(`make.js needs args {ws, section, name, brief}: section is one of ${Object.keys(SECTIONS).join(', ')}, name like "end-to-end"`)
}
const s = SECTIONS[section]
const file = `${section}/${name}${s.ext}`
const page = s.page(name)
const skill = `.claude/skills/${s.skill}/SKILL.md`
const q = (v) => `'${String(v).replace(/'/g, `'\\''`)}'`

const FINDINGS = {
  type: 'object',
  properties: {
    exit: { type: 'integer' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: { where: { type: 'string' }, rule: { type: 'string' }, message: { type: 'string' }, fix: { type: 'string' } },
        required: ['where', 'rule', 'message', 'fix'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['exit', 'findings', 'summary'],
}
const list = (r) => r.findings.map((f) => `- ${f.where} ${f.rule}: ${f.message} -> ${f.fix}`).join('\n')
const checkPrompt = `From the repo root, run python3 bs.py check ${q(ws)}. Report its exit code and every ERROR and WARN finding (where = file and pointer or line, rule id, message, the -> fix hint). summary: the last line. Change nothing.`

phase('Author')
let check = null
for (let round = 1; round <= 3; round++) {
  const task = round === 1
    ? `Write ${ws}/${file} with the skill ${skill} (read it first, then the README it names). Brief: ${brief}
Read ${ws}/records/. Fulfil every required element the skill lists. Loop on python3 bs.py check ${q(ws)} until it exits 0.`
    : `python3 bs.py check ${q(ws)} still fails. Fix ${ws}/${file} with the skill ${skill}, then run check again:\n${list(check)}`
  await agent(task, { label: `author ${file}, round ${round}`, phase: 'Author', agentType: 'author' })
  check = await agent(checkPrompt, { label: `check, round ${round}`, phase: 'Author', schema: FINDINGS, effort: 'low' })
  if (check && check.exit === 0) break
}
if (!check || check.exit !== 0) {
  log('bs.py check still fails after 3 rounds: nothing is built')
  return { file, done: false, stage: 'check', check }
}

phase('Review')
const review = await agent(
  `Review ${ws}/${file} against ${ws}/records/ with your duties: grounded node titles, absent needles, named AI items, edges, UNCHECKED record files, None found cards, order clarifications, agentic versions with systems: [], names where roles belong (every duty in .claude/agents/checker.md). Report each finding with where (file and pointer or line), rule (the duty), message and the smallest fix. exit: 0 with no findings, else 1.`,
  { label: `checker ${file}`, phase: 'Review', schema: FINDINGS, agentType: 'checker' },
)
let answers = null
if (review && review.findings.length) {
  answers = await agent(
    `The checker reports these findings on ${ws}/${file}. Answer each one: fix it, or say why the records support the file as written. Then loop on python3 bs.py check ${q(ws)} until it exits 0.\n${list(review)}`,
    { label: `answer the checker on ${file}`, phase: 'Review', agentType: 'author' },
  )
  check = await agent(checkPrompt, { label: 'check after review', phase: 'Review', schema: FINDINGS, effort: 'low' })
  if (!check || check.exit !== 0) return { file, done: false, stage: 'review', review, answers, check }
}

phase('Build')
const build = await agent(
  `From the repo root, run python3 bs.py build ${q(ws)}, then python3 bs.py status ${q(ws)}. Report the build's exit code, each ERROR line it prints (where = the page, rule, message, the -> fix hint), and each MISSING line of status as a finding with rule "missing". summary: the status line for ${page}, then its State and Next step lines. Change nothing.`,
  { label: 'build and status', phase: 'Build', schema: FINDINGS, effort: 'low' },
)
log(build ? build.summary : 'the build step returned nothing')
return { file, page, done: Boolean(build && build.exit === 0), review, answers, build }
