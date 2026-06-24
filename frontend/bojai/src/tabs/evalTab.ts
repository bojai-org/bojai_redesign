export function getEvalTabContent(context: 'build' | 'use'): string {
	const description = context === 'build'
		? 'Configure how the built model should be evaluated.'
		: 'Review evaluation results for this run.';
	return `
		<div class="sub-panel hidden" id="subpanel-${context}-eval">
			<h4>Eval</h4>
			<p>${description}</p>
		</div>
	`;
}
