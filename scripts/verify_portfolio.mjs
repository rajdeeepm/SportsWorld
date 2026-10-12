// Integrity checks for shipped research data and a server-free public build.
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const pub=path.join(repo,'portfolio');
const data=JSON.parse(readFileSync(path.join(pub,'snapshot.json'),'utf8'));
const raw=gunzipSync(Buffer.from(readFileSync(path.join(pub,'replay-inputs.b64'),'utf8').trim(),'base64'));
assert.equal(createHash('sha256').update(raw).digest('hex'),data.input_sha256,'Replay input content hash');
assert.equal(data.teams.length,32);
assert.equal(new Set(data.teams.map(t=>t.team_id)).size,32);
assert.equal(data.regular_games,272);
assert.equal(data.as_of,'2025-11-01T12:00:00+00:00');
let scenarioCount=0;
function checkTeam(t) {
  assert.equal(t.games,17);
  assert.equal(t.win_hist.length,18);
  assert.equal(t.win_hist.reduce((a,b)=>a+b,0),data.draws);
  assert.ok(t.win_hist.every(n=>Number.isInteger(n)&&n>=0));
  assert.ok(t.wins_p05<=t.expected_wins&&t.expected_wins<=t.wins_p95);
  assert.ok(t.playoffs>=0&&t.playoffs<=1);
  assert.ok(Math.abs(t.win_hist.reduce((s,n,w)=>s+n*w,0)/data.draws-t.expected_wins)<=.0051,'Expected wins agree with histogram');
}
for(const team of data.teams) {
  checkTeam(team);checkTeam(team.fast);
  const variants=data.scenarios[team.team_id];
  assert.deepEqual(Object.keys(variants).sort(),['loss','stronger','weaker','win']);
  for(const [kind,s] of Object.entries(variants)) {
    checkTeam(s.team);scenarioCount++;
    assert.ok(s.wins_delta_se>=0&&Number.isFinite(s.wins_delta_se));
    assert.ok(Math.abs((s.team.expected_wins-team.expected_wins)-s.wins_delta)<.011,'Branch delta agrees with before/after');
    if(kind==='stronger'||kind==='win')assert.ok(s.wins_delta>=0,'Positive intervention increases team wins');
    if(kind==='weaker'||kind==='loss')assert.ok(s.wins_delta<=0,'Negative intervention decreases team wins');
  }
}
assert.equal(scenarioCount,128);
for(const summary of data.research.summary) for(const mode of ['dynamic','fast']) {
  const rows=data.research.rows.filter(r=>r.mode===mode&&r.checkpoint===summary.checkpoint);
  assert.deepEqual(rows.map(r=>r.season).sort(),[2021,2022,2023,2024,2025]);
  assert.equal(summary[mode].coverage,rows.reduce((s,r)=>s+r.wins_90_coverage,0)/rows.length);
  assert.ok(Math.abs(summary[mode].mae-rows.reduce((s,r)=>s+r.wins_mae,0)/rows.length)<1e-12);
}
const html=readFileSync(path.join(pub,'index.html'),'utf8');
const js=readFileSync(path.join(pub,'app.js'),'utf8');
assert.ok(!/fetch\(|WebSocket|localhost|127\.0\.0\.1|\/api\//.test(js),'Public interactions require no backend');
for(const match of html.matchAll(/(?:href|src)="\.\/([^"#]+)"/g))assert.ok(existsSync(path.join(pub,match[1])),`Local asset ${match[1]}`);
const script=readFileSync(path.join(pub,'snapshot-data.js'),'utf8');
assert.deepEqual(JSON.parse(script.slice('window.SPORTSWORLD_SNAPSHOT='.length).trim().replace(/;$/,'')),data,'Classic-script snapshot matches downloadable JSON');
const config=JSON.parse(readFileSync(path.join(pub,'vercel.json'),'utf8'));
assert.ok(config.redirects.some(r=>r.has?.[0]?.value==='www.worldofsports.tech'));
console.log(`PASS: 32 teams, ${scenarioCount} saved branches, 40 historical evaluation rows, content hash, local assets, no backend dependencies.`);
