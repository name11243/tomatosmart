import {use,init} from 'echarts/core';
import {GraphChart,LineChart} from 'echarts/charts';
import {GridComponent,TooltipComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
use([GraphChart,LineChart,GridComponent,TooltipComponent,CanvasRenderer]);
export {init};
