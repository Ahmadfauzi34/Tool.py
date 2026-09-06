import { UserService } from '../services/user.service';

export interface UserModel {
  id: string;
  name: string;
  createdAt: number;
  activeServiceInstance?: UserService;
}

export function validateUserModel(user: UserModel): boolean {
  if (user.activeServiceInstance) {
    return true;
  }
  return !!user.id;
}

