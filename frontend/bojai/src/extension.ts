import * as vscode from 'vscode';
import { getBuildTabContent } from './tabs/buildTab';
import { getUseTabContent } from './tabs/useTab';
import { DataTabConfig } from './tabs/dataTab';

function getNonce(): string {
	let text = '';
	const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
	for (let i = 0; i < 32; i++) {
		text += possible.charAt(Math.floor(Math.random() * possible.length));
	}
	return text;
}

class BojaiViewProvider implements vscode.WebviewViewProvider {
	resolveWebviewView(webviewView: vscode.WebviewView): void {
		webviewView.webview.options = { enableScripts: true };

		const cfg = vscode.workspace.getConfiguration('bojai');
		const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
		const tabCfg: DataTabConfig = {
			wsRoot,
			defaultModel: cfg.get('defaultModel', 'gpt-4o-mini'),
			defaultProvider: cfg.get('defaultProvider', 'openai'),
		};
		const buildUrl: string = cfg.get('buildServerUrl', 'http://localhost:8000');
		const runtimeUrl: string = cfg.get('runtimeServerUrl', 'http://localhost:8001');

		webviewView.webview.html = this.getHtml(webviewView.webview, tabCfg, buildUrl, runtimeUrl);
	}

	private getHtml(
		webview: vscode.Webview,
		tabCfg: DataTabConfig,
		buildUrl: string,
		runtimeUrl: string
	): string {
		const nonce = getNonce();
		const runtimeConfig = JSON.stringify({ buildUrl, runtimeUrl });

		return `<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta http-equiv="Content-Security-Policy" content="
		default-src 'none';
		style-src ${webview.cspSource} 'unsafe-inline';
		script-src 'nonce-${nonce}';
		connect-src http://localhost:* https://localhost:*;
	">
	<style>
		body {
			font-family: var(--vscode-font-family);
			color: var(--vscode-foreground);
			font-size: var(--vscode-font-size);
			padding: 8px;
		}
		.tabs-row {
			display: flex;
			justify-content: space-between;
			align-items: flex-start;
			gap: 12px;
			margin-bottom: 12px;
		}
		.main-tabs { display: flex; gap: 6px; }
		.sub-tabs {
			display: flex;
			flex-direction: column;
			gap: 6px;
			padding-left: 12px;
			border-left: 1px solid var(--vscode-panel-border);
		}
		.tab {
			padding: 4px 10px;
			border: 1px solid var(--vscode-button-border, transparent);
			border-radius: 4px;
			background: var(--vscode-button-secondaryBackground);
			color: var(--vscode-button-secondaryForeground);
			text-align: center;
			cursor: pointer;
			user-select: none;
		}
		.tab.active {
			background: var(--vscode-button-background);
			color: var(--vscode-button-foreground);
		}
		.main-panel.hidden, .sub-panel.hidden { display: none; }
		.sub-panel {
			border-top: 1px solid var(--vscode-panel-border);
			padding-top: 10px;
			margin-top: 4px;
		}

		/* Forms */
		.field { margin-bottom: 8px; }
		.field label {
			display: block;
			font-size: 11px;
			color: var(--vscode-descriptionForeground);
			margin-bottom: 3px;
		}
		.field input {
			width: 100%;
			box-sizing: border-box;
			background: var(--vscode-input-background);
			color: var(--vscode-input-foreground);
			border: 1px solid var(--vscode-input-border, transparent);
			border-radius: 2px;
			padding: 4px 6px;
			font-family: var(--vscode-font-family);
			font-size: var(--vscode-font-size);
		}
		.field-row { display: flex; gap: 8px; }
		.field-row .field { flex: 1; }
		.hint { color: var(--vscode-descriptionForeground); font-size: 10px; }

		/* Buttons */
		.btn-primary, .btn-secondary {
			padding: 5px 12px;
			border: none;
			border-radius: 2px;
			cursor: pointer;
			font-family: var(--vscode-font-family);
			font-size: var(--vscode-font-size);
		}
		.btn-primary {
			background: var(--vscode-button-background);
			color: var(--vscode-button-foreground);
			margin-top: 4px;
		}
		.btn-primary:hover { background: var(--vscode-button-hoverBackground); }
		.btn-primary:disabled {
			opacity: 0.5;
			cursor: not-allowed;
		}
		.btn-secondary {
			background: var(--vscode-button-secondaryBackground);
			color: var(--vscode-button-secondaryForeground);
		}
		.btn-secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
		.btn-row { display: flex; gap: 8px; margin: 6px 0; }

		/* Disclaimer */
		.disclaimer {
			border-left: 3px solid var(--vscode-editorWarning-foreground, #f0a500);
			padding: 6px 10px;
			margin-bottom: 10px;
			background: var(--vscode-editorWidget-background);
			font-size: 11px;
			line-height: 1.5;
		}

		/* Status messages */
		.status { font-size: 11px; margin-top: 4px; min-height: 14px; }
		.status.ok { color: var(--vscode-testing-iconPassed, #4caf50); }
		.status.err { color: var(--vscode-errorForeground, #f44); }
		.status.info { color: var(--vscode-descriptionForeground); }

		/* Sections */
		.section { margin-top: 12px; }
		.section-header {
			font-size: 11px;
			font-weight: 600;
			color: var(--vscode-descriptionForeground);
			text-transform: uppercase;
			letter-spacing: 0.04em;
			margin-bottom: 6px;
		}
		.file-list {
			margin: 0 0 10px 0;
			padding: 0 0 0 16px;
			font-size: 11px;
			max-height: 120px;
			overflow-y: auto;
		}
		.file-list li { margin-bottom: 2px; word-break: break-all; }

		/* Data viewer */
		.item-display {
			background: var(--vscode-editor-background);
			border: 1px solid var(--vscode-panel-border);
			border-radius: 2px;
			padding: 8px;
			font-size: 11px;
			white-space: pre-wrap;
			word-break: break-all;
			max-height: 200px;
			overflow-y: auto;
			margin-top: 6px;
		}
		.muted { color: var(--vscode-descriptionForeground); font-size: 12px; }
		.hidden { display: none !important; }
	</style>
</head>
<body>
	<div class="tabs-row">
		<div class="main-tabs">
			<div class="tab" data-main="build">Build</div>
			<div class="tab" data-main="use">Use</div>
		</div>
		<div class="sub-tabs">
			<div class="tab" data-sub="data">Data</div>
			<div class="tab" data-sub="training">Training</div>
			<div class="tab" data-sub="eval">Eval</div>
		</div>
	</div>
	${getBuildTabContent(tabCfg)}
	${getUseTabContent(tabCfg)}

	<script nonce="${nonce}">
	(function () {

		/* ── Tab switching ─────────────────────────────────────────────── */
		const mainTabs = document.querySelectorAll('.main-tabs .tab');
		const subTabs  = document.querySelectorAll('.sub-tabs .tab');
		const mainPanels = document.querySelectorAll('.main-panel');
		const subPanels  = document.querySelectorAll('.sub-panel');
		let activeMain = 'build';
		let activeSub  = 'data';

		function renderTabs() {
			mainTabs.forEach(t => t.classList.toggle('active', t.dataset.main === activeMain));
			subTabs.forEach(t  => t.classList.toggle('active', t.dataset.sub  === activeSub));
			mainPanels.forEach(p => p.classList.toggle('hidden', p.id !== 'panel-' + activeMain));
			subPanels.forEach(p  => p.classList.toggle('hidden',
				p.id !== 'subpanel-' + activeMain + '-' + activeSub));
		}
		mainTabs.forEach(t => t.addEventListener('click', () => { activeMain = t.dataset.main; renderTabs(); }));
		subTabs.forEach(t  => t.addEventListener('click', () => { activeSub  = t.dataset.sub;  renderTabs(); }));
		renderTabs();

		/* ── Config ────────────────────────────────────────────────────── */
		const CFG = ${runtimeConfig};

		/* ── Shared helpers ────────────────────────────────────────────── */
		function setStatus(id, msg, type) {
			const el = document.getElementById(id);
			if (!el) { return; }
			el.textContent = msg;
			el.className = 'status ' + (type || '');
		}

		async function apiCall(baseUrl, method, path, body) {
			const url = baseUrl + path;
			const opts = { method, headers: {} };
			if (body !== undefined) {
				opts.headers['Content-Type'] = 'application/json';
				opts.body = JSON.stringify(body);
			}
			let res;
			try {
				res = await fetch(url, opts);
			} catch (networkErr) {
				throw new Error('Cannot reach ' + url + ' — is the server running?');
			}
			const data = await res.json().catch(() => ({}));
			if (!res.ok) { throw new Error(data.detail || ('HTTP ' + res.status + ' from ' + url)); }
			return data;
		}

		/* ── Shared state ──────────────────────────────────────────────── */
		let preFiles  = [];
		let postData  = null;   // { input: [...], output: [...] }

		/* ── Build / Data : Pre-processing ─────────────────────────────── */
		const btnPreRun = document.getElementById('btn-pre-run');
		if (btnPreRun) {
			btnPreRun.addEventListener('click', async () => {
				const dir      = document.getElementById('build-dir').value.trim();
				const model    = document.getElementById('build-model').value.trim();
				const provider = document.getElementById('build-provider').value.trim();
				if (!dir) { setStatus('pre-status', 'Directory is required.', 'err'); return; }

				btnPreRun.disabled = true;
				setStatus('pre-status', 'Running pre-processing…', 'info');
				try {
					const result = await apiCall(CFG.buildUrl, 'POST', '/data/pre-process', {
						address: dir,
						llm: { model, provider }
					});
					preFiles = result.files || [];

					const ul = document.getElementById('pre-files-list');
					ul.innerHTML = preFiles.length
						? preFiles.map(f => '<li>' + f + '</li>').join('')
						: '<li><em>No files selected.</em></li>';

					// auto-fill raw data address with first result
					const rawInput = document.getElementById('build-raw-addr');
					if (rawInput && preFiles.length > 0) { rawInput.value = preFiles[0]; }

					document.getElementById('pre-results').classList.remove('hidden');
					setStatus('pre-status', 'Found ' + preFiles.length + ' file(s).', 'ok');
				} catch (e) {
					setStatus('pre-status', 'Error: ' + e.message, 'err');
				} finally {
					btnPreRun.disabled = false;
				}
			});
		}

		/* ── Build / Data : Post-processing ─────────────────────────────── */
		const btnPostRun = document.getElementById('btn-post-run');
		if (btnPostRun) {
			btnPostRun.addEventListener('click', async () => {
				const dir      = document.getElementById('build-dir').value.trim();
				const rawAddr  = document.getElementById('build-raw-addr').value.trim();
				const model    = document.getElementById('build-model').value.trim();
				const provider = document.getElementById('build-provider').value.trim();
				if (!rawAddr) { setStatus('post-status', 'Raw data address is required.', 'err'); return; }

				btnPostRun.disabled = true;
				setStatus('post-status', 'Running post-processing…', 'info');
				try {
					const result = await apiCall(CFG.buildUrl, 'POST', '/data/post-process', {
						address: dir,
						raw_data_address: rawAddr,
						llm: { model, provider }
					});
					postData = result;

					const summary = document.getElementById('post-summary');
					summary.textContent = 'Input: ' + result.input.length + ' item(s)' +
						(result.output ? ',  Output: ' + result.output.length + ' item(s)' : '') + '.';
					summary.classList.remove('hidden');

					setStatus('post-status', 'Post-processing complete.', 'ok');

					// unlock the Use/Data load button
					const loadBtn = document.getElementById('btn-load-data');
					if (loadBtn) {
						loadBtn.disabled = false;
						const noData = document.getElementById('use-no-data');
						if (noData) {
							noData.querySelector('p').textContent =
								'Post-processing done (' + result.input.length +
								' items). Click Load to push into the runtime.';
						}
					}
				} catch (e) {
					setStatus('post-status', 'Error: ' + e.message, 'err');
				} finally {
					btnPostRun.disabled = false;
				}
			});
		}

		/* ── Use / Data : Load into runtime ─────────────────────────────── */
		const btnLoad = document.getElementById('btn-load-data');
		if (btnLoad) {
			btnLoad.addEventListener('click', async () => {
				if (!postData) { return; }
				btnLoad.disabled = true;
				setStatus('load-status', 'Loading…', 'info');
				try {
					const result = await apiCall(CFG.runtimeUrl, 'POST', '/data/init', {
						input: postData.input,
						output: postData.output || null
					});
					setStatus('load-status', 'Loaded.', 'ok');

					const stats = document.getElementById('use-data-stats');
					stats.textContent = result.length + ' item(s) in runtime' +
						(result.has_output ? ',  has output.' : ',  no output.');

					document.getElementById('use-data-view').classList.remove('hidden');
				} catch (e) {
					setStatus('load-status', 'Error: ' + e.message, 'err');
					btnLoad.disabled = false;
				}
			});
		}

		/* ── Use / Data : Next item ──────────────────────────────────────── */
		const btnNext = document.getElementById('btn-next-item');
		if (btnNext) {
			btnNext.addEventListener('click', async () => {
				try {
					const item = await apiCall(CFG.runtimeUrl, 'GET', '/data/next');
					document.getElementById('use-data-item').textContent = JSON.stringify(item, null, 2);
				} catch (e) {
					document.getElementById('use-data-item').textContent = 'Error: ' + e.message;
				}
			});
		}

		/* ── Use / Data : Reset cursor ───────────────────────────────────── */
		const btnReset = document.getElementById('btn-reset-cursor');
		if (btnReset) {
			btnReset.addEventListener('click', async () => {
				try {
					await apiCall(CFG.runtimeUrl, 'POST', '/data/reset');
					document.getElementById('use-data-item').textContent = '(cursor reset)';
				} catch (e) {
					document.getElementById('use-data-item').textContent = 'Error: ' + e.message;
				}
			});
		}

	})();
	</script>
</body>
</html>`;
	}
}

export function activate(context: vscode.ExtensionContext) {

	console.log('BojAI activated');

	const provider = new BojaiViewProvider();

	context.subscriptions.push(
		vscode.window.registerWebviewViewProvider('bojaiView', provider)
	);

	const disposable = vscode.commands.registerCommand(
		'bojai.helloWorld',
		() => {
			vscode.window.showInformationMessage('Hello World from BojAI!');
		}
	);

	context.subscriptions.push(disposable);
}

export function deactivate() {}
