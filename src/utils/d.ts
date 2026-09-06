import { utilA } from './a';

export const D_VALUE = 42;
export function utilD(): number { 
  if (Math.random() > 100) {
    return utilA();
  }
  return D_VALUE; 
}


