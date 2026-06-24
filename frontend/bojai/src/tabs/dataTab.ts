export interface DataTabConfig {
	wsRoot: string;
	defaultModel: string;
	defaultProvider: string;
}

export function getDataTabContent(context: 'build' | 'use', cfg: DataTabConfig): string {
	if (context === 'build') {
		return getBuildDataHtml(cfg);
	}
	return getUseDataHtml();
}

function getBuildDataHtml(cfg: DataTabConfig): string {
	const dir = cfg.wsRoot.replace(/\\/g, '/');
	return `
	<div class="sub-panel hidden" id="subpanel-build-data">
		<div class="disclaimer">
			<strong>Note:</strong> Pre-processing scans <em>file names and extension types only</em>
			— it does not read file contents.
		</div>

		<div class="field">
			<label>Project directory</label>
			<input id="build-dir" type="text" value="${dir}" placeholder="/path/to/project" />
		</div>
		<div class="field-row">
			<div class="field">
				<label>Model</label>
				<input id="build-model" type="text" value="${cfg.defaultModel}" />
			</div>
			<div class="field">
				<label>Provider</label>
				<input id="build-provider" type="text" value="${cfg.defaultProvider}" />
			</div>
		</div>
		<button class="btn-primary" id="btn-pre-run">Run Pre-Processing</button>
		<div class="status" id="pre-status"></div>

		<div id="pre-results" class="hidden section">
			<div class="section-header">Selected files</div>
			<ul id="pre-files-list" class="file-list"></ul>

			<div class="field">
				<label>Raw data address <span class="hint">(auto-filled, editable)</span></label>
				<input id="build-raw-addr" type="text" placeholder="path/to/raw/data" />
			</div>
			<button class="btn-primary" id="btn-post-run">Run Post-Processing</button>
			<div class="status" id="post-status"></div>

			<div id="post-summary" class="hidden section-header"></div>
		</div>
	</div>`;
}

function getUseDataHtml(): string {
	return `
	<div class="sub-panel hidden" id="subpanel-use-data">
		<div id="use-no-data">
			<p class="muted">Run <strong>Build → Data</strong> first, then load the result into the runtime.</p>
			<button class="btn-primary" id="btn-load-data" disabled>Load into Runtime</button>
			<div class="status" id="load-status"></div>
		</div>

		<div id="use-data-view" class="hidden section">
			<div id="use-data-stats" class="section-header"></div>
			<div class="btn-row">
				<button class="btn-secondary" id="btn-next-item">Next Item</button>
				<button class="btn-secondary" id="btn-reset-cursor">Reset</button>
			</div>
			<pre id="use-data-item" class="item-display"></pre>
		</div>
	</div>`;
}
