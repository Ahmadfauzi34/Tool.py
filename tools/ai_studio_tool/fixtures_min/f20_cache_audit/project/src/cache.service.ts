export class CacheService {
  private dataCache = new Map();
  private sessionCache = new Map();

  setWithTimestamp(key: string, value: any) {
    const cacheKey = key + Date.now();
    this.dataCache.set(cacheKey, value);
  }

  setWithConcat(userId: string, productId: string) {
    const key = userId + productId;
    this.dataCache.set(key, { userId, productId });
  }

  setObjectKey(config: any, result: any) {
    this.sessionCache.set(config, result);
  }

  getWithObject(config: any) {
    return this.sessionCache.get(config);
  }
}
