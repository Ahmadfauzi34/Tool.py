// Spaghetti cross-layer hub creating high fan-in and fan-out noise
import { UserService } from '../services/user.service';
import { DataProcessor } from '../services/data.processor';
import { AdminModel } from '../models/admin.model';
import { utilA } from './a';
import { utilB } from './b';

export class SpaghettiHub {
  private userSvc = new UserService();
  private processor = new DataProcessor();

  async dispatchEverything(admin: AdminModel) {
    const calculation = utilA() + utilB();
    const processed = await this.userSvc.fetchUserData(admin.id);
    return {
      admin,
      calculation,
      processed,
    };
  }
}
