import { UserRepository } from './user.repository';
@Injectable({ providedIn: 'root' })
export class UserService {
  constructor(private repo: UserRepository) {}
}
