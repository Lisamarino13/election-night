// Pre-push smoke test: actually RUN the board's render against live data.
//
// Two blank-board bugs tonight (FEEDLBL undefined, then `unalloc` used before its
// const declaration) were both syntactically valid, so `new Function(src)` passed and
// the tab still rendered nothing. Only executing the code catches them.
//
//   jsc tools/smoke.js -- <path to index.html> <path to data/results.json>
var args = arguments;
var htmlPath = args[0], dataPath = args[1];
var html = readFile(htmlPath);

// pull the inline scripts, in order
var scripts = [], re = /<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g, m;
while ((m = re.exec(html)) !== null) scripts.push(m[1]);
// index.html's inline code depends on helpers defined in the LOCAL external scripts
// (esc lives in compare.js), so those must be loaded too or every card throws.
var ext = [], re2 = /<script\b[^>]*\bsrc="([^"?]+)[^"]*"[^>]*>/g, m2;
while ((m2 = re2.exec(html)) !== null) if (!/^https?:/.test(m2[1])) ext.push(m2[1]);
var extSrc = "";
for (var i = 0; i < ext.length; i++) {
  try { extSrc += "\n" + readFile(ext[i]); } catch (e) { print("  (skip " + ext[i] + ")"); }
}
var src = scripts.join("\n") + extSrc;

// minimal DOM so cardFor/render can run
function El(){
  this.children=[]; this.style={}; this.dataset={}; this._html="";
  this.className=""; this.textContent=""; this.value=""; this.checked=false;
  this.classList={add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
  this.options=[]; this.selectedIndex=0; this.files=[]; this.disabled=false;
}
El.prototype.appendChild=function(c){ this.children.push(c); return c; };
El.prototype.append=function(){ for (var i=0;i<arguments.length;i++) this.children.push(arguments[i]); };
El.prototype.setAttribute=function(){}; El.prototype.addEventListener=function(){};
El.prototype.querySelector=function(){ return new El(); };
El.prototype.querySelectorAll=function(){ return []; };
El.prototype.remove=function(){};
El.prototype.insertAdjacentHTML=function(){}; El.prototype.closest=function(){ return new El(); };
El.prototype.focus=function(){}; El.prototype.scrollIntoView=function(){};
Object.defineProperty(El.prototype,"innerHTML",{get:function(){return this._html;},set:function(v){this._html=String(v);}});
var document = {
  createElement: function(){ return new El(); },
  getElementById: function(){ return new El(); },
  querySelector: function(){ return new El(); },
  querySelectorAll: function(){ return []; },
  addEventListener: function(){}, body: new El(), documentElement: new El()
};
var window = { addEventListener:function(){}, location:{hash:"",reload:function(){}}, matchMedia:function(){return {matches:false,addEventListener:function(){}};} };
var localStorage = { getItem:function(){return null;}, setItem:function(){} };
var setInterval = function(){ return 0; }, setTimeout = function(){ return 0; };
var addEventListener = function(){}, removeEventListener = function(){};
var location = {hash:"", reload:function(){}}, navigator = {userAgent:"jsc"};
var matchMedia = function(){ return {matches:false, addEventListener:function(){}}; };
var requestAnimationFrame = function(){ return 0; };
var history = {replaceState:function(){}, pushState:function(){}};
var fetch = function(){ return { then: function(){ return { then:function(){return {catch:function(){}};}, catch:function(){} }; } }; };

var DATA_PATH = dataPath;
var TEST = `
  (function(){
    var data = JSON.parse(readFile(${JSON.stringify(DATA_PATH)}));
    var checked = 0, bad = 0;
    for (var abbr in data.states) {
      var st = data.states[abbr];
      for (var rk in st.races) {
        var race = st.races[rk];
        try {
          var view = {name: st.name, feedStatus: st.feed_status, feedNote: st.feed_note,
                      officialUrl: st.official_url, unitsExpected: st.unitsExpected,
                      unitsNote: st.unitsNote, unit: st.unit, countsFirst: st.countsFirst,
                      modes: race.modes || null, candidates: race.candidates,
                      counties: race.counties || []};
          var p = project(view);
          cardFor(abbr + ":" + rk, view, abbr, race.tier);
          var sum = 0; for (var i = 0; i < p.proj.length; i++) sum += p.proj[i];
          var tot = p.totC + p.allocated;
          if (Math.abs(sum - tot) > 2) {
            print("SMOKE FAIL (math): " + abbr + " " + rk + " candidates sum " +
                  Math.round(sum) + " but total row " + Math.round(tot));
            bad++;
          }
          if (p.totC > 0 && p.outstanding > 0 && Math.abs(p.allocated - p.outstanding) > 2) {
            print("SMOKE FAIL (unallocated): " + abbr + " " + rk + " allocated " +
                  Math.round(p.allocated) + " of outstanding " + p.outstanding);
            bad++;
          }
          checked++;
        } catch (e) {
          print("SMOKE FAIL (render): " + abbr + " " + rk + " -> " + e);
          bad++;
        }
      }
    }
    print("smoke: rendered " + checked + " race card(s), " + bad + " failure(s)");
    globalThis.__smokeBad = bad;
  })();
`;
var ok = true;
try { eval(src + "\n" + TEST); } catch (e) { print("SMOKE FAIL (load): " + e); ok = false; }
if (ok && globalThis.__smokeBad) ok = false;
print(ok ? "SMOKE PASS" : "SMOKE FAIL");
