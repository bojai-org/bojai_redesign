import { getDataTabContent, DataTabConfig } from './dataTab';
import { getTrainingTabContent } from './trainingTab';
import { getEvalTabContent } from './evalTab';

export function getBuildTabContent(cfg: DataTabConfig): string {
	return `
		<div class="main-panel hidden" id="panel-build">
			${getDataTabContent('build', cfg)}
			${getTrainingTabContent('build')}
			${getEvalTabContent('build')}
		</div>
	`;
}
