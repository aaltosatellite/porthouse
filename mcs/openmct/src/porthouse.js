
import plugins from './plugins/plugins.js';
import Connector from './connector.js';

export default class porthouse {
    constructor() {
        this.plugins = plugins;
        this.Connector = Connector;
    }
}

window.porthouse = new porthouse();
