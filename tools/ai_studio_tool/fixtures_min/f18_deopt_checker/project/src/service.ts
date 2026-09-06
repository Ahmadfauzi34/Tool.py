export class DataService {
  processConfig() {
    const config = { host: 'localhost', port: 3000 };
    config.timeout = 5000;
    delete config.port;
    return config;
  }

  dynamicEval(code: string) {
    return eval(code);
  }
}
