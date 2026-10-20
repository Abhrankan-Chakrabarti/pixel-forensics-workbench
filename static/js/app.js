(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = {
    groups: [], modules: [], selected: new Set(), sessionId: null, objectUrl: null,
    results: [], reportUrl: null, activeFilter: 'all', uploadInProgress: false,
    running: false, toastTimer: null, renderStarted: false,
  };
  const app = $('workbench');
  const categoryIcons = {core:'▣',basic:'◉',relationships:'⌁',anomaly:'⚠',forensic:'◈',data_hiding:'▤',investigation:'⌕',utilities:'⚙'};
  const categoryColors = {core:'cyan',basic:'purple',relationships:'blue',anomaly:'orange',forensic:'violet',data_hiding:'green',investigation:'pink',utilities:'muted'};

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  function humanize(key) { return String(key).replace(/_/g,' ').replace(/([a-z])([A-Z])/g,'$1 $2').replace(/\bpx\b/gi,'px').replace(/\b\w/g,c=>c.toUpperCase()); }
  function prettyValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'number') return Number.isInteger(value) ? String(value) : Number(value.toPrecision(5)).toString();
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (Array.isArray(value)) {
      const txt = value.map(v => typeof v === 'object' ? JSON.stringify(v) : String(v)).join(', ');
      return txt.length > 180 ? txt.slice(0,177)+'…' : (txt || '—');
    }
    if (typeof value === 'object') {
      const txt = JSON.stringify(value);
      return txt.length > 190 ? txt.slice(0,187)+'…' : txt;
    }
    return String(value);
  }
  function toast(message, isError = false) {
    const t = $('toast'); t.textContent = message; t.classList.remove('hidden');
    t.style.borderColor = isError ? 'var(--red)' : 'var(--cyan)';
    clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => t.classList.add('hidden'), 3600);
  }
  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const contentType = response.headers.get('content-type') || '';
    const body = contentType.includes('application/json') ? await response.json() : null;
    if (!response.ok) throw new Error((body && body.error) || `Request failed (${response.status})`);
    return body;
  }
  function updateHealth(online, text) {
    const chip = $('healthText').closest('.status-chip');
    chip.classList.toggle('online', online); chip.classList.toggle('offline', !online);
    $('healthText').textContent = text;
  }
  async function checkHealth() {
    try {
      const result = await api('/api/health');
      updateHealth(true, 'BACKEND ONLINE');
      $('moduleCount').textContent = result.modules;
      $('runSelected').textContent = `${state.selected.size} / ${result.modules}`;
    } catch (_) { updateHealth(false, 'BACKEND OFFLINE'); }
  }
  async function loadCatalog() {
    try {
      const data = await api('/api/modules');
      state.groups = data.groups || [];
      state.modules = state.groups.flatMap(g => g.items.map(item => ({...item, group:g.name, key:g.key, groupDescription:g.description})));
      $('moduleCount').textContent = state.modules.length;
      renderModules(true); updateCounts();
    } catch (err) {
      $('moduleCategories').innerHTML = `<div class="loading-line">Could not load module catalog. Start the Flask app and refresh.</div>`;
      toast(err.message, true);
    }
  }
  function currentOpenCategories() {
    const open = new Set();
    $('moduleCategories').querySelectorAll('.module-category[open]').forEach(d => open.add(d.dataset.category));
    return open;
  }
  function renderModules(firstRender = false) {
    const openCategories = firstRender ? new Set(['core','basic','relationships','anomaly']) : currentOpenCategories();
    const query = $('moduleSearch').value.trim().toLowerCase();
    const markup = state.groups.map(group => {
      const visible = group.items.filter(item => `${item.name} ${item.description} ${group.name}`.toLowerCase().includes(query));
      if (!visible.length) return '';
      const selectedN = visible.filter(item => state.selected.has(item.id)).length;
      const allChecked = selectedN === visible.length;
      const someChecked = selectedN > 0 && !allChecked;
      const isOpen = openCategories.has(group.key) || query.length > 0;
      const items = visible.map(item => `
        <label class="module-label" title="${escapeHTML(item.description)}">
          <input type="checkbox" data-module="${escapeHTML(item.id)}" ${state.selected.has(item.id) ? 'checked' : ''}>
          <span><span class="module-name">${escapeHTML(item.name)}</span><span class="module-desc">${escapeHTML(item.description)}</span></span>
        </label>`).join('');
      return `<details class="module-category" data-category="${escapeHTML(group.key)}" ${isOpen ? 'open' : ''}>
        <summary class="category-head"><span class="category-title-wrap"><span class="category-icon color-${categoryColors[group.key] || 'cyan'}">${categoryIcons[group.key] || '◈'}</span><span><span class="category-name">${escapeHTML(group.name)}</span><span class="category-count">${visible.length} modules · ${escapeHTML(group.description)}</span></span></span><span class="category-select"><input type="checkbox" data-cat="${escapeHTML(group.key)}" aria-label="Select visible ${escapeHTML(group.name)} modules" ${allChecked ? 'checked' : ''} ${someChecked ? 'data-indeterminate="true"' : ''} onclick="event.stopPropagation()"><span>Select</span><span class="category-chevron">›</span></span></summary>
        <div class="module-items">${items}</div></details>`;
    }).join('');
    $('moduleCategories').innerHTML = markup || `<div class="loading-line">No modules match “${escapeHTML(query)}”.</div>`;
    $('moduleCategories').querySelectorAll('[data-cat]').forEach(box => {
      box.indeterminate = box.dataset.indeterminate === 'true';
      box.addEventListener('change', () => {
        const category = state.groups.find(g => g.key === box.dataset.cat);
        if (!category) return;
        const q = $('moduleSearch').value.trim().toLowerCase();
        category.items.filter(item => `${item.name} ${item.description} ${category.name}`.toLowerCase().includes(q)).forEach(item => {
          if (box.checked) state.selected.add(item.id); else state.selected.delete(item.id);
        });
        renderModules(); updateCounts();
      });
    });
    $('moduleCategories').querySelectorAll('[data-module]').forEach(box => {
      box.addEventListener('change', () => {
        if (box.checked) state.selected.add(box.dataset.module); else state.selected.delete(box.dataset.module);
        updateCounts(); renderModules();
      });
    });
  }
  function updateCounts() {
    $('selectedCount').textContent = state.selected.size;
    $('runSelected').textContent = `${state.selected.size} / ${state.modules.length}`;
    $('runBtn').disabled = !state.sessionId || state.selected.size === 0 || state.running || state.uploadInProgress;
    $('selectAll').disabled = state.running || !state.modules.length;
    $('selectCore').disabled = state.running || !state.modules.length;
    $('selectNone').disabled = state.running || !state.modules.length;
  }
  function setModulesCollapsed(collapsed) {
    app.classList.toggle('modules-collapsed', Boolean(collapsed));
    const button = $('toggleModules');
    button.textContent = collapsed ? 'Show Module Selection' : 'Hide Module Selection';
    button.setAttribute('aria-expanded', String(!collapsed));
  }
  function openImageLightbox(img) {
    if (!img || !img.src) return;
    $('lightboxImage').src = img.currentSrc || img.src;
    $('lightboxImage').alt = img.alt || 'Expanded image preview';
    $('lightboxCaption').textContent = img.alt || 'Image preview';
    $('imageLightbox').classList.remove('hidden');
    $('closeLightbox').focus();
  }
  function closeImageLightbox() {
    $('imageLightbox').classList.add('hidden');
    $('lightboxImage').removeAttribute('src');
  }
  function updateImageInfo(meta = {}) {
    const rows = [
      ['File name', meta.filename || '—'], ['Format', meta.format || '—'],
      ['Dimensions', (meta.width && meta.height) ? `${meta.width} × ${meta.height}` : '—'],
      ['File size', meta.file_size_human || humanBytes(meta.file_size_bytes)], ['Color mode', meta.mode || meta.source_mode || '—'],
      ['SHA-256', meta.sha256 || 'Available after analysis'],
    ];
    $('imageInfo').innerHTML = rows.map(([label,value]) => `<div class="info-row ${label==='SHA-256'?'hash-row':''}"><span>${escapeHTML(label)}</span><b title="${escapeHTML(value)}">${escapeHTML(value)}</b></div>`).join('');
    if (meta.width && meta.height) $('previewDimensions').textContent = `${meta.width} × ${meta.height}px · ${meta.format || 'image'}`;
  }
  function humanBytes(n) { if (!Number.isFinite(Number(n))) return '—'; n=Number(n); return n >= 1024*1024 ? `${(n/1024/1024).toFixed(2)} MB` : `${(n/1024).toFixed(1)} KB`; }
  function setProgress(pct, text) {
    $('progressFill').style.width = `${Math.max(0,Math.min(100,pct))}%`;
    $('progressPercent').textContent = `${Math.round(pct)}%`;
    $('runStatus').textContent = text;
  }
  async function deleteSession(sid) {
    if (!sid) return;
    try { await api(`/api/session/${encodeURIComponent(sid)}`, {method:'DELETE'}); } catch (_) { /* server TTL will still reap it */ }
  }
  async function selectFile(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) { toast('Choose a supported image file.', true); return; }
    if (file.size > 20*1024*1024) { toast('Image is larger than the 20 MB upload limit.', true); return; }
    await deleteSession(state.sessionId); state.sessionId = null; state.results = []; state.reportUrl = null;
    setModulesCollapsed(false); resetResults();
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = URL.createObjectURL(file);
    $('uploadTitle').textContent = file.name; $('uploadSub').textContent = 'Previewing locally; preparing server-side analysis session';
    $('fileInfo').textContent = `${file.name} · ${humanBytes(file.size)}`;
    $('sourcePreview').innerHTML = `<img src="${state.objectUrl}" alt="Selected source image preview">`;
    $('previewIndicator').textContent = 'UPLOADING'; $('previewIndicator').classList.remove('ready');
    $('clearFile').disabled = false; state.uploadInProgress = true; updateCounts(); updateImageInfo({filename:file.name,format:file.type.split('/').pop().toUpperCase(),file_size_bytes:file.size});
    setProgress(0,'Uploading image to local Flask session…');
    const form = new FormData(); form.append('image',file,file.name);
    try {
      const data = await api('/api/upload',{method:'POST',body:form});
      state.sessionId = data.session_id; state.lastUploadMetadata = data.image;
      $('uploadSub').textContent = 'Image ready for selected analysis modules';
      $('previewIndicator').textContent = 'SOURCE READY'; $('previewIndicator').classList.add('ready');
      updateImageInfo(data.image); setProgress(0,'Image ready. Select modules and run analysis.');
      $('resultCountTag').textContent = 'WAITING'; toast('Image loaded locally. Select analysis modules.');
    } catch (err) {
      $('uploadSub').textContent = 'Upload failed; check the image and server limits';
      $('previewIndicator').textContent = 'UPLOAD ERROR';
      setProgress(0,err.message); toast(err.message,true);
    } finally { state.uploadInProgress=false; updateCounts(); }
  }
  async function clearImage() {
    await deleteSession(state.sessionId); state.sessionId=null;state.results=[];state.reportUrl=null;
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);state.objectUrl=null;
    $('fileInput').value='';$('uploadTitle').textContent='Drop an image here';$('uploadSub').textContent='or click to browse your computer';$('fileInfo').textContent='No image loaded';
    $('sourcePreview').innerHTML='<div class="empty-image"><span>▧</span><b>Image appears here</b><small>Choose a source image to begin</small></div>';
    $('previewDimensions').textContent='Waiting for source image';$('previewIndicator').textContent='NO SOURCE';$('previewIndicator').classList.remove('ready');$('clearFile').disabled=true;
    updateImageInfo({});setProgress(0,'Upload an image, then select modules.');$('elapsedTime').textContent='—';resetResults();$('uploadSub').textContent='or click to browse your computer';updateCounts();
  }
  async function loadSampleEvidence() {
    try {
      toast('Loading sample forensic evidence…');
      const res = await fetch('/static/samples/sample_forensic_evidence.png');
      if (!res.ok) throw new Error('Could not fetch sample evidence image');
      const blob = await res.blob();
      const file = new File([blob], 'sample_forensic_evidence.png', { type: 'image/png' });
      await selectFile(file);
      if (!state.selected.size) {
        state.modules.filter(m => ['core', 'basic', 'relationships'].includes(m.key)).forEach(m => state.selected.add(m.id));
        renderModules();
        updateCounts();
        toast('Loaded sample evidence image & selected Core analysis modules.');
      }
    } catch (err) {
      toast('Error loading sample image: ' + err.message, true);
    }
  }
  async function runAnalysis() {
    if (!state.sessionId || !state.selected.size || state.running) return;
    state.running=true;updateCounts();$('busyOverlay').classList.remove('hidden');$('busyTitle').textContent='Analyzing image';$('busySubtitle').textContent=`Running ${state.selected.size} selected modules independently…`;
    $('progressFill').classList.add('indeterminate');setProgress(12,`Preparing ${state.selected.size} analyzers…`);
    const start=performance.now();
    try {
      const data=await api('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:state.sessionId,modules:[...state.selected]})});
      state.results=data.results||[];state.reportUrl=data.report_url;state.lastAnalysisMetadata=data.image;
      $('elapsedTime').textContent=`${((performance.now()-start)/1000).toFixed(2)} s`;
      updateImageInfo(data.image);setProgress(100,`Analysis complete · ${data.summary.completed} completed, ${data.summary.failed} failed, ${data.summary.warnings} warning(s)`);
      $('resultCountTag').textContent=`${state.results.length} RESULTS`;$('resultCountTag').classList.add('has-results');
      renderResults();$('expandAll').disabled=!state.results.length;$('collapseAll').disabled=!state.results.length;$('resetRun').disabled=!state.results.length;$('exportHtmlReport').disabled=!state.reportUrl;$('exportPdfReport').disabled=!state.reportUrl;
      if (state.results.length) setModulesCollapsed(true);
      const failed=data.summary.failed||0;toast(failed?`Run finished; ${failed} module(s) failed independently. See their error cards.`:`Analysis finished: ${state.results.length} modules. Review findings manually.`);
    } catch (err) {setProgress(0,err.message);toast(err.message,true);} finally {
      $('progressFill').classList.remove('indeterminate');$('busyOverlay').classList.add('hidden');state.running=false;updateCounts();
    }
  }
  function metricMarkup(metrics = {}) {
    const entries=Object.entries(metrics);
    if (!entries.length) return '<div class="metrics"><div class="metric-item wide"><span>Metrics</span><b>No numeric metrics were returned.</b></div></div>';
    const chosen=entries.slice(0,16);
    return `<div class="metrics">${chosen.map(([key,value])=>{
      const printable=prettyValue(value);const wide=printable.length>44||typeof value==='object'||/sha256|hash|warning|note|heuristic|dimensions|ranked|peaks|region|tile|fraction_by|matrix|signal_weights/i.test(key);
      return `<div class="metric-item ${wide?'wide':''}"><span>${escapeHTML(humanize(key))}</span><b title="${escapeHTML(printable)}">${escapeHTML(printable)}</b></div>`;
    }).join('')}${entries.length>chosen.length?`<div class="metric-item wide"><span>More metrics</span><b>${entries.length-chosen.length} additional fields are included in the HTML and PDF reports.</b></div>`:''}</div>`;
  }
  function rgbPanelMarkup(metrics = {}) {
    const names = [
      { key: 'red', label: 'RED', color: '#ff4b5c' },
      { key: 'green', label: 'GREEN', color: '#35d98a' },
      { key: 'blue', label: 'BLUE', color: '#5796ff' },
    ];
    const values = names.map(n => ({ ...n, stats: metrics[n.key] || {} }));
    const mean = key => Number(values.find(v => v.key === key)?.stats.mean || 0);
    const rgb = [mean('red'), mean('green'), mean('blue')].map(v => Math.max(0, Math.min(255, Math.round(v))));
    const hex = `#${rgb.map(v => v.toString(16).padStart(2,'0')).join('').toUpperCase()}`;
    return `<div class="rgb-channel-grid">${values.map(v => {
      const m = v.stats.mean;
      const meanText = m === undefined ? '—' : prettyValue(m);
      const minText = v.stats.min === undefined ? '—' : prettyValue(v.stats.min);
      const maxText = v.stats.max === undefined ? '—' : prettyValue(v.stats.max);
      const channelColor = v.key === 'red' ? `rgb(${Math.round(m||0)},0,0)` : v.key === 'green' ? `rgb(0,${Math.round(m||0)},0)` : `rgb(0,0,${Math.round(m||0)})`;
      return `<div class="rgb-channel-tile"><div class="rgb-channel-top"><span class="rgb-swatch" style="background:${channelColor}"></span><span class="rgb-channel-name">${v.label}</span></div><div class="rgb-channel-value">${meanText}</div><div class="rgb-range"><span>MIN <b>${minText}</b></span><span>MAX <b>${maxText}</b></span></div><div class="rgb-meter"><i style="width:${Math.max(0,Math.min(100,Number(m||0)/255*100))}%;background:${v.color}"></i></div></div>`;
    }).join('')}</div><div class="rgb-composite"><span class="rgb-swatch" style="background:${hex}"></span><span>Composite channel means</span><b>${hex}</b></div>`;
  }
  function nativeChartMarkup(chart) {
    if (!chart || !chart.type) return '';
    const esc = escapeHTML;
    const width = 880, left = 70, right = 24, top = 25, bottom = 50;
    const plotW = width-left-right;
    const title = esc(chart.title || 'Image data chart');
    const suffix = chart.value_suffix || '';
    let body = '', height = 330;
    if (chart.type === 'bar') {
      const items = (chart.items || []).filter(item => Number.isFinite(Number(item.value)));
      if (!items.length) return '';
      height = Math.max(300, top + 45 + items.length * 34);
      const labelWidth = Math.min(350, Math.max(215, width * .31));
      const barStart = labelWidth + 22;
      const barW = width - barStart - 75;
      const maxV = Math.max(1, ...items.map(item => Number(item.value)));
      const ticks = [0, .25, .5, .75, 1].map(f => {
        const x = barStart + barW*f;
        return `<line class="chart-gridline" x1="${x}" y1="${top-4}" x2="${x}" y2="${height-bottom+4}"/><text class="chart-axis-label" x="${x}" y="${height-bottom+23}" text-anchor="middle">${prettyValue(maxV*f)}${esc(suffix)}</text>`;
      }).join('');
      const bars = items.map((item,i) => {
        const y = top + i*34;
        const v = Number(item.value);
        const bw = Math.max(1,barW*v/maxV);
        const color = /^#[0-9a-f]{6}$/i.test(item.color || '') ? item.color : 'var(--blue)';
        const label = String(item.label || `Item ${i+1}`);
        return `<text class="chart-category-label" x="${labelWidth}" y="${y+16}" text-anchor="end">${esc(label.length>43?label.slice(0,40)+'…':label)}</text><rect class="chart-mark" tabindex="0" role="img" aria-label="${esc(label)}: ${esc(prettyValue(v))}${esc(suffix)}" data-chart-label="${esc(label)}" data-chart-value="${esc(prettyValue(v))}${esc(suffix)}" x="${barStart}" y="${y+2}" width="${bw}" height="21" rx="5" fill="${color}"><title>${esc(label)}: ${esc(prettyValue(v))}${esc(suffix)}</title></rect><text class="chart-value-label" x="${Math.min(width-65,barStart+bw+8)}" y="${y+17}">${esc(prettyValue(v))}${esc(suffix)}</text>`;
      }).join('');
      body = `${ticks}${bars}<text class="chart-axis-label" x="${barStart+barW/2}" y="${height-8}" text-anchor="middle">${esc(chart.x_label || 'Value')}</text>`;
    } else if (chart.type === 'line') {
      const series = (chart.series || []).map(s => ({ ...s, values:(s.values||[]).map(Number).filter(Number.isFinite) })).filter(s=>s.values.length);
      if (!series.length) return '';
      const maxCount = Math.max(...series.map(s=>s.values.length));
      // Use provided x-values where available; otherwise graph samples index-by-index.
      const allValues = series.flatMap(s=>s.values);
      let yMin = Number.isFinite(Number(chart.y_min)) ? Number(chart.y_min) : Math.min(0,...allValues);
      let yMax = Number.isFinite(Number(chart.y_max)) ? Number(chart.y_max) : Math.max(1,...allValues);
      if (yMax <= yMin) yMax = yMin + 1;
      const plotH = height-top-bottom;
      const y = v => top + plotH - ((v-yMin)/(yMax-yMin))*plotH;
      const x = i => left + (maxCount<2 ? .5 : i/(maxCount-1))*plotW;
      const ticks = [0,.25,.5,.75,1].map(f=>{const val=yMin+(yMax-yMin)*f,yy=y(val);return `<line class="chart-gridline" x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}"/><text class="chart-axis-label" x="${left-12}" y="${yy+4}" text-anchor="end">${esc(prettyValue(val))}</text>`}).join('');
      const lines = series.map((s,si)=>{
        const color = /^#[0-9a-f]{6}$/i.test(s.color||'')?s.color:['var(--blue)','var(--green)','var(--cyan)'][si%3];
        const coords = s.values.map((v,i)=>`${x(i)},${y(v)}`);
        const poly = `<polyline points="${coords.join(' ')}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
        const marks=s.values.map((v,i)=>{
          const xv=(s.x_values&&s.x_values[i]!==undefined)?s.x_values[i]:i;
          const label=`${s.name||'Series'} · ${chart.x_label||'Sample'} ${prettyValue(xv)}`;
          const showValue=prettyValue(v)+(chart.value_suffix||'');
          return `<circle class="chart-mark" tabindex="0" role="img" aria-label="${esc(label)}: ${esc(showValue)}" data-chart-label="${esc(label)}" data-chart-value="${esc(showValue)}" cx="${x(i)}" cy="${y(v)}" r="3.4" fill="${color}" stroke="var(--surface)" stroke-width="1.5"><title>${esc(label)}: ${esc(showValue)}</title></circle>`;
        }).join('');
        return poly+marks;
      }).join('');
      const firstSeries=series[0], xvals=firstSeries.x_values||[];
      const xlabels=[0,Math.floor((maxCount-1)/2),maxCount-1].filter((v,i,a)=>a.indexOf(v)===i).map(i=>{
        const label=xvals[i]===undefined?i:xvals[i];return `<text class="chart-axis-label" x="${x(i)}" y="${height-bottom+22}" text-anchor="middle">${esc(prettyValue(label))}</text>`;
      }).join('');
      const legend=`<div class="chart-legend">${series.map((s,i)=>`<span><i style="background:${/^#[0-9a-f]{6}$/i.test(s.color||'')?s.color:['#53a8ff','#66e0b0','#39e7ff'][i%3]}"></i>${esc(s.name||`Series ${i+1}`)}</span>`).join('')}</div>`;
      body = `${ticks}${lines}${xlabels}<text class="chart-axis-label" x="${left+plotW/2}" y="${height-8}" text-anchor="middle">${esc(chart.x_label || 'Sample')}</text>`;
      return `<figure class="result-chart"><div class="chart-heading">${title}</div><svg class="native-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}">${body}</svg><div class="chart-tooltip" aria-live="polite">Hover or focus a data point to inspect its value.</div>${legend}<figcaption>${esc(chart.y_label || 'Measured value')} · generated from analysis data</figcaption></figure>`;
    } else return '';
    return `<figure class="result-chart"><div class="chart-heading">${title}</div><svg class="native-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}">${body}</svg><div class="chart-tooltip" aria-live="polite">Hover or focus a data point or bar to inspect its value.</div><figcaption>${esc(chart.y_label || 'Measured value')} · generated from analysis data</figcaption></figure>`;
  }
  function bindChartTooltips(container) {
    container.querySelectorAll('.chart-mark').forEach(mark => {
      const chart = mark.closest('.result-chart'); const tip = chart && chart.querySelector('.chart-tooltip');
      if (!tip) return;
      const show = () => { tip.textContent = `${mark.dataset.chartLabel}: ${mark.dataset.chartValue}`; tip.classList.add('active'); };
      const clear = () => { tip.textContent = 'Hover or focus a data point or bar to inspect its value.'; tip.classList.remove('active'); };
      mark.addEventListener('mouseenter',show);mark.addEventListener('focus',show);mark.addEventListener('mouseleave',clear);mark.addEventListener('blur',clear);
    });
  }
  function resultCardMarkup(result) {
    const status=result.status||'ok';const stateLabel=status==='error'?'ERROR':status==='warning'?'REVIEW':'DONE';
    const pixelModules = new Set(['bit_extraction','bit_planes','lsb','difference','xor_analysis']);
    const visualClass = pixelModules.has(result.module_id) ? 'pixel-map-image' : '';
    const chartVisualLabels = new Set((result.chart && result.chart.replace_visuals) || []);
    let visuals=(result.visuals||[]).filter(v=>!chartVisualLabels.has(v.label));
    if (result.module_id === 'channels') visuals = [];
    const visualMarkup=visuals.map(v=>`<figure class="result-visual"><img class="${visualClass}" loading="lazy" decoding="async" src="${escapeHTML(v.url)}" alt="${escapeHTML(v.label||result.name)}"><figcaption>${escapeHTML(v.label||'Visualization')}</figcaption></figure>`).join('');
    const chartMarkup=result.chart?nativeChartMarkup(result.chart):'';
    const rgbMarkup=result.module_id==='channels'?rgbPanelMarkup(result.metrics||{}):'';
    const warningMarkup=(result.warnings||[]).length?`<details class="result-warnings"><summary>${result.warnings.length} analyst note${result.warnings.length===1?'':'s'}</summary><ul>${result.warnings.map(w=>`<li>${escapeHTML(w)}</li>`).join('')}</ul></details>`:'';
    const metricsMarkup=result.module_id==='channels'?'':metricMarkup(result.metrics);
    return `<article class="result-card" data-result-module="${escapeHTML(result.module_id)}"><div class="result-card-head"><strong>${escapeHTML(result.name)}</strong><span class="state-pill ${status==='error'?'error':status==='warning'?'warning':''}">${stateLabel}</span></div><p class="result-summary">${escapeHTML(result.summary||'No summary provided.')}</p>${rgbMarkup}${chartMarkup}${visualMarkup?`<div class="result-visuals">${visualMarkup}</div>`:''}${metricsMarkup}${warningMarkup}<div class="card-footer"><span>${Number.isFinite(result.elapsed_ms)?`${result.elapsed_ms.toFixed(1)} ms`:''}</span><span>${status==='error'?'Module isolated':status==='warning'?'Manual review':'Analysis output'}</span></div></article>`;
  }
  function renderTabs() {
    const filterCounts={all:state.results.length};state.results.forEach(r=>filterCounts[r.group_key]=(filterCounts[r.group_key]||0)+1);
    const tabs=[`<button class="result-tab ${state.activeFilter==='all'?'active':''}" data-filter="all">All Results <b id="allResultsCount">${state.results.length}</b></button>`];
    state.groups.forEach(g=>tabs.push(`<button class="result-tab ${state.activeFilter===g.key?'active':''}" data-filter="${escapeHTML(g.key)}">${escapeHTML(g.name)} <b>${filterCounts[g.key]||0}</b></button>`));
    $('resultTabs').innerHTML=tabs.join('');$('resultTabs').querySelectorAll('[data-filter]').forEach(btn=>btn.addEventListener('click',()=>{state.activeFilter=btn.dataset.filter;renderResults();}));
  }
  function renderResults() {
    renderTabs();
    const outputGroups=state.groups.map(g=>({group:g,results:state.results.filter(r=>r.group_key===g.key)})).filter(x=>x.results.length&&(state.activeFilter==='all'||x.group.key===state.activeFilter));
    if (!state.results.length) {
      $('resultsRoot').innerHTML='<div class="empty-results panel"><div class="empty-results-icon">⌁</div><h3>Ready for image investigation</h3><p>Upload a source image, choose modules on the left, and run your analysis. Real measurements and generated visualizations will appear here.</p></div>';
      $('resultSubtitle').textContent='Results from selected modules will be grouped by category.';return;
    }
    $('resultsRoot').innerHTML=outputGroups.map(({group,results})=>`<details class="result-category result-group" data-result-group="${escapeHTML(group.key)}" open><summary class="result-category-head"><span class="result-category-title"><span class="category-icon color-${categoryColors[group.key]||'cyan'}">${categoryIcons[group.key]||'◈'}</span><h3>${escapeHTML(group.name)}</h3><span>${results.length} module${results.length===1?'':'s'}</span></span><span class="result-chevron">›</span></summary><div class="result-grid">${results.map(resultCardMarkup).join('')}</div></details>`).join('');
    bindChartTooltips($('resultsRoot'));
    $('resultSubtitle').textContent=`${state.results.length} module outputs · ${outputGroups.length} categories shown · use Export Report for complete metrics.`;
  }
  function resetResults() {
    state.results=[];state.reportUrl=null;state.activeFilter='all';setModulesCollapsed(false);$('resultsRoot').innerHTML='<div class="empty-results panel"><div class="empty-results-icon">⌁</div><h3>Ready for image investigation</h3><p>Upload a source image, choose modules on the left, and run your analysis. Real measurements and generated visualizations will appear here.</p></div>';
    $('resultSubtitle').textContent='Results from selected modules will be grouped by category.';$('resultCountTag').textContent='WAITING';$('resultCountTag').classList.remove('has-results');$('expandAll').disabled=true;$('collapseAll').disabled=true;$('resetRun').disabled=true;$('exportHtmlReport').disabled=true;$('exportPdfReport').disabled=true;
    $('resultTabs').innerHTML='<button class="result-tab active" data-filter="all">All Results <b>0</b></button>';
  }
  function applySettings() {
    $('themeSelect').addEventListener('change',()=>{app.dataset.theme=$('themeSelect').value;toast(`Theme: ${$('themeSelect').selectedOptions[0].text}`)});
    $('styleSelect').addEventListener('change',()=>{app.dataset.style=$('styleSelect').value;toast(`Layout: ${$('styleSelect').selectedOptions[0].text}`)});
    $('motionSelect').addEventListener('change',()=>{app.dataset.motion=$('motionSelect').value;toast(`Animation: ${$('motionSelect').selectedOptions[0].text}`)});
  }
  function bindEvents() {
    $('toggleModules').addEventListener('click',()=>setModulesCollapsed(!app.classList.contains('modules-collapsed')));
    $('closeLightbox').addEventListener('click',closeImageLightbox);
    $('imageLightbox').addEventListener('click',e=>{if(e.target===$('imageLightbox'))closeImageLightbox();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeImageLightbox();});
    $('sourcePreview').addEventListener('click',e=>{const img=e.target.closest('img');if(img)openImageLightbox(img);});
    $('resultsRoot').addEventListener('click',e=>{const img=e.target.closest('.result-visual img');if(img)openImageLightbox(img);});
    $('selectAll').addEventListener('click',()=>{state.modules.forEach(m=>state.selected.add(m.id));renderModules();updateCounts();});
    $('selectCore').addEventListener('click',()=>{state.modules.filter(m=>['core','basic','relationships'].includes(m.key)).forEach(m=>state.selected.add(m.id));renderModules();updateCounts();toast('Core Set selected: core, basic and pixel-relationship modules.');});
    $('selectNone').addEventListener('click',()=>{state.selected.clear();renderModules();updateCounts();});
    $('moduleSearch').addEventListener('input',()=>renderModules());
    $('fileInput').addEventListener('change',e=>selectFile(e.target.files && e.target.files[0]));
    $('chooseBtn').addEventListener('click',()=>$('fileInput').click());
    $('sampleBtn')?.addEventListener('click',loadSampleEvidence);
    $('clearFile').addEventListener('click',clearImage);
    $('dropzone').addEventListener('dragover',e=>{e.preventDefault();$('dropzone').classList.add('drag');});
    $('dropzone').addEventListener('dragleave',()=>$('dropzone').classList.remove('drag'));
    $('dropzone').addEventListener('drop',e=>{e.preventDefault();$('dropzone').classList.remove('drag');selectFile(e.dataTransfer.files && e.dataTransfer.files[0]);});
    $('dropzone').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('fileInput').click();}});
    $('runBtn').addEventListener('click',runAnalysis);
    $('expandAll').addEventListener('click',()=>{$('resultsRoot').querySelectorAll('.result-group').forEach(d=>d.open=true);});
    $('collapseAll').addEventListener('click',()=>{$('resultsRoot').querySelectorAll('.result-group').forEach(d=>d.open=false);});
    $('resetRun').addEventListener('click',()=>{resetResults();setProgress(0,'Results reset. The loaded image and module selection are unchanged.');toast('Results cleared. Run the selected modules again when ready.');});
    $('exportHtmlReport').addEventListener('click',()=>{if(state.reportUrl)window.location.href=`${state.reportUrl}/html`;});
    $('exportPdfReport').addEventListener('click',()=>{if(state.reportUrl)window.location.href=`${state.reportUrl}/pdf`;});
  }
  applySettings();bindEvents();
  $('resultsRoot').addEventListener('click',e=>{const img=e.target.closest('img');if(img && img.getAttribute('src')?.startsWith('/artifacts/')){/* local generated artifact */}});
  loadCatalog().then(checkHealth);
})();
