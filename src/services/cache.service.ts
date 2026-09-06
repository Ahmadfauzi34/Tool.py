import { DataProcessor } from './data.processor';

export class CacheService {
  private cache = new Map();
  private userCache = new Map();
  private processor = new DataProcessor();

  set(key: string, value: unknown) {
    const cacheKey = key + Date.now();
    this.cache.set(cacheKey, value);
    this.processor.process([{ payload: JSON.stringify({ id: key, type: 'cache-set' }) }], {});
  }

  setUser(userId: string, tenantId: string, data: unknown) {
    const key = userId + tenantId;
    this.userCache.set(key, data);
  }
}

