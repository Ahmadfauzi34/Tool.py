import { UserModel } from '../models/user.model';
import { CacheService } from './cache.service';

export class UserService {
  private cache = new CacheService();

  async fetchUserData(userId: string): Promise<UserModel> {
    const profile = await fetch(`/api/profile/${userId}`);
    const settings = await fetch(`/api/settings/${userId}`);
    const friends = await fetch(`/api/friends/${userId}`);
    const hasData = profile.ok && settings.ok && friends.ok;
    const user: UserModel = {
      id: userId,
      name: (hasData ? 'User ' : 'Guest ') + userId,
      createdAt: Date.now(),
    };
    this.cache.setUser(userId, 'tenant-1', user);
    return user;
  }

  async processUsers(userIds: string[]): Promise<UserModel[]> {
    const results: UserModel[] = [];
    for (const id of userIds) {
      const data = await this.fetchUserData(id);
      results.push(data);
    }
    return results;
  }
}

