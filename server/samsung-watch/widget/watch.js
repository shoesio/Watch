/* ES5 only: Samsung 2012 Orsay / Maple. No framework or remote scripts. */
var Watch = (function () {
 var renderScale = 4 / 3;
 var buildVersion = '0.332', seekTransition = false;
 'use strict';
 var api = null, keys = {}, player = null, groups = [], rows = [], page = 0, total = 0;
 var tab = 0, nav = 0, focus = 0, area = 'grid', group = null, previous = null, choosingSeason = false, season = 'all';
 var genre = '', genreChoices = [], genreFocus = 0, navOrder = [0,1,8,2,9,10,11,12,13,7,14,16,15];
 var browseMode = '', browseSnapshot = '', browseQuery = '', relatedId = '', searchValue = '', searchFocus = 0;
 var searchLetters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('').concat(['Space','Delete','Search']);
 var highlights = [], highlightFocus = 0;
 var selectedArtwork = '', lastInput = 0, featureTimer = null;
 var busy = false, playing = false, paused = false, ticket = null, job = null;
 var generation = 0, pending = [], poll = null, hide = null, readyTimer = null, heartbeat = null, previousTab = 0, pageSize = 4, guideRefresh = null;
 var currentEpisode = null, currentTitle = "", position = 0, duration = 0, sourceOffset = 0, nativeOrigin = null, livePlayback = false, controlFocus = 1, finished = false;
 var timelineMode = false, seekPreview = 0, seekRepeats = 0, lastSeekPress = 0;
 var waiting = false, frozenFrame = false, recoveringView = false, retryFailed = false, recoveryItem = null, recoveryTarget = 0;
 var retryCount = 0, retryTimer = null, bufferTimer = null, stableSince = 0;
 function trace(event) { if (WATCH_CONNECTION.key !== 'SET_DURING_PI_PACKAGING') { request('POST', '/api/diagnostic', {event:event,app_version:buildVersion,position:position,playing:playing,waiting:waiting,seeking:seekTransition}, function () {}); } }
 function playerView(open) { if (open) { document.documentElement.style.background = 'rgba(0,0,0,0)'; document.body.style.background = 'rgba(0,0,0,0)'; } document.body.setAttribute('data-player-open',open ? 'true' : 'false'); el('shell').style.display = open ? 'none' : 'block'; }
 function el(id) { return document.getElementById(id); }
 function text(id, value) { el(id).textContent = value || ''; }
 function message(value) { text('status', value); }
 function request(method, path, data, done) {
  if (WATCH_CONNECTION.key === 'SET_DURING_PI_PACKAGING') {
   setTimeout(function () {
    var match = path.match(/\/api\/(seasons|episodes)\/([^?]+)/), query = path.split('?')[1] || '', pageMatch = query.match(/page=(\d+)/), previewPage = pageMatch ? parseInt(pageMatch[1], 10) : 0, items = [];
    if (method === 'POST' && path === '/api/favourite') { done(null,{ok:true,favourite:data.favourite});return; }
    if (method !== 'GET') { done('Local preview only. Playback is available in the paired Samsung app.'); return; }
    if (typeof WATCH_PREVIEW === 'undefined') { done('Local preview data is missing. Use the installed Samsung app.'); return; }
    if (path.indexOf('/api/suggestions') === 0) { var searchTerm = query.match(/q=([^&]+)/), wantedMode = query.match(/mode=([^&]+)/); items = wantedMode && wantedMode[1] === 'featured' ? (WATCH_PREVIEW.films || []).slice(0,6) : WATCH_PREVIEW.shows.slice(0); if (searchTerm && searchTerm[1]) { var needle = decodeURIComponent(searchTerm[1]).toLowerCase();items = items.filter(function (item) { return item.title.toLowerCase().indexOf(needle) >= 0; }); } }
    else if (match) {
     items = match[1] === 'seasons' ? [{id: 'all', title: 'All episodes', meta: 'Local preview', brands: group ? group.brands : [], image: group ? group.image : null}] : (WATCH_PREVIEW.episodes[decodeURIComponent(match[2])] || []);
    } else { items = /tab=2/.test(query) ? WATCH_PREVIEW.live : (/tab=3/.test(query) ? (WATCH_PREVIEW.films || []) : WATCH_PREVIEW.shows); items = items.slice(0); }
    var availableGenres = [], g, j, wanted = query.match(/genre=([^&]+)/);
    for (g = 0; g < items.length; g += 1) { for (j = 0; j < (items[g].genres || []).length; j += 1) { if (availableGenres.indexOf(items[g].genres[j]) < 0) { availableGenres.push(items[g].genres[j]); } } }
    if (!match && wanted && wanted[1]) { var filter = decodeURIComponent(wanted[1]); items = items.filter(function (item) { return (item.genres || []).indexOf(filter) >= 0; }); }
    done(null, {genres: availableGenres.sort(), items: items.slice(previewPage * pageSize, previewPage * pageSize + pageSize), page: previewPage, total: items.length});
   }, 0);
   return;
  }
  var x = new XMLHttpRequest(), ended = false, timer;
  function finish(error, value) { if (ended) { return; } ended = true; clearTimeout(timer); done(error, value); }
  pending.push(x);
  if (pending.length > 24) { pending.shift(); }
  x.open(method, WATCH_CONNECTION.base + path, true);
  x.setRequestHeader('X-Watch-Key', WATCH_CONNECTION.key);
  if (data) { x.setRequestHeader('Content-Type', 'application/json'); }
  x.onreadystatechange = function () {
   var value;
   if (x.readyState !== 4 || ended) { return; }
   if (x.status === 0) { finish('Cannot reach the Pi. Check the network and app connection.'); return; }
   try { value = JSON.parse(x.responseText); } catch (e) { finish('The Pi returned an unexpected response (HTTP ' + x.status + ').'); return; }
   if (x.status < 200 || x.status >= 300) { finish(value.error || 'Cannot connect to the Pi.'); return; }
   finish(null, value);
  };
  timer = setTimeout(function () { finish('The Pi is not responding. Reopen this section to try again.'); x.abort(); }, (path.indexOf('/api/suggestions') === 0 || path === '/api/import') ? 90000 : 16000);
  try { x.send(data ? JSON.stringify(data) : null); } catch (e) { finish('Cannot connect to the Pi.'); }
 }
 function image(id, variant) { if (WATCH_CONNECTION.key === 'SET_DURING_PI_PACKAGING') { return id || 'images/backdrop.png'; } return id ? WATCH_CONNECTION.base + '/art/' + encodeURIComponent(id) + '?key=' + encodeURIComponent(WATCH_CONNECTION.key) + (variant === 'thumb' ? '&size=thumb' : '') : 'images/backdrop.png'; }
 function cover(img, width, height, contain) {
  width = width * renderScale; height = height * renderScale;
  img.style.visibility = 'hidden'; img.style.width = Math.ceil(width) + 'px'; img.style.height = Math.ceil(height) + 'px'; img.style.left = '0px'; img.style.top = '0px';
  function fit() {
   var w = img.naturalWidth, h = img.naturalHeight, scale;
   if (!w || !h) { return; }
   scale = contain ? Math.min(width / w, height / h) : Math.max(width / w, height / h);
   img.style.width = Math.ceil(w * scale) + 'px'; img.style.height = Math.ceil(h * scale) + 'px';
   img.style.left = Math.round((width - w * scale) / 2) + 'px'; img.style.top = Math.round((height - h * scale) / 2) + 'px'; img.style.visibility = 'visible';
  }
  img.onload = fit; if (img.complete) { fit(); }
 }
 function branding(node, brands) {
  var i, img; node.innerHTML = '';
  for (i = 0; i < (brands || []).length; i += 1) {
   if (!/^(bbc|channel4|u|channel5|itv)$/.test(brands[i].id)) { continue; }
   img = document.createElement('img'); img.className = 'brandLogo'; img.src = 'images/brands/' + brands[i].id + '.png'; img.alt = brands[i].name; node.appendChild(img);
  }
 }
 function artwork(item, variant) { if (item && item.live && item.guide && item.guide.now && item.guide.now.art) { return image(item.guide.now.art, variant); } return item && item.channel_brand ? 'images/channels/' + item.channel_brand + '.png' : image(item && (item.hero || item.image), variant); }
 function describe(item) {
  text('title', item ? item.title : 'Your library');
  text('description', item ? item.description : 'Your favourites and recently watched shows, together.');
  if (item && item.live) {
   var guide = item.guide || {}, now = guide.now, next = guide.next;
   text('description', (now ? 'Now  ' + now.title : 'Programme information currently unavailable') + (next ? '\nNext  ' + next.time + '  ' + next.title : ''));
  }
  text('eyebrow', item ? ((item.content_rating ? item.content_rating + ' · ' : '') + (item.favourite ? '★ · ' : '') + (item.show_logo && item.show_title ? item.title + ' · ' : '') + (item.meta || '')) : 'Your library');
  branding(el('heroBrands'), item && item.brands);
  if (item && item.channel_brand) { var channelMark = document.createElement('img'); channelMark.className = 'channelMark'; channelMark.src = 'images/marks/' + item.channel_brand + '.png'; channelMark.alt = item.title; el('heroBrands').appendChild(channelMark); }
  var logo = el('showLogo'), mark = item && (item.show_logo || (group && group.show_logo));
  var logoSource = mark && WATCH_CONNECTION.key !== 'SET_DURING_PI_PACKAGING' ? WATCH_CONNECTION.base + '/show-logo/' + encodeURIComponent(mark) + '?key=' + encodeURIComponent(WATCH_CONNECTION.key) : '';
  if (logoSource) {
   logo.alt = item.show_title || (group && group.title) || item.title;
   if (logo._watchSource !== logoSource) {
    logo.style.display = 'none'; el('title').style.display = 'block'; logo._watchSource = logoSource;
    logo.onload = function () { logo._watchLoaded = true; logo.style.display = 'block'; el('title').style.display = 'none'; };
    logo.onerror = function () { logo._watchLoaded = false; logo.style.display = 'none'; el('title').style.display = 'block'; };
    logo._watchLoaded = false; logo.src = logoSource;
   } else { logo.style.display = logo._watchLoaded ? 'block' : 'none'; el('title').style.display = logo._watchLoaded ? 'none' : 'block'; }
  } else { logo._watchSource = ''; logo._watchLoaded = false; logo.onload = null; logo.onerror = null; logo.style.display = 'none'; el('title').style.display = 'block'; }
  var hero = el('heroImage'), frame = el('hero');
  var heroSource = artwork(item);
  if (hero._watchSource === heroSource) { return; }
  hero._watchSource = heroSource; hero.style.visibility = 'hidden';
  hero.onload = function () {
   var w = hero.naturalWidth, h = hero.naturalHeight, scale;
   if (!w || !h) { return; }
   scale = item && item.channel_brand && !(item.guide && item.guide.now && item.guide.now.art) ? Math.min(520 / w, 280 / h) : Math.max(520 / w, 280 / h);
   hero.style.width = Math.ceil(w * scale * renderScale) + 'px'; hero.style.height = Math.ceil(h * scale * renderScale) + 'px';
   hero.style.left = Math.round((440 + (520 - w * scale) / 2) * renderScale) + 'px'; hero.style.top = Math.round((280 - h * scale) / 2 * renderScale) + 'px'; hero.style.visibility = 'visible';
  };
  hero.onerror = function () { hero.style.visibility = 'hidden'; };
  hero.src = heroSource;
  if (hero.complete && hero.naturalWidth) { hero.onload(); }
 }
 function draw() {
  var root = el('cards'), i, card, img, shade, title, meta;
  root.innerHTML = '';
  for (i = 0; i < rows.length; i += 1) {
   card = document.createElement('div'); card.className = 'card'; card.id = 'card' + i;
   var picture = document.createElement('div'), brands = document.createElement('div');
   picture.className = 'picture'; brands.className = 'brands'; branding(brands, rows[i].brands);
   img = document.createElement('img'); var imageSource = rows[i].channel_brand ? artwork(rows[i], 'thumb') : image(rows[i].image, 'thumb'); img.alt = '';
   cover(img, 210, pageSize === 8 ? 105 : 93, !!rows[i].channel_brand && !(rows[i].guide && rows[i].guide.now && rows[i].guide.now.art));
   if (rows[i].channel_brand) { var channelBadge = document.createElement('div'), channelImage = document.createElement('img'); channelBadge.className = 'channelCorner';channelImage.className='channelCornerLogo'+(/^bbc(one|two|four|news)$/.test(rows[i].channel_brand) ? ' bbcChannelLogo' : ''); channelImage.src = 'images/marks/' + rows[i].channel_brand + '.png'; channelImage.alt = rows[i].title;channelBadge.appendChild(channelImage);card.appendChild(channelBadge); }
   img.onerror = function () { this.onerror = null; this.style.visibility = 'hidden'; this.src = 'images/backdrop.png'; };
   img.src = imageSource; if (img.complete && img.naturalWidth) { img.onload(); }
   shade = document.createElement('div'); shade.className = 'shade';
   title = document.createElement('div'); title.className = 'name'; title.textContent = rows[i].title;
   meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = rows[i].meta || '';
   if (rows[i].live) {
    var guide = rows[i].guide || {};
    title.textContent = guide.now ? 'Now  ' + guide.now.title : rows[i].title;
    meta.textContent = guide.next ? 'Next  ' + guide.next.time + '  ' + guide.next.title : 'Programme guide unavailable';
   }
   var synopsis = document.createElement('div'), track = document.createElement('div'), fill = document.createElement('div');
   synopsis.className='cardSynopsis';synopsis.textContent=rows[i].live ? ((rows[i].guide && rows[i].guide.now && (rows[i].guide.now.subtitle || rows[i].guide.now.description)) || '') : (rows[i].description || '');
   track.className='cardProgress';fill.style.width=Math.max(0,Math.min(100,Number(rows[i].progress)||0))+'%';track.appendChild(fill);track.style.visibility=rows[i].progress ? 'visible':'hidden';card.appendChild(synopsis);card.appendChild(track);
   picture.appendChild(img); card.appendChild(picture); card.appendChild(brands); card.appendChild(shade); card.appendChild(title); card.appendChild(meta); root.appendChild(card);
  }
  if (!rows.length) { root.innerHTML = '<div class="empty">' + (browseMode ? 'No available results in this section yet. Try another search or genre.' : 'No programmes here yet. Add favourites in your provider accounts.') + '</div>'; }
  text('pageLabel', (group ? (choosingSeason ? 'Series · ' : 'Episodes · ') : (browseMode === 'related' ? 'Similar · ' : (browseMode === 'featured' ? 'Featured · ' : ''))) + (total ? (page + 1) + ' / ' + Math.ceil(total / pageSize) : ''));
  focus = Math.max(0, Math.min(focus, rows.length - 1)); paint();
 }
 function activeNav() { return browseMode === 'shows' ? 1 : (browseMode === 'search' ? 9 : (browseMode === 'recommend' || browseMode === 'related' ? 10 : (browseMode === 'featured' ? 13 : (tab === 3 ? 8 : tab)))); }
 function paint() {
  var i;
  for (i = 0; i < navOrder.length; i += 1) { var navId = navOrder[i]; el('nav' + navId).className = (navId === activeNav() && !group ? 'active ' : '') + (area === 'nav' && navId === nav ? 'focus' : ''); }
  for (i = 0; i < rows.length; i += 1) { el('card' + i).className = 'card' + (rows[i].channel_brand ? ' channel' : '') + (area === 'grid' && i === focus ? ' focus' : ''); }
  if (highlights.length && !group && tab === 0 && !browseMode) { describe(highlights[highlightFocus]); } else if (rows[focus]) { describe(rows[focus]); }
  var showHighlights=highlights.length && !group && tab===0 && !browseMode;el('heroControls').style.display=showHighlights ? 'block':'none';el('nav14').style.display=showHighlights ? '':'none';el('nav15').style.display=showHighlights ? '':'none';el('nav16').style.display=showHighlights ? '':'none';text('heroCount',showHighlights ? (highlightFocus+1)+' / '+highlights.length : '');
  el('nav11').style.display = group && !group.film ? '' : 'none';
  el('nav12').style.display = group && !group.live ? '' : 'none';
  text('nav12',group && group.favourite ? 'Unfavourite' : 'Favourite');
  el('nav13').style.display = !group && tab === 3 ? '' : 'none';
 }
 function loadPage(target, nextFocus) {
  if (busy) { return; }
  if (!group && tab === 1 && !browseMode) { browseMode='shows';browseSnapshot=''; }
  pageSize = !group && (tab === 1 || (tab === 3 && browseMode !== 'featured') || (browseMode && browseMode !== 'featured')) ? 8 : 4;
  document.body.className = !group && pageSize === 8 ? 'all-shows' : '';
  var mine = ++generation;
  if (group) { el('nav7').style.display = 'none'; }
  busy = true; message('Loading…');
  var suggestionPath = '/api/suggestions?mode=' + encodeURIComponent(browseMode) + '&q=' + encodeURIComponent(browseQuery) + '&id=' + encodeURIComponent(relatedId) + '&genre=' + encodeURIComponent(genre) + '&snapshot=' + encodeURIComponent(target === 0 ? '' : browseSnapshot) + '&size=' + pageSize + '&page=' + target;
  request('GET', !group && browseMode ? suggestionPath : group ? '/api/' + (choosingSeason ? 'seasons/' : 'episodes/') + encodeURIComponent(group.id) + '?size=4&page=' + target + '&season=' + encodeURIComponent(season) : '/api/library?size=' + pageSize + '&tab=' + tab + '&page=' + target + '&genre=' + encodeURIComponent(genre), null, function (err, data) {
   if (mine !== generation) { return; } busy = false;
   if (err) { message(err); return; }
   if (data.snapshot) { browseSnapshot = data.snapshot; }
   if (!group && data.genres) { genreChoices = ['All genres'].concat(data.genres); el('nav7').style.display = data.genres.length ? '' : 'none'; text('nav7', 'Genre: ' + (genre || 'All')); }
   if (group || browseMode === 'search' || browseMode === 'related' || browseMode === 'featured') { el('nav7').style.display = 'none'; }
   rows = data.items; total = data.total; page = data.page; focus = nextFocus || 0; draw();
   if (!group && tab===0 && !browseMode) { request('GET','/api/suggestions?mode=highlights&size=8&page=0',null,function(error,result) { if (!error && mine===generation && !group && tab===0 && !browseMode) { highlights=result.items || [];highlightFocus=0;paint(); } }); }
   message(WATCH_CONNECTION.key === 'SET_DURING_PI_PACKAGING' ? 'LOCAL PREVIEW · Sample library · Playback requires the installed TV app.' : (group ? group.title + (choosingSeason ? ' · Choose a series' : ' · Choose an episode') : 'Favourites refresh automatically from your accounts.'));
  });
 }
 function paintSearch() { text('searchQuery', searchValue || 'Enter a title'); var box = el('searchKeys'), i, key; box.innerHTML = ''; for (i = 0; i < searchLetters.length; i += 1) { key = document.createElement('span'); key.textContent = searchLetters[i]; key.className = i === searchFocus ? 'selected' : ''; box.appendChild(key); } }
 function searchKey() { var value = searchLetters[searchFocus]; if (value === 'Search') { if (searchValue.length < 2) { return; } el('searchMenu').style.display = 'none'; browseQuery = searchValue; browseMode = 'search'; browseSnapshot = ''; group = null; tab = 1; area = 'grid'; loadPage(0); } else { if (value === 'Delete') { searchValue = searchValue.slice(0,-1); } else if (searchValue.length < 80) { searchValue += value === 'Space' ? ' ' : value; } paintSearch(); } }
 function setFavourite() { var chosen = group || rows[focus]; if (!chosen || chosen.live) { return; } request('POST','/api/favourite',{id:chosen.id,favourite:!chosen.favourite},function (error,data) { if (error) { message(error); return; } chosen.favourite = data.favourite; paint(); message(data.favourite ? 'Added to your local favourites' : 'Removed from your local favourites'); }); }
 function importProgramme(item) { var mine = ++generation; busy = true; livePlayback = false; selectedArtwork = artwork(item); playerView(true); waiting = true; paintProgramme({show_title:item.title,title:item.title,description:item.description,brands:item.brands,show_logo:item.show_logo}); setPreload(selectedArtwork); overlay('Loading episodes'); request('POST','/api/import',{ref:item.discovery_ref},function(error,data) { if (mine !== generation) { return; } busy = false; waiting = false; playerView(false); el('playback').style.display = 'none'; el('bufferSpinner').style.display = 'none'; if (error) { message(error); return; } previous={page:page,focus:focus,mode:browseMode,snapshot:browseSnapshot};previousTab=tab;group=data;choosingSeason=true;season='all';loadPage(0); }); }
 function setPreload(source) {
  var photo = el('preloadPhoto');
  if (!source) {
   // Detach the bitmap: hiding it alone can leave an Orsay graphics surface over native video.
   photo.onload = null; photo.onerror = null; photo.style.visibility = 'hidden'; photo.style.display = 'none'; photo.removeAttribute('src');
   var empty = document.createElement('img'); empty.id = 'preloadPhoto'; empty.alt = ''; empty.style.display = 'none'; empty.style.visibility = 'hidden';
   photo.parentNode.replaceChild(empty, photo); return;
  }
  photo.style.display = 'block'; cover(photo,960,540,false); photo.src = source;
  if (photo.complete && photo.naturalWidth) { photo.onload(); }
 }
 function paintGenres() { var box = el('genreChoices'), i, choice; box.innerHTML = ''; for (i = 0; i < genreChoices.length; i += 1) { choice = document.createElement('div'); choice.textContent = genreChoices[i]; choice.className = i === genreFocus ? 'selected' : ''; box.appendChild(choice); } if (box.children[genreFocus] && box.children[genreFocus].scrollIntoView) { box.children[genreFocus].scrollIntoView(false); } }
 function openGenres() { if (!genreChoices.length) { message('No genres are available in this section.'); return; } text('genreHeading', tab === 3 ? 'Filter films' : 'Filter shows'); genreFocus = Math.max(0, genreChoices.indexOf(genre || 'All genres')); el('genreMenu').style.display = 'block'; paintGenres(); }
 function moveNav(delta) { var order = [], index = 0, i; for (i = 0; i < navOrder.length; i += 1) { if (el('nav' + navOrder[i]).style.display !== 'none') { order.push(navOrder[i]); } } for (i = 0; i < order.length; i += 1) { if (order[i] === nav) { index = i; break; } } nav = order[Math.max(0, Math.min(order.length - 1, index + delta))]; }

 function changePage(delta) {
  var target = page + delta;
  if (target >= 0 && target < Math.ceil(total / pageSize)) { loadPage(target, delta < 0 ? pageSize - 1 : 0); }
 }
 function select() {
  var selected = rows[focus];
  if (busy) { return; }
  if (area === 'nav') {
   if (nav < 3) { group = null; browseMode = ''; browseSnapshot = ''; tab = nav; genre = ''; area = 'grid'; loadPage(0); }
   else if (nav === 7) { openGenres(); }
   else if (nav === 9) { searchFocus = 0; el('searchMenu').style.display = 'block'; paintSearch(); }
   else if (nav === 10) { group = null; tab = 1; browseMode = 'recommend'; browseSnapshot = ''; genre = ''; area = 'grid'; loadPage(0); }
   else if (nav === 11 && group) { relatedId = group.id; group = null; browseMode = 'related'; browseSnapshot = ''; area = 'grid'; loadPage(0); }
   else if (nav === 12 && group) { setFavourite(); }
   else if (nav === 16 && highlights.length) { area='hero';select();area='grid'; }
   else if (nav === 14 || nav === 15) { highlightFocus=(highlightFocus+(nav===14 ? highlights.length-1 : 1))%highlights.length;paint(); }
   else if (nav === 13) { browseMode = 'featured'; browseSnapshot = ''; area = 'grid'; loadPage(0); }
   else if (nav === 8) { group = null; browseMode = ''; browseSnapshot = ''; tab = 3; genre = ''; area = 'grid'; loadPage(0); }

   return;
  }
  if (area==='hero') { selected=highlights[highlightFocus]; }
  if (!selected) { return; }
  if (selected.discovery_ref) { importProgramme(selected); return; }
  if (!group && selected.home_episode) { start(selected); return; }
  if (!group && selected.film && selected.episode_id) { start(selected); return; }
  if (!group && !selected.live) {
   previous = {page: page, focus: focus, mode:browseMode, snapshot:browseSnapshot}; previousTab = tab; group = selected; choosingSeason = true; season = 'all'; loadPage(0);
  } else if (choosingSeason && group) {
   choosingSeason = false; season = selected.id; loadPage(0);
  } else { start(selected); }
 }
 function overlay(status, seconds) {
  el('playback').className = paused ? 'paused' : (waiting ? 'buffering' : '');
  if (waiting && el('preloadPhoto').style.display !== 'none') { el('playback').className += ' preloading'; }
  if (retryFailed) { el('playback').className += ' connection-error'; }
  el('bufferSpinner').style.display = waiting ? 'block' : 'none';
  clearTimeout(hide); text('playbackStatus', status); el('playback').style.display = 'block';
  el('qualityBadge').style.display = el('qualityBadge').textContent ? 'block' : 'none';
  if (seconds && !waiting) { hide = setTimeout(function () { el('playback').style.display = 'none'; el('qualityBadge').style.display = 'none'; }, seconds * 1000); }
 }
 function release(done) {
  var releasing = ticket; ticket = null;
  if (releasing) { request('DELETE', '/api/play/' + encodeURIComponent(releasing), {position: position, completed: finished}, function () { if (done) { done(); } }); }
  else if (done) { done(); }
 }
 function stop(showLibrary, done, keepOverlay) {
  trace(keepOverlay ? 'hold-player' : (showLibrary ? 'close-player' : 'stop-source'));
  if (showLibrary) { seekTransition = false; playerView(false); }
  clearTimeout(retryTimer); retryTimer = null; clearTimeout(bufferTimer); bufferTimer = null;
  generation += 1; clearTimeout(poll); clearTimeout(hide); clearTimeout(readyTimer); clearInterval(heartbeat);
  if (job) { request('DELETE', '/api/prepare/' + encodeURIComponent(job), null, function () {}); job = null; }
  var wasPlaying = playing; playing = false;
  if ((wasPlaying || frozenFrame) && player) { try { if (keepOverlay) { player.Pause(); frozenFrame = true; } else { player.Stop(); frozenFrame = false; } } catch (ignore) {} }
  paused = false; busy = false; timelineMode = false;
  if (keepOverlay) {
   waiting = true; recoveringView = true; playerView(true); overlay('Buffering… reconnecting');
  } else {
   setPreload(''); waiting = false; recoveringView = false; retryFailed = false; el('bufferSpinner').style.display = 'none';
  el('qualityBadge').style.display = 'none'; text('qualityBadge', '');
  el('playback').style.display = 'none'; el('shell').style.display = 'block'; document.body.style.background = '#0c111b'; document.documentElement.style.background = '#0c111b';
  if (showLibrary) { message('Ready. Choose another episode.'); }
  }
  release(done);
 }
 function begin(data) {
  ticket = data.ticket; job = null; trace('begin');
  currentEpisode = data.episode_id || currentEpisode; currentTitle = data.title; sourceOffset = Number(data.start_position || 0); position = sourceOffset; duration = Number(data.duration_seconds || 0); nativeOrigin = null; stableSince = 0; livePlayback = !!data.live; controlFocus = 1; timelineMode = false; finished = false; paintTransport();
  if (!player || typeof player.Play !== 'function') { stop(false); message('The Samsung native player is unavailable in this browser. Open the installed Smart Hub app.'); return; }
  if (frozenFrame) { try { player.Stop(); } catch (ignore) {} frozenFrame = false; }
  playing = true; busy = false; paused = false; waiting = true; recoveringView = false; retryFailed = false;
  playerView(true); document.body.style.background = 'rgba(0,0,0,0)'; document.documentElement.style.background = 'rgba(0,0,0,0)';
  setPreload(''); paintProgramme(data); overlay('Opening stream…');
  text('qualityBadge', data.spec && data.spec.quality); el('qualityBadge').style.display = data.spec && data.spec.quality ? 'block' : 'none';
  try {
   player.SetDisplayArea(0, 0, 960, 540);
   if (player.Play(data.url) === 0) { throw new Error('Rejected'); }
   try { if (typeof player.SetInitialBuffer === 'function') { player.SetInitialBuffer(1024 * 1024); } if (typeof player.SetPendingBuffer === 'function') { player.SetPendingBuffer(1024 * 1024); } if (typeof player.SetInitialTimeOut === 'function') { player.SetInitialTimeOut(45); } } catch (bufferOptionUnavailable) {}
   heartbeat = setInterval(function () { if (playing && ticket) { request('POST', '/api/play/' + ticket + '/heartbeat', {position: position}, function () {}); } }, 5000);
   readyTimer = setTimeout(function () { if (playing) { recover(); } }, 45000);
  } catch (e) { recover(); }
 }
 function presentation(item) { var now = item.live && item.guide && item.guide.now; if (!now) { return item; } return {live:true,title:now.title || item.title,show_title:item.title,description:now.subtitle || now.description || '',brands:item.brands,channel_brand:item.channel_brand}; }
 function paintProgramme(data) {
  var show = data.show_title || (group && group.title) || data.title;
  text('playingShow', show);
  var episodeTitle = data.title || '';
  if (episodeTitle === show) { episodeTitle = ''; }
  else { episodeTitle = episodeTitle.replace(/^(?:Series|Season)\s+[\w]+\s*[:·-]?\s*/i, '').replace(/^Episode\s+\d+\s*[:·-]?\s*/i, '').replace(/^\d+\.\s*/, ''); }
  text('playingTitle', episodeTitle);
  text('playingDescription', data.description || '');
  var series = String(data.season || ''), episode = Number(data.episode_number || 0), parts = [];
  if (livePlayback) { parts.push('LIVE'); }
  else {
   if (series && !/^(episodes|film)$/i.test(series)) { parts.push(/^\d+$/.test(series) ? 'Series ' + series : series); }
   if (episode) { parts.push('Episode ' + episode); }
  }
  if (data.duration_seconds && !livePlayback) { parts.push(Math.round(Number(data.duration_seconds)/60) + ' min'); }
  text('playingEpisode', parts.join(' · '));
  branding(el('playingBrands'), data.brands);
  if (data.channel_brand) { var mark=document.createElement('img');mark.className='channelMark';mark.src='images/marks/'+data.channel_brand+'.png';mark.alt=show;el('playingBrands').appendChild(mark); }
  var logo = el('playingLogo'); logo.style.display = 'none'; el('playingShow').style.display = 'block';
  logo.onload = null; logo.onerror = null;
  if (data.show_logo) {
   var source = WATCH_CONNECTION.base + '/show-logo/' + encodeURIComponent(data.show_logo) + '?key=' + encodeURIComponent(WATCH_CONNECTION.key);
   logo.alt = show;
   logo.onload = function () { logo.style.display = 'block'; el('playingShow').style.display = 'none'; };
   logo.onerror = function () { logo.style.display = 'none'; el('playingShow').style.display = 'block'; };
   if (logo._watchSource === source && logo.complete && logo.naturalWidth) { logo.onload(); }
   else { logo._watchSource = source; logo.src = source; }
  }
 }
 function start(item, startPosition, recovering) {
  if (!recovering) { retryCount = 0; }
  var programmeInfo=presentation(item);livePlayback=!!item.live || livePlayback;
  if (!recoveringView) { livePlayback = !!item.live; selectedArtwork = (item.hero || item.image) ? artwork(item) : (rows[focus] ? artwork(rows[focus]) : ''); playerView(true); waiting = true; paintProgramme({show_title:programmeInfo.show_title || (group ? group.title : item.title),title:programmeInfo.title,description:programmeInfo.description,duration_seconds:item.duration_seconds,season:item.season,episode_number:item.episode_number,channel_brand:programmeInfo.channel_brand,show_logo:item.show_logo || (group && group.show_logo),brands:item.brands || (group && group.brands)});setPreload(selectedArtwork);overlay('Preparing'); }
  if (recoveringView) { waiting = true; overlay('Buffering… preparing stream'); }
  var mine = ++generation;
  busy = true; message('Preparing ' + item.title + '… Return cancels.');
  var payload = {episode_id: item.episode_id || item.id};
  if (typeof startPosition === 'number') { payload.start_position = startPosition; }
  currentEpisode = payload.episode_id;
  request('POST', '/api/prepare', payload, function (err, data) {
   if (mine !== generation) { if (data && data.job) { request('DELETE', '/api/prepare/' + data.job, null, function () {}); } return; }
   if (err) { busy = false; if (recovering || item.live) { retryAgain(item, startPosition); } else { stop(true); message(err); } return; }
   job = data.job;
   function check() {
    request('GET', '/api/prepare/' + encodeURIComponent(job), null, function (error, value) {
     if (mine !== generation) { return; }
     if (error || value.state === 'failed') { job = null; busy = false; if (recovering || item.live) { retryAgain(item, startPosition); } else { stop(true); message(error || value.error); } }
     else if (value.state === 'ready') { begin(value); }
     else { poll = setTimeout(check, 1500); }
    });
   }
   poll = setTimeout(check, 500);
  });
 }
 function clock(seconds) {
  seconds = Math.max(0, Math.floor(seconds)); var h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60, sec = seconds % 60;
  return (h ? h + ':' + (m < 10 ? '0' : '') : '') + m + ':' + (sec < 10 ? '0' : '') + sec;
 }
 function paintTransport() {
  var shownPosition = timelineMode ? seekPreview : position;
  el('playbackHelp').className = timelineMode ? 'timeline-focus' : '';
  var i; text('timeLabel', livePlayback ? 'Live' : (timelineMode ? 'Jump to ' : '') + clock(shownPosition) + (duration ? ' / ' + clock(duration) : ''));
  text('remainingLabel', !livePlayback && duration ? clock(Math.max(0, duration - shownPosition)) + ' remaining' : '');
  var timelinePercent = duration && !livePlayback ? Math.min(100, Math.max(0, shownPosition / duration * 100)) : 0;
  el('timelineFill').style.width = timelinePercent + '%'; el('timelineDot').style.left = timelinePercent + '%'; el('timelineDot').style.display = livePlayback ? 'none' : 'block';
  var controls = [1,3]; for (i = 0; i < controls.length; i += 1) { var control = controls[i]; el('control' + control).className = control === controlFocus ? 'selected' : ''; el('control' + control).style.display = livePlayback && control === 3 ? 'none' : ''; }
  text('control1', paused ? 'Play' : 'Pause');
  text('transportHint', timelineMode ? 'Left / Right · Scrub faster with repeated presses    OK · Play from here    Down / Return · Cancel' : 'Up · Timeline    Arrows · Select    OK · Activate    Return · Save and close');
 }
 function scrub(delta) {
  var now = new Date().getTime(); seekRepeats = now - lastSeekPress < 700 ? seekRepeats + 1 : 0; lastSeekPress = now;
  var step = seekRepeats > 12 ? 120 : (seekRepeats > 6 ? 60 : (seekRepeats > 2 ? 30 : 10));
  seekPreview = Math.max(0, Math.min(duration ? Math.max(0, duration - 2) : 86400, seekPreview + delta * step));
  paintTransport(); overlay(paused ? 'Paused · Choose a position' : 'Choose a position');
 }
 function togglePause(wantPause) {
  try { if (wantPause) { player.Pause(); paused = true; } else { player.Resume(); paused = false; } paintTransport(); overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 3); } catch (ignore) {}
 }
 function seek(delta) {
  if (livePlayback) { overlay('Seeking is available for episodes. This is live TV.', 3); return; }
  var target = Math.max(0, Math.min(duration ? Math.max(0, duration - 2) : 86400, position + delta));
  var item = {id: currentEpisode, title: currentTitle};
  seekTransition = true; playerView(true); trace('seek');
  var expected = generation + 1; retryCount = 0; retryFailed = false; recoveryItem = item; recoveryTarget = target;
  stop(false, function () { if (generation === expected) { start(item, target, true); } }, true);
 }
 function timeUpdate(milliseconds) {
  if (!playing) { return; }
  var value = Number(milliseconds) / 1000;
  if (!isFinite(value) || value < 0) { return; }
  if (nativeOrigin === null) { nativeOrigin = value < 3 ? 0 : value; }
  if (sourceOffset + value - nativeOrigin < position - 2) { nativeOrigin = sourceOffset + value - position; }
  var previousPosition = position;
  position = Math.max(position, sourceOffset + value - nativeOrigin);
  if (position > previousPosition + 0.1) { seekTransition = false; if (waiting || el('preloadPhoto').style.display !== 'none') { setPreload(''); waiting = false; clearTimeout(bufferTimer); bufferTimer = null; overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 3); } }
  if (duration) { position = Math.min(duration, position); }
  paintTransport(); if (!seekTransition) { clearTimeout(readyTimer); }
  if (!paused && !bufferTimer) { if (!stableSince) { stableSince = new Date().getTime(); } else if (new Date().getTime() - stableSince > 30000) { retryCount = 0; } }
 }
 function retryAgain(item, target) {
  if (retryTimer) { return; }
  retryCount += 1;
  var maxRetries = livePlayback ? 6 : 3;
  if (retryCount > maxRetries) { busy = false; waiting = false; retryFailed = true; recoveringView = true; overlay('Connection unavailable. OK · Try again    Return · Save and close'); return; }
  busy = true; waiting = true; recoveringView = true; recoveryItem = item; recoveryTarget = target; overlay('Buffering… reconnecting ' + retryCount + ' / ' + maxRetries); message('Reconnecting ' + retryCount + ' / ' + maxRetries + '. Your position is saved. Return cancels.');
  retryTimer = setTimeout(function () { retryTimer = null; busy = false; start(item, target, true); }, [0,2000,5000,10000][Math.min(retryCount,3)]);
 }
 function recover() {
  if (!playing || retryTimer) { return; }
  var item = {id: currentEpisode, title: currentTitle}, target = livePlayback ? 0 : Math.max(0, position - 3), expected = generation + 1;
  stop(false, function () { if (generation === expected) { retryAgain(item, target); } }, true);
 }
 function buffering() {
  if (!playing) { return; }
  stableSince = 0; waiting = true; overlay('Buffering… keeping your place'); clearTimeout(bufferTimer);
  bufferTimer = setTimeout(function () { bufferTimer = null; recover(); }, 45000);
 }
 function back() {
  trace('back');
  if (playing && timelineMode) { timelineMode = false; paintTransport(); overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 3); return; }
  if (busy || playing || recoveringView) { stop(true); return; }
  if (group && !choosingSeason) { choosingSeason = true; loadPage(0); return; }
  if (group) { group = null; choosingSeason = false; tab = previousTab; browseMode = previous.mode || ''; browseSnapshot = previous.snapshot || ''; loadPage(previous.page, previous.focus); return; }
  if (area === 'grid') { area = 'nav'; nav = !group ? activeNav() : (tab === 3 ? 8 : tab); paint(); return; }
  if (api) { api.sendReturnEvent(); }
 }
 function nativeVolume() {
  if (typeof WatchVolume !== 'undefined') { WatchVolume.init(keys); return; }
  // 2012 Orsay requires the capital-S onShow lifecycle, after sendReadyEvent.
  try { el('pluginObjectNNavi').SetBannerState(1); } catch (ignoreBanner) {}
  if (typeof Common === 'undefined' || !Common.API || !Common.API.Plugin) { return; }
  var plugin;
  try { plugin = new Common.API.Plugin(); } catch (ignorePlugin) { return; }
  var names = ['KEY_VOL_UP','KEY_VOL_DOWN','KEY_MUTE'], fallback = [7,11,27], i;
  for (i = 0; i < names.length; i += 1) {
   try { plugin.unregistKey(typeof keys[names[i]] === 'number' ? keys[names[i]] : fallback[i]); } catch (ignoreKey) {}
  }
 }
 function key(e) {
  e = e || window.event; var k = e.keyCode; lastInput = new Date().getTime();
  function is(name, fallback) { return k === (typeof keys[name] === 'number' ? keys[name] : fallback); }
  if (is('KEY_VOL_UP', 7) || is('KEY_VOL_DOWN', 11) || is('KEY_MUTE', 27)) {
   if (typeof WatchVolume !== 'undefined' && WatchVolume.handle(k)) { if (api) { api.blockNavigation(e); } if (e.preventDefault) { e.preventDefault(); } return false; }
   return true;
  }
  if (is('KEY_EXIT', 10182)) { shutdown(); if (api) { api.sendExitEvent(); } return false; }
  if (api) { api.blockNavigation(e); } if (e.preventDefault) { e.preventDefault(); }
  if (el('searchMenu').style.display === 'block') { if (is('KEY_RETURN',10009) || k === 8 || k === 27) { el('searchMenu').style.display = 'none'; } else if (is('KEY_ENTER',13)) { searchKey(); } else { if (is('KEY_LEFT',37)) { searchFocus = Math.max(0,searchFocus-1); } if (is('KEY_RIGHT',39)) { searchFocus = Math.min(searchLetters.length-1,searchFocus+1); } if (is('KEY_UP',38)) { searchFocus = Math.max(0,searchFocus-6); } if (is('KEY_DOWN',40)) { searchFocus = Math.min(searchLetters.length-1,searchFocus+6); } paintSearch(); } return false; }
  if (el('genreMenu').style.display === 'block') { if (is('KEY_UP', 38)) { genreFocus = Math.max(0, genreFocus - 1); paintGenres(); } else if (is('KEY_DOWN', 40)) { genreFocus = Math.min(genreChoices.length - 1, genreFocus + 1); paintGenres(); } else if (is('KEY_ENTER', 13)) { genre = genreFocus ? genreChoices[genreFocus] : ''; browseSnapshot = ''; group = null; if (tab === 2) { tab = 1; } area = 'grid'; el('genreMenu').style.display = 'none'; loadPage(0); } else if (is('KEY_RETURN', 10009) || k === 8 || k === 27) { el('genreMenu').style.display = 'none'; } return false; }
  if (el('credits').style.display === 'block') { if (is('KEY_ENTER', 13) || is('KEY_RETURN', 10009) || k === 8 || k === 27) { el('credits').style.display = 'none'; } return false; }
  if (is('KEY_INFO', 457) && !playing && !busy) { el('credits').style.display = 'block'; return false; }
  if (is('KEY_RETURN', 10009) || k === 8 || k === 27) { back(); return false; }
  if (recoveringView && !playing) { if (retryFailed && (is('KEY_ENTER', 13) || is('KEY_PLAY', 415))) { retryCount = 0; retryFailed = false; retryAgain(recoveryItem, recoveryTarget); } return false; }
  if (playing) {
   if (timelineMode) {
    if (is('KEY_LEFT', 37) || is('KEY_RIGHT', 39)) { scrub(is('KEY_RIGHT', 39) ? 1 : -1); }
    else if (is('KEY_DOWN', 40)) { timelineMode = false; paintTransport(); overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 3); }
    else if (is('KEY_ENTER', 13) || is('KEY_PLAY', 415)) { var jump = seekPreview - position; timelineMode = false; seek(jump); }
    else if (is('KEY_PAUSE', 19)) { togglePause(true); }
    else if (is('KEY_STOP', 413)) { stop(true); }
    return false;
   }
   if (is('KEY_UP', 38) && !livePlayback && !waiting) { timelineMode = true; seekPreview = position; seekRepeats = 0; lastSeekPress = 0; paintTransport(); overlay(paused ? 'Paused · Choose a position' : 'Choose a position'); }
   else if (is('KEY_STOP', 413)) { stop(true); }
   else if (is('KEY_FF', 417) || is('KEY_RW', 412)) { seek(is('KEY_FF', 417) ? 30 : -30); }
   else if (is('KEY_PAUSE', 19)) { togglePause(true); }
   else if (is('KEY_PLAY', 415)) { togglePause(false); }
   else if (is('KEY_LEFT', 37) || is('KEY_RIGHT', 39)) {
    if (el('playback').style.display !== 'none') {
     var availableControls = livePlayback ? [1] : [1,3], controlIndex = availableControls.indexOf(controlFocus);
     controlFocus = availableControls[Math.max(0, Math.min(availableControls.length - 1, controlIndex + (is('KEY_RIGHT', 39) ? 1 : -1)))];
    }
    paintTransport(); overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 5);
   } else if (is('KEY_ENTER', 13)) {
    if (el('playback').style.display === 'none') { controlFocus = 1; }
    if (controlFocus === 1) { togglePause(!paused); }
    else if (controlFocus === 3) { seek(-position); }
   } else { overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 3); }
   return false;
  }
  if (busy) { return false; }
  if (area==='nav' && (nav===14 || nav===15) && is('KEY_PLAY',415) && highlights[highlightFocus]) { area='hero';select();area='grid';return false; }
  if (is('KEY_YELLOW',403)) { setFavourite(); return false; }
  if (is('KEY_PLAY', 415) && !group && rows[focus] && rows[focus].resume_episode) { start({id: rows[focus].resume_episode, title: rows[focus].title}); return false; }
  if (is('KEY_ENTER', 13) || is('KEY_PLAY', 415)) { select(); return false; }
  if (is('KEY_UP', 38)) {
   if (area === 'nav' && el('heroControls').style.display !== 'none') { nav = 16; }
   else if (area === 'grid' && focus >= 4) { focus -= 4; }
   else if (area === 'grid' && page > 0) { loadPage(page - 1, pageSize - 4 + focus); }
   else if (area === 'grid') { area = 'nav'; nav = !group ? activeNav() : (tab === 3 ? 8 : tab); }
  }
  else if (is('KEY_DOWN', 40)) {
   if (area === 'nav' && (nav===14 || nav===15 || nav===16)) { nav=0; }
   else if (area === 'nav') { area = 'grid'; }
   else if (focus + 4 < rows.length) { focus += 4; }
   else if (page + 1 < Math.ceil(total / pageSize)) { loadPage(page + 1, focus % 4); }
  }
  else if (is('KEY_LEFT', 37)) {
   if (area === 'nav') { moveNav(-1); }
   else if (focus % 4 === 0 && page > 0) { loadPage(page - 1, Math.floor(focus / 4) * 4 + 3); }
   else if (focus % 4 > 0) { focus -= 1; }
  }
  else if (is('KEY_RIGHT', 39)) {
   if (area === 'nav') { moveNav(1); }
   else if ((focus % 4 === 3 || focus === rows.length - 1) && page + 1 < Math.ceil(total / pageSize)) { loadPage(page + 1, Math.floor(focus / 4) * 4); }
   else if (focus < rows.length - 1) { focus += 1; }
  }
  else if (is('KEY_FF', 417)) { changePage(1); }
  else if (is('KEY_RW', 412)) { changePage(-1); }
  paint(); return false;
 }
 function init() {
  text('appVersion', 'Watch ' + buildVersion);
  if (typeof Common !== 'undefined') { api = new Common.API.Widget(); keys = new Common.API.TVKeyValue(); }
  player = el('player');
  player.OnBufferingStart = 'Watch.buffering'; player.OnBufferingComplete = 'Watch.buffered';
  player.OnCurrentPlayTime = 'Watch.tick'; player.OnRenderingComplete = 'Watch.ended';
  player.OnConnectionFailed = 'Watch.failed'; player.OnRenderError = 'Watch.failed';
  player.OnNetworkDisconnected = 'Watch.failed'; player.OnStreamNotFound = 'Watch.failed';
  player.OnStreamInfoReady = 'Watch.streamReady';
  var previousShow = window.onShow;
  window.onShow = function () { if (typeof previousShow === 'function') { previousShow.apply(window, arguments); } nativeVolume(); };
  if (api) { api.sendReadyEvent(); }
  el('remote').focus();
  if (WATCH_CONNECTION.key === 'SET_DURING_PI_PACKAGING') { loadPage(0); }
  else { request('POST', '/api/session', {app_version:buildVersion, viewport_width: window.innerWidth, viewport_height: window.innerHeight, screen_width: window.screen.width, screen_height: window.screen.height}, function () { loadPage(0); }); }
  featureTimer = setInterval(function () { if ((browseMode !== 'featured' && !(tab===0 && !browseMode && highlights.length)) || group || busy || playing || area !== 'grid' || !rows.length || new Date().getTime()-lastInput < 18000) { return; } if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { return; } if (tab===0 && !browseMode && highlights.length) { highlightFocus=(highlightFocus+1)%highlights.length; } else { focus=(focus+1)%rows.length; } paint(); },18000);
  guideRefresh = setInterval(function () { if (tab === 2 && !group && !playing && !busy) { loadPage(page, focus); } }, 60000);
 }
 function shutdown() { if (typeof WatchVolume !== 'undefined') { WatchVolume.shutdown(); } clearInterval(featureTimer);clearInterval(guideRefresh); stop(false); }
 return {init: init, key: key, shutdown: shutdown,
  streamReady: function () { try { player.SetDisplayArea(0, 0, 960, 540); } catch (ignore) {} },
  buffering: buffering,
  buffered: function () { if (!playing) { return; } setPreload(''); waiting = false; clearTimeout(bufferTimer); bufferTimer = null; if (!seekTransition) { clearTimeout(readyTimer); } overlay(paused ? 'Paused' : 'Playing', paused ? 0 : 3); },
  tick: timeUpdate,
  ended: function () { trace('ended'); if (!playing || seekTransition) { return; } if (livePlayback || !duration || position < duration - 5) { recover(); } else { finished = !!duration; stop(true); } },
  failed: recover
 };
}());
