/* End-to-end tests use only temporary synthetic repositories. */
const { chromium }=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const cp=require('node:child_process');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'planner-ui-')),repo=path.join(tmp,'repo');fs.mkdirSync(repo);
 const env={PATH:'/usr/bin:/bin',HOME:tmp,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null'};
 const git=(...args)=>cp.execFileSync('/usr/bin/git',['-c','user.name=Fixture','-c','user.email=fixture@example.invalid',...args],{cwd:repo,env,stdio:'pipe'});
 git('init','--initial-branch=main');git('commit','--allow-empty','-m','feat: initial project');git('tag','v1.2.3');
 git('commit','--allow-empty','-m','feat: 支持离线版本报告');git('commit','--allow-empty','-m','fix: 保留未提交的工作区内容');
 git('commit','--allow-empty','-m','fix: <img src=x onerror=window.INJECTED=true>');
 const child=cp.spawn('/usr/bin/python3',['-B',path.join(root,'local_app/server.py'),'--no-browser'],{cwd:root,stdio:['ignore','pipe','pipe']});
 let browser;
 const evidence=process.env.PLANNER_EVIDENCE_DIR||path.join(root,'docs/implementation/local-evidence');fs.mkdirSync(evidence,{recursive:true});
 try{
  const url=await new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(new Error('startup timeout')),5000);child.stdout.on('data',chunk=>{output+=chunk;if(output.includes('\n')){clearTimeout(timeout);resolve(output.trim());}});child.on('exit',code=>reject(new Error('server exit '+code)));});
  browser=await chromium.launch({headless:true,executablePath:process.env.PLANNER_BROWSER||'/usr/bin/google-chrome',args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(new URL(url).origin))external.push(r.url());});
  await page.goto(url);await page.waitForFunction(()=>!document.body.classList.contains('busy'));
  await page.locator('#path').fill(repo);await page.locator('#open').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.locator('#baseline-confirm').check();await page.locator('#plan').click();await page.locator('#result').waitFor({state:'visible'});
  assert.equal(await page.locator('#candidate').textContent(),'1.3.0');
  assert.equal(await page.evaluate(()=>window.INJECTED),undefined);
  await page.locator('#reason').fill('已检查全部合成提交，确认规则建议。');await page.locator('#review-form button').click();
  await page.waitForFunction(()=>document.getElementById('review-state').textContent==='已记录');
  await page.locator('#preview').click();await page.locator('#preview-content').waitFor({state:'visible'});
  assert.match(await page.locator('#preview-content').textContent(),/1\.3\.0/);
  const exported=await page.evaluate(async target=>{const r=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json','X-Planner-Token':sessionStorage.getItem('planner-session')},body:JSON.stringify({path:target,format:'json',planFingerprint:plan.planFingerprint})});return {status:r.status,body:await r.json()};},path.join(tmp,'report.json'));
  assert.equal(exported.status,200);assert.equal(JSON.parse(fs.readFileSync(path.join(tmp,'report.json'),'utf8')).candidateVersion,'1.3.0');
  await page.screenshot({path:path.join(evidence,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(evidence,'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'horizontal overflow');
  git('commit','--allow-empty','-m','fix: changed after review');
  await page.locator('#preview').click();await page.locator('#error').waitFor({state:'visible'});
  assert.match(await page.locator('#error').textContent(),/变化|失效/);
  assert.equal(await page.locator('#result').isVisible(),false);
  await page.locator('#quit').click();await page.getByRole('heading',{name:'会话已结束'}).waitFor();
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const summary={status:'PASS',checks:['open','baseline confirmation','semver 1.3.0','XSS text handling','manual review','preview','JSON export','stale invalidation','desktop/mobile layout','no external requests','quit'],pageErrors:errors,externalRequests:external};
  fs.writeFileSync(path.join(evidence,'ui-results.json'),JSON.stringify(summary,null,2)+'\n');console.log(JSON.stringify(summary));
 }finally{if(browser)await browser.close();if(child.exitCode===null){child.kill('SIGTERM');await new Promise(resolve=>child.once('exit',resolve));}fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
