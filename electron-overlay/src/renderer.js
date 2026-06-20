const panel       = document.getElementById('panel');
const greeting     = document.getElementById('greeting');
const greetingText = document.getElementById('greeting-text');
const input        = document.getElementById('input');
const hint          = document.getElementById('hint');
const glyph         = document.getElementById('glyph');
const output        = document.getElementById('output');
const inputRow      = document.getElementById('input-row');
const actions       = document.getElementById('actions');

let isRunning = false;
let buffer = '';

function timeGreeting() {
  const h = new Date().getHours();
  if (h < 5)  return "Still up, Shlok? 🌙";
  if (h < 12) return "Morning, Shlok ☀️";
  if (h < 17) return "Afternoon, Shlok";
  if (h < 21) return "Evening, Shlok";
  return "Late one, Shlok 🌙";
}

function resizeToContent() {
  requestAnimationFrame(() => {
    window.aura.resize(panel.scrollHeight + 20);
  });
}

function resetToIdle() {
  isRunning = false;
  input.disabled = false;
  input.value = '';
  buffer = '';
  output.textContent = '';
  output.classList.remove('visible');
  inputRow.classList.remove('has-output');
  hint.classList.remove('visible');
  greeting.style.display = 'block';
  actions.style.display = 'flex';
  greetingText.textContent = timeGreeting();
  setGlyphState('idle');
  resizeToContent();
}

function showPanel() {
  panel.classList.add('visible');
  resetToIdle();
  setTimeout(() => input.focus(), 60);
}

function hidePanel() {
  panel.classList.remove('visible');
}

window.aura.onShown(showPanel);
window.aura.onHidden(hidePanel);
window.aura.onHotkeyAgain(() => input.focus());

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (isRunning) return; // don't dismiss mid-task on accidental Escape
    window.aura.escapePressed();
  }
});

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && input.value.trim() && !isRunning) {
    runCommand(input.value.trim());
  }
});

actions.addEventListener('click', (e) => {
  const chip = e.target.closest('.action-chip');
  if (!chip) return;
  const cmd = chip.dataset.cmd;
  if (cmd.endsWith(' ')) {
    // Needs user to finish typing (e.g. "new project called ")
    input.value = cmd;
    input.focus();
    input.setSelectionRange(cmd.length, cmd.length);
  } else {
    runCommand(cmd);
  }
});

function setGlyphState(state) {
  glyph.classList.remove('busy');
  if (state === 'busy') {
    glyph.classList.add('busy');
    glyph.style.background = 'var(--accent)';
    glyph.style.boxShadow = '0 0 10px var(--accent)';
  } else if (state === 'success') {
    glyph.style.background = 'var(--success)';
    glyph.style.boxShadow = '0 0 10px var(--success)';
  } else if (state === 'error') {
    glyph.style.background = 'var(--error)';
    glyph.style.boxShadow = '0 0 10px var(--error)';
  } else {
    glyph.style.background = 'var(--accent)';
    glyph.style.boxShadow = '0 0 10px var(--accent)';
  }
}

function colorizeLine(line) {
  if (line.includes('✓')) return `<span class="line-success">${escapeHtml(line)}</span>`;
  if (line.includes('✗')) return `<span class="line-error">${escapeHtml(line)}</span>`;
  if (/[🔍🧠📋⚡🎯📅🐙💻🚀]/.test(line)) return `<span class="line-accent">${escapeHtml(line)}</span>`;
  if (line.trim() === '' || line.includes('──')) return `<span class="line-dim">${escapeHtml(line)}</span>`;
  return escapeHtml(line);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function runCommand(text) {
  isRunning = true;
  input.disabled = true;
  hint.classList.remove('visible');
  greeting.style.display = 'none';
  actions.style.display = 'none';
  setGlyphState('busy');

  output.classList.add('visible');
  inputRow.classList.add('has-output');
  buffer = '';
  output.innerHTML = '';
  resizeToContent();

  window.aura.runCommand(
    text,
    (chunk) => {
      buffer += chunk;
      output.innerHTML = buffer.split('\n').map(colorizeLine).join('\n');
      output.scrollTop = output.scrollHeight;
      resizeToContent();
    },
    () => {
      isRunning = false;
      input.disabled = false;
      input.value = '';
      setGlyphState('success');
      hint.textContent = '↵ run another · esc close';
      hint.classList.add('visible');
      input.focus();
      resizeToContent();
    },
    (err) => {
      isRunning = false;
      input.disabled = false;
      setGlyphState('error');
      buffer += `\n✗ ${err}`;
      output.innerHTML = buffer.split('\n').map(colorizeLine).join('\n');
      resizeToContent();
    }
  );
}