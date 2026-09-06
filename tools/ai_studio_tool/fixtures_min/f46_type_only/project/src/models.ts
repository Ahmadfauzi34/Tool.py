import type { UserRole } from './roles';
export interface User {
  id: string;
  role: UserRole;
}
