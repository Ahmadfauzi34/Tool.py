export class DataProcessor {
  private cache = new Map();

  processItems(items: any[]) {
    const results = [];
    for (const item of items) {
      const parsed = JSON.parse(item.data);
      const result = { id: parsed.id, value: parsed.value };
      results.push(result);
    }
    return results;
  }

  setupPolling() {
    const timer = setInterval(() => {
      this.poll();
    }, 5000);
  }

  attachListener(el: HTMLElement) {
    el.addEventListener('resize', this.handleResize);
  }
}
