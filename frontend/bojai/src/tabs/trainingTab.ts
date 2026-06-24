export function getTrainingTabContent(context: 'build' | 'use'): string {
	const description = context === 'build'
		? 'Configure how the model should be trained.'
		: 'Track or resume training runs from here.';
	return `
		<div class="sub-panel hidden" id="subpanel-${context}-training">
			<h4>Training</h4>
			<p>${description}</p>
		</div>
	`;
}
