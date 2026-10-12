const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent = (n) => `${(100*n).toFixed(1)}%`;
const signed = (n) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(2)}`;
const number = (n) => n.toLocaleString('en-US');
let data, teamId = '8', model = 'dynamic', scenario = 'baseline';
const pages = ['explorer', 'research', 'method', 'reproduce'];

function route(focus = false) {
  const page = location.hash.slice(1).split('?')[0] || 'explorer';
  const selected = pages.includes(page) ? page : 'explorer';
  if (data) pages.forEach((id) => { $(`#${id}`).hidden = id !== selected; });
  document.querySelectorAll('[data-page]').forEach((a) => {
    if (a.dataset.page === selected) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  document.title = `SportsWorld: ${({'explorer':'Season Explorer','research':'Research Evidence','method':'Model & Limitations','reproduce':'Reproduce the Work'})[selected]}`;
  if (data && selected === 'explorer') renderExplorer();
  if (focus) { $('#main').focus({preventScroll: true}); window.scrollTo({top:0,behavior:'instant'}); }
}

function chart(baseline, branch, name) {
  const counts = baseline.win_hist;
  const alt = branch?.win_hist;
  const width = Math.max(280, $('#distribution').clientWidth || 740), height = 255, left = 46, right = 8, top = 18, bottom = 38;
  const innerW = width-left-right, innerH = height-top-bottom;
  const peak = Math.max(...counts,...(alt ?? []))/data.draws;
  const maximum = Math.max(.1, Math.ceil(peak/.05)*.05);
  const step = innerW/counts.length;
  const barW = step*(alt ? .36 : .66);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="distribution-title distribution-description"><title id="distribution-title">${escape(name)} final-win distribution</title><desc id="distribution-description">${alt ? 'Baseline and saved scenario' : 'Baseline'} shares across ${data.draws} simulated seasons. Exact counts are in the expandable table below.</desc>`;
  for(let k=0;k<=4;k++) {
    const p = maximum*k/4, y=top+innerH*(1-p/maximum);
    svg+=`<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" stroke="#203655"/><text x="${left-9}" y="${y+4}" text-anchor="end">${Math.round(p*100)}%</text>`;
  }
  counts.forEach((c,w)=> {
    const x=left+w*step+step*.17, h=c/data.draws/maximum*innerH;
    svg+=`<rect x="${x}" y="${top+innerH-h}" width="${barW}" height="${h}" rx="2" fill="${alt ? '#8da5c4' : '#73b6ff'}"><title>${w} wins: ${number(c)} baseline draws</title></rect>`;
    if(alt) {
      const ah=alt[w]/data.draws/maximum*innerH;
      svg+=`<rect x="${x+barW+1}" y="${top+innerH-ah}" width="${barW}" height="${ah}" rx="2" fill="#f4c94e"><title>${w} wins: ${number(alt[w])} saved scenario draws</title></rect>`;
    }
    if((w% (width < 400 ? 4 : 2)===0 && w < (width < 400 ? 16 : 17)) || w===17) svg+=`<text x="${left+(w+.5)*step}" y="${height-20}" text-anchor="middle">${w}</text>`;
  });
  svg+=`<text x="${left+innerW/2}" y="${height-1}" text-anchor="middle">Final regular-season wins</text></svg>`;
  $('#distribution').innerHTML=svg;
  $('#legend').innerHTML=alt ? '<span><i style="background:#8da5c4"></i>Baseline</span><span><i class="scenario"></i>Saved scenario</span>' : '<span><i></i>Baseline distribution</span>';
  $('#histogram-table').innerHTML=counts.map((c,w)=>`<tr><th scope="row">${w}</th><td>${number(c)}</td><td>${alt ? number(alt[w]) : 'Not selected'}</td></tr>`).join('');
}

function renderExplorer() {
  const team=data.teams.find(t=>t.team_id===teamId) ?? data.teams[0];
  teamId=team.team_id;
  const base=model==='fast' ? team.fast : team;
  const saved=scenario==='baseline' ? null : data.scenarios[teamId]?.[scenario];
  const shown=saved ? saved.team : base;
  $('#team').value=teamId;
  $('#team-name').textContent=team.name;
  $('#team-context').textContent=`${team.division} · Record at cutoff ${team.record.wins}–${team.record.losses}${team.record.ties ? `–${team.record.ties}` : ''}`;
  const next=team.next_game;
  const opponent=next ? data.teams.find(t=>t.team_id===(next.home_id===teamId ? next.away_id : next.home_id)) : null;
  $('#team-next').textContent=next ? `Next archived matchup: ${next.home_id===teamId ? 'vs' : 'at'} ${opponent?.name ?? 'opponent'} · ${new Date(next.start).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})}` : 'No remaining archived matchup';
  $('#model-label').textContent=saved ? 'Saved correlated scenario' : model==='fast' ? 'Fixed strength' : 'Correlated strength';
  $('#expected').innerHTML=`${shown.expected_wins.toFixed(2)} <span class="unit">/ 17</span>`;
  $('#interval').textContent=`${shown.wins_p05.toFixed(0)}–${shown.wins_p95.toFixed(0)} wins`;
  $('#playoffs').textContent=percent(shown.playoffs);
  document.querySelectorAll('[data-scenario]').forEach(b=>{
    const active=b.dataset.scenario===scenario;
    b.setAttribute('aria-pressed',String(active));
    b.disabled=!next && ['win','loss'].includes(b.dataset.scenario);
  });
  document.querySelectorAll('input[name=model]').forEach(input=>{input.checked=input.value===model;});
  chart(base,saved?.team,team.name);
  const insight=$('#scenario-insight');
  if(saved) {
    const pp=(shown.playoffs-team.playoffs)*100;
    insight.innerHTML=`<p><strong>${escape(saved.label)}:</strong> expected wins ${team.expected_wins.toFixed(2)} → ${shown.expected_wins.toFixed(2)} <span class="delta">(${signed(saved.wins_delta)})</span>. Model playoff odds ${percent(team.playoffs)} → ${percent(shown.playoffs)} (${signed(pp)} percentage points).</p><p>Paired 95% Monte Carlo interval for the expected-win change: ${signed(saved.wins_delta-1.96*saved.wins_delta_se)} to ${signed(saved.wins_delta+1.96*saved.wins_delta_se)} wins. This measures simulation sampling error, not model uncertainty.</p>`;
  } else {
    insight.innerHTML=`<strong>${model==='fast' ? 'Independent outcomes at fixed ratings.' : 'Shared uncertain team strength.'}</strong> These are conditional model projections from ${new Date(data.as_of).toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'})}, not current odds. NFL ties and official tiebreak chains are approximated.`;
  }
}

function renderResearch() {
  const summaries=data.research.summary;
  $('#dynamic-coverage').textContent=percent(summaries[0].dynamic.coverage);
  $('#fast-coverage').textContent=percent(summaries[0].fast.coverage);
  $('#research-table').innerHTML=summaries.map(r=>`<tr><th scope="row">${Math.round(r.checkpoint*100)}% played</th><td>${percent(r.dynamic.coverage)}</td><td>${percent(r.fast.coverage)}</td><td>${r.dynamic.mae.toFixed(3)}</td><td>${r.fast.mae.toFixed(3)}</td></tr>`).join('');
  const rows=data.research.rows.slice().sort((a,b)=>a.season-b.season||a.checkpoint-b.checkpoint||a.mode.localeCompare(b.mode));
  $('#season-rows').innerHTML=rows.map(r=>`<tr><th scope="row">${r.season}</th><td>${Math.round(r.checkpoint*100)}%</td><td>${escape(r.mode==='dynamic'?'Correlated':'Fixed')}</td><td>${percent(r.wins_90_coverage)}</td><td>${r.wins_mae.toFixed(3)}</td></tr>`).join('');
  $('#limitations').innerHTML=data.limitations.map(x=>`<li>${escape(x)}</li>`).join('');
  const entries=[['Historical cutoff',`${data.as_of} (UTC)`],['Simulator',data.simulator],['Draws / seed',`${number(data.draws)} / ${data.seed}`],['Source code at generation',data.source_commit],['Bundled input SHA256',data.input_sha256],['Parameter source',data.parameter_source],['Regular schedule',`${data.regular_games} games; ${data.played_games} included at cutoff`],['Evaluation cohort',`${data.research.seasons.join(', ')}; ${data.research.team_seasons} team-seasons per checkpoint`]];
  $('#provenance').innerHTML=entries.map(([key,value])=>`<dt>${escape(key)}</dt><dd>${escape(value)}</dd>`).join('');
}

async function init() {
  try {
    data=window.SPORTSWORLD_SNAPSHOT;
    if(!data) throw new Error('Snapshot unavailable');
    if(data.schema_version!==1 || data.teams.length!==32 || data.draws!==10000) throw new Error('Unsupported snapshot');
    $('#team').innerHTML=data.teams.slice().sort((a,b)=>a.name.localeCompare(b.name)).map(t=>`<option value="${escape(t.team_id)}">${escape(t.name)}</option>`).join('');
    renderResearch();$('#loading').hidden=true;route();
  } catch(error) { $('#loading').hidden=true;$('#error').hidden=false; }
}
$('#retry').addEventListener('click',()=>location.reload());
$('#team').addEventListener('change',event=>{teamId=event.target.value;scenario='baseline';renderExplorer();});
document.querySelectorAll('input[name=model]').forEach(input=>input.addEventListener('change',()=>{model=input.value;scenario='baseline';renderExplorer();}));
document.querySelectorAll('[data-scenario]').forEach(button=>button.addEventListener('click',()=>{scenario=button.dataset.scenario;if(scenario!=='baseline')model='dynamic';renderExplorer();}));
window.addEventListener('resize',()=>{if(data && !$('#explorer').hidden) renderExplorer();});
window.addEventListener('hashchange',()=>route(true));
init();
