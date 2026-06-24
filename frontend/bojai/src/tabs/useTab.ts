import { getDataTabContent, DataTabConfig } from './dataTab';
import { getTrainingTabContent } from './trainingTab';
import { getEvalTabContent } from './evalTab';

export function getUseTabContent(cfg: DataTabConfig): string {
	return `
		<div class="main-panel hidden" id="panel-use">
			${getDataTabContent('use', cfg)}
			${getTrainingTabContent('use')}
			${getEvalTabContent('use')}
		</div>
	`;
}
