let questions=[], currentIndex=0, currentMode='practice', lastResult=null;
let declaredLevel='Foundation', detectedLevel='Foundation', currentSubject='Python', questionType='mixed', diagnosticMode=false;
const $=id=>document.getElementById(id);

async function loadCatalog(){
  const d=await (await fetch('/api/catalog')).json();
  $('subjectSelect').innerHTML=d.subjects.map(s=>`<option>${escapeHtml(s)}</option>`).join('');
  $('levelSelect').innerHTML=d.levels.map(l=>`<option>${escapeHtml(l)}</option>`).join('');
  $('subjectSelect').value=currentSubject; $('levelSelect').value=declaredLevel;
  $('subjectList').innerHTML=d.subjects.map(s=>`<span class="subject-pill">${escapeHtml(s)}</span>`).join('');
}
async function loadQuestions(){
  currentSubject=$('subjectSelect').value; declaredLevel=$('levelSelect').value; questionType=$('typeSelect').value;
  const d=await (await fetch(`/api/adaptive?subject=${encodeURIComponent(currentSubject)}&declared_level=${encodeURIComponent(declaredLevel)}&type=${encodeURIComponent(questionType)}&count=8`)).json();
  questions=d.questions; detectedLevel=d.detected_level||declaredLevel; currentIndex=0; $('detectedLevel').textContent=detectedLevel; $('declaredLevel').textContent=declaredLevel; renderQuestion(); updateDashboard(); checkStatus();
}
async function checkStatus(){const d=await (await fetch('/api/status')).json();$('aiStatus').textContent=d.ai_enabled?'🟢 Live AI + Adaptive':'🟡 Local Adaptive Engine';$('aiStatus').title=d.message;}
function modeQuestion(q){if(currentMode==='devil')return `Challenge your reasoning: “${q.question}” Give a claim, evidence, and a counterexample.`;if(currentMode==='teach')return `Teach this to a beginner: “${q.question}” Use a simple example and explain why it works.`;return q.question;}
function renderQuestion(){
  if(!questions.length){$('questionText').textContent='No questions found. Choose another subject or type.';return;}
  const q=questions[currentIndex];
  $('topicTag').textContent=q.subject; $('difficultyTag').textContent=q.level; $('typeTag').textContent=q.type==='mcq'?'MCQ':'Reasoning'; $('questionNumber').textContent=`Question ${currentIndex+1} of ${questions.length}`;
  $('questionText').textContent=modeQuestion(q); $('answer').value=''; $('result').classList.add('hidden');
  const box=$('mcqOptions'); box.innerHTML='';
  if(q.type==='mcq'){
    box.classList.remove('hidden');
    q.options.forEach((opt,i)=>{const label=document.createElement('label');label.className='option';label.innerHTML=`<input type="radio" name="mcq" value="${i}"><span>${String.fromCharCode(65+i)}. ${escapeHtml(opt)}</span>`;box.appendChild(label);});
    $('answer').classList.add('hidden');
  }else{box.classList.add('hidden');$('answer').classList.remove('hidden');}
}
function setMode(m){currentMode=m;document.querySelectorAll('.mode').forEach(b=>b.classList.toggle('active',b.dataset.mode===m));$('modeTitle').textContent=m==='practice'?'🎯 Adaptive Socratic Practice':m==='devil'?'⚔️ Devil’s Advocate':'👩‍🏫 Teach-Back';renderQuestion();}
async function analyze(){
  const q=questions[currentIndex]; if(!q)return;
  let answer=$('answer').value.trim(), selected=-1;
  if(q.type==='mcq'){const selectedEl=document.querySelector('input[name="mcq"]:checked');if(!selectedEl){alert('Please choose one option.');return;}selected=+selectedEl.value;answer=q.options[selected];}
  if(q.type==='reasoning' && answer.length<12){alert('Please give a little more reasoning so the tutor can evaluate your thinking.');return;}
  const confidence=+$('confidenceSlider').value;
  const res=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:q.id,answer,selected_option:selected,question_type:q.type,confidence,mode:currentMode,declared_level:declaredLevel})});
  const data=await res.json(); if(!res.ok){alert(data.error||'Could not analyze.');return;} lastResult=data;
  detectedLevel=data.detected_level||detectedLevel; $('detectedLevel').textContent=detectedLevel; $('resultLevel').textContent=detectedLevel;
  $('score').textContent=data.score; $('analysisText').textContent=data.analysis; $('fingerprint').textContent=data.misconception; $('confidenceMessage').textContent=data.confidence_message; $('followup').textContent=data.next_step; $('socraticQuestion').textContent=data.socratic_question||'What evidence supports your explanation?'; $('strengths').innerHTML=(data.strengths||[]).map(x=>`<li>${escapeHtml(x)}</li>`).join(''); $('result').classList.remove('hidden'); updateDashboard();
}
async function hint(){const q=questions[currentIndex];const d=await (await fetch('/api/hint',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:q.id})})).json();$('result').classList.remove('hidden');$('analysisText').textContent='💡 '+d.hint;$('score').textContent='—';$('strengths').innerHTML='<li>Hint requested without revealing the answer.</li>';}
function nextQuestion(){ if(diagnosticMode && currentIndex===questions.length-1){ diagnosticMode=false; alert('Level check complete. The tutor will now prepare adaptive questions using your detected level.'); loadQuestions(); return; } currentIndex=(currentIndex+1)%questions.length;renderQuestion(); }
async function updateDashboard(){const d=await (await fetch('/api/dashboard')).json();$('questionCount').textContent=d.total;$('accuracy').textContent=d.accuracy+'%';$('confidence').textContent=d.confidence+'%';$('difficulty').textContent=d.detected_level;$('detectedLevel').textContent=d.detected_level;$('misconceptions').innerHTML=d.misconceptions.length?d.misconceptions.map(m=>`<div>⚠️ <b>${escapeHtml(m)}</b></div>`).join(''):'<div class="empty">No recurring misconception yet.</div>';$('knowledgeMap').innerHTML=d.knowledge_map.length?d.knowledge_map.map(x=>`<div class="knowledge-item"><b>${escapeHtml(x.topic)}</b> — ${x.score}%<div class="bar"><div class="fill" style="width:${x.score}%"></div></div></div>`).join(''):'<p class="muted">Complete attempts to build your map.</p>';}
async function generatePractice(){const d=await (await fetch('/api/insights')).json();const subject=d.weakest==='—'?currentSubject:d.weakest;const level=d.detected_level||detectedLevel;const g=await (await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subject,level,misconception:d.weakest})})).json();$('practiceQuestion').innerHTML=`<b>${escapeHtml(g.question)}</b><br><small>${escapeHtml(g.why_it_matters||'')}</small><br><em>Challenge: ${escapeHtml(g.challenge||'')}</em>`;}
async function showReplay(){const p=$('replayPanel');p.classList.toggle('hidden');if(p.classList.contains('hidden'))return;const d=await (await fetch('/api/replay')).json();$('replayList').innerHTML=d.length?d.map(r=>`<div class="replay-item"><b>${escapeHtml(r.topic)}</b> · ${escapeHtml(r.question_type||'reasoning').toUpperCase()} · <strong>${r.ai_score}/100</strong> · ${r.correct?'✓':'✗'}<p>${escapeHtml(r.answer)}</p><small>Declared ${escapeHtml(r.declared_level||'—')} → Detected ${escapeHtml(r.detected_level||'—')} · Confidence ${r.confidence}% · ${escapeHtml(r.created_at)}</small></div>`).join(''):'<p class="muted">No attempts yet.</p>';}
async function showInsights(){const p=$('insightsPanel');p.classList.toggle('hidden');if(p.classList.contains('hidden'))return;const d=await (await fetch('/api/insights')).json();$('profileSummary').textContent=d.summary;$('recommendations').innerHTML=(d.recommendations||[]).map(x=>`<div class="nextbox">💡 ${escapeHtml(x)}</div>`).join('');}
async function resetProgress(){if(!confirm('Reset all learning history?'))return;await fetch('/api/reset',{method:'POST'});lastResult=null;detectedLevel=declaredLevel;updateDashboard();}
function escapeHtml(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}
async function runDiagnostic(){ currentSubject=$('subjectSelect').value; declaredLevel=$('levelSelect').value; diagnosticMode=true; const d=await (await fetch(`/api/diagnostic?subject=${encodeURIComponent(currentSubject)}`)).json(); questions=d.questions; questionType='mcq'; currentIndex=0; $('typeSelect').value='mcq'; $('detectedLevel').textContent='Assessing…'; alert('Level assessment: answer 5 questions without worrying about your selected level. Your performance will determine the adaptive level.'); renderQuestion(); }
$('diagnosticBtn').addEventListener('click',runDiagnostic);$('startBtn').addEventListener('click',loadQuestions);$('subjectSelect').addEventListener('change',loadQuestions);$('levelSelect').addEventListener('change',()=>{$('declaredLevel').textContent=$('levelSelect').value;});$('typeSelect').addEventListener('change',loadQuestions);document.querySelectorAll('.mode').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));$('confidenceSlider').addEventListener('input',e=>$('confidenceValue').textContent=e.target.value+'%');$('analyzeBtn').addEventListener('click',analyze);$('hintBtn').addEventListener('click',hint);$('nextBtn').addEventListener('click',nextQuestion);$('generateBtn').addEventListener('click',generatePractice);$('replayBtn').addEventListener('click',showReplay);$('insightsBtn').addEventListener('click',showInsights);$('resetBtn').addEventListener('click',resetProgress);
(async()=>{await loadCatalog();await loadQuestions();})();
