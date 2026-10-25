"use strict";
const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem("planner-session");
if (location.hash) { sessionStorage.setItem("planner-session", token); history.replaceState(null,"", "/"); }
let snapshot = null, plan = null, busy = false;
const states = {suggested:"规则建议",needs_review:"需要人工复核",no_release:"无新增版本"};
function icons(){lucide.createIcons();}
function message(text, error=false){$(error?"error":"notice").textContent=text; if(error) $("error").hidden=false;}
async function api(action, data={}){
 const res=await fetch("/api/"+action,{method:"POST",headers:{"Content-Type":"application/json","X-Planner-Token":token||""},body:JSON.stringify(data)});
 const body=await res.json();
 if(!res.ok){if(body.planInvalidated){plan=null;renderPlan();} throw new Error(body.error||"操作失败");}
 return body;
}
async function perform(fn){
 if(busy)return;busy=true;$("error").hidden=true;message("正在处理…");document.body.classList.add("busy");
 const controls=[...document.querySelectorAll("button,input,select,textarea")]; const disabled=controls.map(x=>x.disabled);controls.forEach(x=>x.disabled=true);
 try{await fn();}catch(e){message(e.message||"无法连接本地服务，请重新启动。",true);message("");}
 finally{controls.forEach((x,i)=>x.disabled=disabled[i]);busy=false;document.body.classList.remove("busy");if($("refresh"))$("refresh").disabled=!snapshot;}
}
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function renderSnapshot(){
 $("snapshot").hidden=!snapshot;$("workspace").hidden=!snapshot;$("empty").hidden=!!snapshot;
 if(!snapshot)return;
 $("path").value=snapshot.root;$("branch").textContent=snapshot.status.branch||"无分支";$("head").textContent=snapshot.head?snapshot.head.slice(0,12):"尚无提交";
 $("upstream").textContent=snapshot.status.upstream?`本地跟踪：${snapshot.status.upstream} · 领先 ${snapshot.status.ahead??"未知"} / 落后 ${snapshot.status.behind??"未知"}`:"无 upstream · 远端状态未知";
 ["staged","unstaged","untracked","conflicts"].forEach(k=>$(k).textContent=snapshot.status[k]);
 $("freshness").textContent="采集于 "+new Date(snapshot.capturedAt).toLocaleTimeString();
 const tags=snapshot.tags.filter(t=>t.reachable&&t.stable).sort((a,b)=>{const av=a.version.split('.').map(BigInt),bv=b.version.split('.').map(BigInt);for(let i=0;i<3;i++){if(av[i]!==bv[i])return av[i]>bv[i]?-1:1;}return a.ref.localeCompare(b.ref);});
 $("baseline").replaceChildren();tags.forEach(t=>{const o=el("option",t.ref+" · "+t.commit.slice(0,8));o.value=t.ref;$("baseline").append(o);});
 $("tag-field").hidden=!tags.length;$("initial-field").hidden=!!tags.length;$("baseline-confirm").checked=false;
 $("tag-count").textContent=`(${snapshot.tags.length})`;
 const table=el("table"),heading=el("tr");["标签","对象","状态"].forEach(x=>heading.append(el("th",x)));table.append(heading);
 snapshot.tags.forEach(t=>{const row=el("tr");[t.ref,t.object.slice(0,12),!t.version?"排除：非版本标签":!t.commit?"复核：非直接提交":!t.reachable?"排除：不可达":!t.stable?"复核：预发布 / 构建元数据":"可选基线 · 签名未验证"].forEach(x=>row.append(el("td",x)));table.append(row);});
 $("tags").replaceChildren(table);$("refresh").disabled=false;
}
function renderPlan(){
 $("result").hidden=!plan;$("export-section").hidden=!plan;$("preview-content").hidden=true;$("reason").value="";$("override").value="";
 if(!plan)return;
 $("plan-status").textContent=states[plan.status];$("plan-status").className="badge"+(plan.status==="needs_review"?" review":"");
 $("candidate").textContent=plan.candidateVersion||"待复核";if(plan.status==="no_release")$("candidate").textContent="无需升级";
 $("bump").textContent=`${plan.bump} · 暂定 ${plan.provisionalCandidate||"无"}`;$("commit-count").textContent=plan.commits.length;
 $("review-state").textContent=plan.manualReview?"已记录":"未确认";
 $("reasons").replaceChildren(...(plan.reviewReasons.length?plan.reviewReasons:["无待复核规则项；仍需人工确认"]).map(x=>el("li",x)));
 $("risks").replaceChildren(...plan.risks.map(x=>el("li",x)));
 const rows=plan.commits.map(c=>{const row=el("div",undefined,"commit-row"),details=el("details"),summary=el("summary",c.title);details.append(summary,el("p",c.message,"message"));if(c.reviews.length)details.append(el("p",c.reviews.join("；"),"review-note"));row.append(el("span",c.breaking?"BREAKING":c.type,"type"),details,el("code",c.oid.slice(0,8)));return row;});
 $("commits").replaceChildren(...(rows.length?rows:[el("p","基线与 HEAD 之间没有新增提交。","muted")]));
}
$("choose").onclick=()=>perform(async()=>{const r=await api("choose");if(r.path){$("path").value=r.path;const s=await api("open",{path:r.path});snapshot=s.snapshot;plan=null;renderSnapshot();renderPlan();message("仓库已读取，请确认基线。");}else message("已取消选择。");});
$("open").onclick=()=>perform(async()=>{snapshot=null;plan=null;renderSnapshot();renderPlan();const r=await api("open",{path:$("path").value});snapshot=r.snapshot;renderSnapshot();message("仓库已读取，请确认基线。");});
$("path").onkeydown=e=>{if(e.key==="Enter")$("open").click();};
$("refresh").onclick=()=>perform(async()=>{const r=await api("refresh");snapshot=r.snapshot;plan=null;renderSnapshot();renderPlan();message("已刷新，旧计划与确认已清除。");});
$("plan").onclick=()=>perform(async()=>{const r=await api("plan",{baseline:$("baseline").value,initial:$("initial").value,confirmed:$("baseline-confirm").checked});plan=r.plan;renderPlan();message("计划已生成，尚未授权发布。");});
$("review-form").onsubmit=e=>{e.preventDefault();perform(async()=>{const r=await api("review",{planFingerprint:plan.planFingerprint,reason:$("reason").value,override:$("override").value});plan=r.plan;renderPlan();message("已记录当前计划的人工复核。");});};
$("preview").onclick=()=>perform(async()=>{const r=await api("preview",{planFingerprint:plan?.planFingerprint,format:$("format").value});$("preview-content").textContent=r.content;$("preview-content").hidden=false;message("报告预览已更新。");});
$("format").onchange=()=>{$("preview-content").hidden=true;};
for(const id of ["baseline","initial"]){$(id).addEventListener("change",()=>{ $("baseline-confirm").checked=false;plan=null;renderPlan();perform(async()=>{await api("discard");message("基线输入已变更，请重新确认并生成计划。");});});}
async function save(dialog){const r=await api("export",{planFingerprint:plan?.planFingerprint,format:$("format").value,dialog,path:$("save-path").value});message(r.cancelled?"已取消导出。":"报告已保存："+r.path);}
$("export").onclick=()=>perform(async()=>{try{await save(true);}catch(e){$("save-fallback").hidden=false;throw e;}});
$("save-path-button").onclick=()=>perform(()=>save(false));
$("quit").onclick=()=>perform(async()=>{await api("quit");sessionStorage.removeItem("planner-session");document.querySelector("main").replaceChildren(el("h1","会话已结束"),el("p","仓库数据已从会话清除，可以关闭窗口。"));});
icons();
perform(async()=>{const r=await api("state");snapshot=r.snapshot;plan=r.plan;renderSnapshot();renderPlan();message("");});
