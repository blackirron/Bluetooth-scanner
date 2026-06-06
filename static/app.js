const devices = new Map();
let scanning = false;
let ws = null;

const $ = (sel) => document.querySelector(sel);

const scanBtn = $('#scanBtn');
const clearBtn = $('#clearBtn');
const typeFilter = $('#typeFilter');
const searchInput = $('#searchInput');
const deviceGrid = $('#deviceGrid');
const emptyState = $('#emptyState');
const scanBanner = $('#scanBanner');
const deviceCount = $('#deviceCount');
const adapterStatus = $('#adapterStatus');
const deviceModal = $('#deviceModal');
const modalBody = $('#modalBody');

function rssiBars(rssi) {
  if (rssi == null) return '';
  let level = 1;
  if (rssi > -50) level = 4;
  else if (rssi > -65) level = 3;
  else if (rssi > -80) level = 2;
  const bars = [1, 2, 3, 4].map(i =>
    `<span class="${i <= level ? 'active' : ''}"></span>`
  ).join('');
  return `<span class="rssi-bar">${bars}</span> ${rssi} dBm`;
}

function typeBadge(type) {
  const labels = { ble: 'BLE', classic: 'Classic', paired: 'Paired' };
  return `<span class="badge badge-${type}">${labels[type] || type}</span>`;
}

function renderCard(device) {
  const isMaker = device.extra?.is_maker_board;
  const connected = device.extra?.connected;
  const classes = [
    'device-card',
    `type-${device.device_type}`,
    isMaker ? 'is-maker' : '',
  ].filter(Boolean).join(' ');

  const badges = [
    typeBadge(device.device_type),
    isMaker ? '<span class="badge badge-maker">Maker Board</span>' : '',
    connected ? '<span class="badge badge-connected">Connected</span>' : '',
    device.extra?.paired ? '<span class="badge badge-paired">Paired</span>' : '',
  ].filter(Boolean).join('');

  return `
    <div class="${classes}" data-address="${device.address}">
      <div class="card-header">
        <div>
          <div class="card-name">${esc(device.name)}</div>
          <div class="card-address">${esc(device.address)}</div>
        </div>
        <div class="card-badges">${badges}</div>
      </div>
      <div class="card-meta">
        ${device.rssi != null ? `<div class="meta-item">${rssiBars(device.rssi)}</div>` : ''}
        ${device.manufacturer ? `<div class="meta-item">${esc(device.manufacturer)}</div>` : ''}
        ${device.uuids?.length ? `<div class="meta-item">${device.uuids.length} service(s)</div>` : ''}
      </div>
    </div>
  `;
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function getFilteredDevices() {
  const query = searchInput.value.toLowerCase().trim();
  const type = typeFilter.value;

  return [...devices.values()].filter(d => {
    if (type === 'ble' && d.device_type !== 'ble') return false;
    if (type === 'classic' && d.device_type !== 'classic') return false;
    if (type === 'paired' && d.device_type !== 'paired' && !d.extra?.paired) return false;
    if (type === 'maker' && !d.extra?.is_maker_board) return false;
    if (query) {
      const hay = `${d.name} ${d.address} ${d.manufacturer || ''}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });
}

function render() {
  const filtered = getFilteredDevices();
  deviceCount.textContent = `${filtered.length} device${filtered.length !== 1 ? 's' : ''}`;

  if (filtered.length === 0) {
    emptyState.classList.remove('hidden');
    deviceGrid.querySelectorAll('.device-card').forEach(el => el.remove());
    return;
  }

  emptyState.classList.add('hidden');
  const html = filtered.map(renderCard).join('');
  deviceGrid.innerHTML = html;

  deviceGrid.querySelectorAll('.device-card').forEach(card => {
    card.addEventListener('click', () => {
      const dev = devices.get(card.dataset.address);
      if (dev) showModal(dev);
    });
  });
}

function showModal(device) {
  const rows = [
    ['Type', device.device_type.toUpperCase()],
    ['Address', device.address],
    ['Connectable', device.connectable ? 'Yes' : 'No'],
    ['RSSI', device.rssi != null ? `${device.rssi} dBm` : 'N/A'],
    ['Manufacturer', device.manufacturer || 'Unknown'],
    ['Last Seen', device.last_seen ? new Date(device.last_seen).toLocaleString() : 'N/A'],
  ];

  if (device.extra?.paired != null) rows.push(['Paired', device.extra.paired ? 'Yes' : 'No']);
  if (device.extra?.connected != null) rows.push(['Connected', device.extra.connected ? 'Yes' : 'No']);
  if (device.extra?.icon) rows.push(['Icon', device.extra.icon]);
  if (device.extra?.tx_power != null) rows.push(['TX Power', `${device.extra.tx_power} dBm`]);

  const uuidHtml = device.uuids?.length
    ? `<div class="uuid-list">${device.uuids.map(u => `<span class="detail-value">${esc(u)}</span>`).join('')}</div>`
    : 'None';

  modalBody.innerHTML = `
    <div class="modal-title">${esc(device.name)}</div>
    <div class="modal-address">${esc(device.address)}</div>
    <div class="detail-grid">
      ${rows.map(([label, val]) => `
        <div class="detail-row">
          <span class="detail-label">${label}</span>
          <span class="detail-value">${esc(String(val))}</span>
        </div>
      `).join('')}
      <div class="detail-row">
        <span class="detail-label">Services</span>
        <div>${uuidHtml}</div>
      </div>
    </div>
  `;
  deviceModal.classList.remove('hidden');
}

function closeModal() {
  deviceModal.classList.add('hidden');
}

function setScanning(val) {
  scanning = val;
  scanBtn.disabled = val;
  scanBanner.classList.toggle('hidden', !val);
  scanBtn.innerHTML = val
    ? '<div class="spinner" style="width:16px;height:16px;border-width:2px"></div> Scanning…'
    : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
         <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
       </svg> Scan Devices`;
}

function updateAdapterStatus(adapter) {
  const adapters = adapter?.adapters || [];
  if (adapters.length === 0) {
    adapterStatus.innerHTML = '<span class="status-dot offline"></span><span>No adapter found</span>';
    return;
  }
  const a = adapters[0];
  const dot = a.powered ? 'online' : 'offline';
  const state = a.powered
    ? (a.discovering ? 'Discovering' : 'Ready')
    : 'Powered off';
  adapterStatus.innerHTML =
    `<span class="status-dot ${dot}"></span><span>${esc(a.name || a.alias)} — ${state}</span>`;
}

function upsertDevices(list) {
  for (const d of list) {
    devices.set(d.address, d);
  }
  render();
}

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'initial') {
      upsertDevices(msg.devices);
      setScanning(msg.scanning);
      updateAdapterStatus(msg.adapter);
    } else if (msg.type === 'scan_complete') {
      upsertDevices(msg.devices);
      setScanning(false);
    } else if (msg.type === 'status') {
      updateAdapterStatus(msg.adapter);
    }
  };

  ws.onclose = () => setTimeout(connectWs, 2000);
}

async function startScan() {
  if (scanning) return;
  setScanning(true);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send('scan');
  } else {
    try {
      await fetch('/api/scan', { method: 'POST' });
      const poll = setInterval(async () => {
        const res = await fetch('/api/devices');
        const data = await res.json();
        upsertDevices(data.devices);
        if (!data.scanning) {
          clearInterval(poll);
          setScanning(false);
        }
      }, 1000);
    } catch {
      setScanning(false);
    }
  }
}

async function clearDevices() {
  await fetch('/api/clear', { method: 'POST' });
  devices.clear();
  render();
}

scanBtn.addEventListener('click', startScan);
clearBtn.addEventListener('click', clearDevices);
typeFilter.addEventListener('change', render);
searchInput.addEventListener('input', render);
$('#modalClose').addEventListener('click', closeModal);
$('#modalBackdrop').addEventListener('click', closeModal);

connectWs();
