import { log } from './logger';
import type { User } from './models';
export function run(u: User) { log(u.id); }
